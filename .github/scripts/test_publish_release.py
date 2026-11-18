"""用隔离夹具验证版本编号和发版中断后的重跑。"""

import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import publish_release as release

REPO = "owner/toolkit"
SOURCE = "a" * 40
BASE = "b" * 40


class PublishTests(unittest.TestCase):
    def setUp(self):
        location = tempfile.TemporaryDirectory()
        self.addCleanup(location.cleanup)
        self.folder = Path(location.name)
        self.package = self.folder / "tool.pyz"
        self.checksum = self.package.with_suffix(".sha256")
        self.package.write_text("发行包", encoding="utf-8")
        self.checksum.write_bytes(b"sha256")
        self.releases = [{"tag_name": "v0.1.0", "draft": False, "prerelease": False}]
        self.refs = []
        self.uploads = []
        self.head = BASE
        self.tags = "v0.1.0"
        self.fail_checksum = False
        self.fail_publish = False
        patches = (
            patch.dict(os.environ, GITHUB_SERVER_URL="https://github.com", GITHUB_RUN_ID="123"),
            patch.object(release, "api", self.api),
            patch.object(release, "git", self.git),
            patch.object(release, "verify_package", return_value=self.package),
            patch.object(release.subprocess, "run", self.upload),
        )
        for fixture in patches:
            fixture.start()
            self.addCleanup(fixture.stop)

    def git(self, action, *args):
        return {"rev-parse": self.head, "merge-base": self.head, "tag": self.tags}[action]

    def api(self, repo, endpoint, *args, payload=None):
        self.assertEqual(repo, REPO)
        if endpoint == "releases?per_page=100":
            return [self.releases]
        if endpoint == "releases" and args == ("--method", "POST"):
            draft = dict(payload, id=10, prerelease=False, assets=[])
            self.releases.append(draft)
            return draft
        if endpoint.startswith("git/matching-refs/tags/"):
            return self.refs
        if endpoint == "git/refs" and args == ("--method", "POST"):
            self.assertEqual(len(self.releases[-1]["assets"]), 2)
            ref = {"ref": payload["ref"], "object": {"type": "commit", "sha": payload["sha"]}}
            self.refs.append(ref)
            return ref
        if endpoint == "releases/10":
            draft = self.releases[-1]
            if args == ("--method", "PATCH"):
                self.assertEqual(len(self.refs), 1)
                self.assertEqual(payload, {"draft": False, "make_latest": "true"})
                if self.fail_publish:
                    raise subprocess.CalledProcessError(1, "gh api")
                url = f"https://github.com/{repo}/releases/tag/{draft['tag_name']}"
                draft.update(draft=False, html_url=url)
                self.head = SOURCE
            return draft
        self.fail(f"遇到未预期的 GitHub API 调用 {endpoint} {args}")

    def upload(self, command, *, check):
        self.assertTrue(check)
        self.assertEqual(command[:3], ["gh", "release", "upload"])
        self.assertEqual(command[-2:], ["--repo", REPO])
        draft = self.releases[-1]
        self.assertTrue(draft["draft"])
        self.assertEqual(command[3], draft["tag_name"])
        for name in command[4:-2]:
            path = Path(name)
            if path == self.checksum and self.fail_checksum:
                raise subprocess.CalledProcessError(1, command)
            digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            draft["assets"].append({"name": path.name, "digest": digest, "state": "uploaded"})
            self.uploads.append(path.name)

    def publish(self, base="v0.1.0"):
        release.publish(REPO, SOURCE, base, self.folder)

    def test_partial_upload_resumes_and_completed_release_is_idempotent(self):
        self.fail_checksum = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.publish()
        self.assertTrue(self.releases[-1]["draft"])
        self.assertEqual(self.refs, [])
        self.fail_checksum = False
        self.publish()
        self.publish()
        self.assertEqual(len(self.releases), 2)
        self.assertEqual(self.releases[-1]["tag_name"], "v0.1.1")
        self.assertFalse(self.releases[-1]["draft"])
        self.assertEqual(self.uploads, ["tool.pyz", "tool.sha256"])

    def test_unrelated_versions_and_drafts_are_preserved(self):
        self.tags += "\nv0.1.1\nv2.0.0"
        self.releases.append({"tag_name": "v0.1.2", "draft": True, "prerelease": False})
        self.publish()
        self.assertEqual(self.releases[-1]["tag_name"], "v0.1.3")
        self.assertTrue(self.releases[1]["draft"])

    def test_publish_retries_after_the_tag_was_created(self):
        self.fail_publish = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.publish()
        self.assertEqual(len(self.refs), 1)
        self.assertTrue(self.releases[-1]["draft"])
        self.fail_publish = False
        self.publish()
        self.assertFalse(self.releases[-1]["draft"])
        self.assertEqual(self.uploads, ["tool.pyz", "tool.sha256"])

    def test_draft_with_altered_attachment_is_never_published(self):
        self.fail_checksum = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.publish()
        self.releases[-1]["assets"][0]["digest"] = "sha256:损坏"
        self.fail_checksum = False
        with self.assertRaisesRegex(ValueError, "与已验收产物不一致"):
            self.publish()
        self.assertTrue(self.releases[-1]["draft"])
        self.assertEqual(self.refs, [])

    def test_changed_baseline_and_conflicting_tag_stop_before_publish(self):
        with self.assertRaisesRegex(ValueError, "升级基线已由"):
            self.publish(base="v0.0.1")
        self.assertEqual(len(self.releases), 1)
        self.refs.append({"ref": "refs/tags/v0.1.1", "object": {"type": "commit", "sha": BASE}})
        with self.assertRaisesRegex(ValueError, "已由其他发布占用"):
            self.publish()
        self.assertTrue(self.releases[-1]["draft"])


if __name__ == "__main__":
    unittest.main()
