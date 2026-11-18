"""固定版本安装的网络、来源和隔离生命周期验证。"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import install_release as installer
import toolkit
from lifecycle.model import STAMP, bundle
from scaffold.release import build


class FixedReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        base = Path(temporary.name)
        source = base / "source"
        files, _ = bundle(ROOT)
        for name, body in files.items():
            if name != STAMP:
                target = source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        cls.releases = {}
        for version in ("v0.1.0", "v0.1.1"):
            # 从独立提交实际构建，确保测试的字节和安装入口符合发行格式。
            rule = source / "rules/global.md"
            rule.write_bytes(rule.read_bytes() + f"\n<!-- 测试版本 {version} -->\n".encode())
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(source),
                    "-c",
                    "user.name=测试",
                    "-c",
                    "user.email=test@example.com",
                    "-c",
                    "commit.gpgsign=false",
                    "commit",
                    "-qm",
                    f"测试 {version}",
                ],
                check=True,
            )
            commit = subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
            )
            package, checksum = build(source, commit.strip(), base / version)
            cls.releases[version] = (commit.strip(), package, checksum)

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name).resolve()
        self.args = argparse.Namespace(
            home=self.home, codex_home=None, legacy_policy=None, apply=True
        )
        self.codex = self.home / ".codex"
        self.codex.mkdir()
        self.config = self.codex / "config.toml"
        self.config.write_bytes(b"# user\n")
        self.agents = self.codex / "AGENTS.md"
        self.agents.write_bytes(b"# user rules\n")
        self.responses = {}
        self.mock_network = patch.object(installer, "request_bytes", side_effect=self.request)
        self.mock_network.start()
        self.addCleanup(self.mock_network.stop)
        for key, (version, (commit, package, checksum)) in enumerate(self.releases.items(), 1):
            assets = []
            for asset_id, path in ((key * 10, package), (key * 10 + 1, checksum)):
                body = path.read_bytes()
                self.responses[f"releases/assets/{asset_id}"] = body
                assets.append({"id": asset_id, "name": path.name, "state": "uploaded"})
            self.responses[f"releases/tags/{version}"] = {
                "tag_name": version,
                "draft": False,
                "prerelease": False,
                "assets": assets,
            }
            target = {"type": "commit", "sha": commit}
            if version == "v0.1.0":
                self.responses["git/tags/" + "a" * 40] = {"object": target}
                target = {"type": "tag", "sha": "a" * 40}
            self.responses[f"git/ref/tags/{version}"] = {
                "ref": f"refs/tags/{version}",
                "object": target,
            }

    def request(self, endpoint, accept="application/vnd.github+json"):
        value = self.responses[endpoint]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, bytes):
            self.assertEqual(accept, "application/octet-stream")
            return value
        return json.dumps(value).encode()

    def command(self, action, version=None, *, apply=False):
        args = [action, "--home", str(self.home)]
        if version is not None:
            args.extend(["--version", version])
        if apply:
            args.append("--apply")
        result = None

        def call(command):
            nonlocal result
            completed = subprocess.run(command, check=True, capture_output=True)
            result = json.loads(completed.stdout)
            return completed.returncode

        if version is None:
            call([sys.executable, str(ROOT / "scripts/toolkit.py"), *args])
        else:
            with patch.object(installer.subprocess, "call", side_effect=call):
                self.assertEqual(toolkit.main(args), 0)
        return result

    def test_fixed_version_previews_updates_and_retains_user_files(self):
        manifest = self.codex / "ai-dev-standards/manifest.json"
        self.assertEqual(self.command("install", "v0.1.0")["status"], "preview")
        self.assertFalse(manifest.exists())
        self.assertEqual(self.command("install", "v0.1.0", apply=True)["status"], "deployed")
        self.assertEqual(self.command("install", "v0.1.0", apply=True)["status"], "unchanged")
        before_update = manifest.read_bytes()
        self.assertEqual(self.command("update", "v0.1.1")["status"], "preview")
        self.assertEqual(manifest.read_bytes(), before_update)
        self.assertEqual(self.command("update", "v0.1.1", apply=True)["status"], "deployed")
        commit = self.releases["v0.1.1"][0]
        launcher = self.codex / "ai-dev-standards/bundle/scripts/ai-dev-standards"
        version = subprocess.check_output([sys.executable, str(launcher), "--version"], text=True)
        self.assertIn(f"v0.1.1（Git {commit}）", version)
        offline_package = self.releases["v0.1.1"][1]
        offline = subprocess.check_output(
            [sys.executable, str(offline_package), "--version"], text=True
        )
        self.assertIn(f"未记录发布标签（Git {commit}）", offline)
        self.assertEqual(self.command("doctor")["source"]["release_version"], "v0.1.1")
        self.assertEqual(self.command("update", "v0.1.1", apply=True)["status"], "unchanged")
        self.assertEqual(self.command("uninstall", apply=True)["status"], "uninstalled")
        self.assertEqual(self.config.read_bytes(), b"# user\n")
        self.assertEqual(self.agents.read_bytes(), b"# user rules\n")

    def test_download_failures_stop_before_writing_user_files(self):
        endpoint = "releases/tags/v0.1.1"
        metadata = self.responses[endpoint]
        for value, message in (
            (HTTPError("https://api.github.com", 404, "Not Found", {}, None), "找不到已发布"),
            (URLError("网络失败"), "连接 GitHub 失败"),
            (dict(metadata, assets=metadata["assets"][:1]), "缺少可下载的附件"),
        ):
            self.responses[endpoint] = value
            with self.assertRaisesRegex(installer.ReleaseError, message):
                installer.run_release("install", "v0.1.1", self.args)
        self.responses[endpoint] = metadata
        with self.assertRaisesRegex(installer.ReleaseError, "固定的正式版本号"):
            installer.run_release("install", "latest", self.args)
        asset = metadata["assets"][0]
        asset["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(installer.ReleaseError, "SHA-256 与 GitHub 记录不一致"):
            installer.run_release("install", "v0.1.1", self.args)
        del asset["digest"]
        self.responses["releases/assets/21"] = "错误的校验值".encode()
        with self.assertRaisesRegex(installer.ReleaseError, "校验文件不一致"):
            installer.run_release("install", "v0.1.1", self.args)
        self.assertEqual(
            sorted(path.name for path in self.codex.iterdir()), ["AGENTS.md", "config.toml"]
        )
        self.assertEqual(self.config.read_bytes(), b"# user\n")
        self.assertEqual(self.agents.read_bytes(), b"# user rules\n")

    def test_tag_sha_must_match_packaged_origin_even_when_checksum_matches(self):
        original = self.responses["releases/assets/20"]
        updated = io.BytesIO()
        with ZipFile(io.BytesIO(original)) as archive, ZipFile(updated, "w") as output:
            for name in archive.namelist():
                body = archive.read(name)
                if name == STAMP:
                    stamp = json.loads(body)
                    stamp["source"]["git_commit"] = "0" * 40
                    body = json.dumps(stamp).encode()
                output.writestr(name, body)
        payload = self.responses["releases/assets/20"] = updated.getvalue()
        filename = self.releases["v0.1.1"][1].name
        self.responses["releases/assets/21"] = (
            f"{hashlib.sha256(payload).hexdigest()}  {filename}\n".encode()
        )
        with self.assertRaisesRegex(installer.ReleaseError, "发行包来源与标签"):
            installer.run_release("install", "v0.1.1", self.args)
        self.assertFalse((self.codex / "ai-dev-standards").exists())
