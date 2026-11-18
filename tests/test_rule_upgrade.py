"""验证已有项目的规则升级、属主校验、暂存边界和失败恢复。"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bootstrap.model import DIRECTORY, BootstrapError, render
from bootstrap.storage import apply, inspect, source_version
from bootstrap.upgrade import ProjectLayout, recover_upgrade, upgrade
from lifecycle.transaction import publish


class RuleUpgradeTests(unittest.TestCase):
    """以旧版生成结果作为夹具，使用独立新来源验证实际差异。"""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        self.project = base / "project"
        self.project.mkdir()
        self.toolkit = base / "source"
        shutil.copytree(ROOT / "standards", self.toolkit / "standards")
        shutil.copytree(
            ROOT / "templates/project-bootstrap", self.toolkit / "templates/project-bootstrap"
        )
        self.config = {
            "schema_version": 1,
            "stacks": {"react-vite": ["."]},
            "checks": [{"name": "示例检查", "cwd": ".", "argv": ["python3", "--version"]}],
            "deviations": ["本项目保留现有约定"],
            "commit_policy": "manual",
        }
        files, block, identity = render(ROOT, self.config)
        (self.project / "AGENTS.md").write_bytes(b"# User rules\r\n")
        apply(self.project, files, block, source_version(ROOT, identity), b"# User rules\r\n")
        self.managed = self.project / DIRECTORY
        self.agents = self.project / "AGENTS.md"
        self.comments = "standards/common/comments.md"
        with (self.toolkit / self.comments).open("ab") as handle:
            handle.write("\n新版本的说明。\n".encode())

    def run_upgrade(self, *, apply_changes=False, config=None):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = upgrade(self.toolkit, self.project, config, apply_changes)
        return status, stdout.getvalue()

    def test_preview_apply_and_repeat_preserve_custom_content_and_index(self):
        with self.agents.open("ab") as handle:
            handle.write(b"\nUser suffix\r\n")
        extra = self.managed / "mine.md"
        extra.write_text("项目自维护说明\n")
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        subprocess.run(["git", "-C", str(self.project), "add", "AGENTS.md"], check=True)
        index = self.project / ".git/index"
        index_bytes = index.read_bytes()
        old = (self.managed / self.comments).read_bytes()
        status, diff = self.run_upgrade()
        self.assertEqual(status, "preview")
        self.assertIn("+新版本的说明。", diff)
        self.assertEqual((self.managed / self.comments).read_bytes(), old)
        layout = ProjectLayout.create(self.project)
        self.assertFalse(layout.backups.exists())
        status, _ = self.run_upgrade(apply_changes=True)
        self.assertEqual(status, "upgraded")
        self.assertEqual(extra.read_text(), "项目自维护说明\n")
        self.assertTrue(self.agents.read_bytes().startswith(b"# User rules\r\n"))
        self.assertTrue(self.agents.read_bytes().endswith(b"\nUser suffix\r\n"))
        self.assertEqual(index.read_bytes(), index_bytes)
        self.assertEqual(json.loads((self.managed / "project.json").read_bytes()), self.config)
        files, block, identity = render(self.toolkit, self.config)
        self.assertTrue(inspect(self.project, files, block, identity)[1])
        self.assertEqual(self.run_upgrade(apply_changes=True)[0], "unchanged")
        (transaction,) = layout.backups.glob("txn-*")
        self.assertEqual((transaction / "before/root" / self.comments).read_bytes(), old)

    def test_explicit_config_updates_stack_and_removes_only_old_owned_copy(self):
        config = Path(self.project.parent) / "next.json"
        next_config = dict(self.config, stacks={"fastapi": ["."]})
        config.write_text(json.dumps(next_config))
        owned = self.managed / "standards/frontend/react-vite.md"
        extra = owned.with_name("custom.md")
        extra.write_text("自定义前端约定")
        status, _ = self.run_upgrade(apply_changes=True, config=config)
        self.assertEqual(status, "upgraded")
        self.assertFalse(owned.exists())
        self.assertEqual(extra.read_text(), "自定义前端约定")
        self.assertIn("fastapi", self.agents.read_text())

    def test_modified_managed_file_and_new_path_collision_are_rejected(self):
        target = self.managed / self.comments
        before = target.read_bytes()
        target.write_text("项目手工修改")
        with self.assertRaisesRegex(BootstrapError, "受管文件已改动"):
            self.run_upgrade(apply_changes=True)
        self.assertEqual(target.read_text(), "项目手工修改")
        target.write_bytes(before)
        candidate = self.managed / "standards/backend/fastapi.md"
        candidate.parent.mkdir()
        candidate.write_text("项目自有同名规范")
        config = self.project.parent / "next.json"
        config.write_text(json.dumps(dict(self.config, stacks={"fastapi": ["."]})))
        with self.assertRaisesRegex(BootstrapError, "项目自有文件冲突"):
            self.run_upgrade(apply_changes=True, config=config)
        self.assertEqual(candidate.read_text(), "项目自有同名规范")

    def test_failure_after_directory_publish_restores_old_content(self):
        before = (self.managed / self.comments).read_bytes()
        config = self.project.parent / "next.json"
        config.write_text(json.dumps(dict(self.config, stacks={"fastapi": ["."]})))

        def fail_agents(target, stored, description, transaction):
            if target == self.agents:
                raise OSError("模拟入口写入失败")
            return publish(target, stored, description, transaction)

        with (
            patch("lifecycle.transaction.publish", side_effect=fail_agents),
            self.assertRaisesRegex(OSError, "模拟入口写入失败"),
        ):
            self.run_upgrade(apply_changes=True, config=config)
        layout = ProjectLayout.create(self.project)
        self.assertFalse(layout.lock.exists())
        self.assertEqual((self.managed / self.comments).read_bytes(), before)
        (transaction,) = layout.backups.glob("txn-*")
        self.assertEqual(
            recover_upgrade(self.project, transaction, False)["status"], "no_recovery_needed"
        )

    def test_disrupted_process_upgrade_can_be_recovered_from_real_cli(self):
        before = (self.managed / self.comments).read_bytes()
        code = """
import os, sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from bootstrap.upgrade import upgrade
from lifecycle.transaction import publish
def interrupt(*args):
    publish(*args)
    os._exit(73)
with patch("lifecycle.transaction.publish", side_effect=interrupt):
    upgrade(Path(sys.argv[2]), Path(sys.argv[3]), None, True)
"""
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                code,
                str(ROOT / "scripts"),
                str(self.toolkit),
                str(self.project),
            ],
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 73, result.stderr)
        layout = ProjectLayout.create(self.project)
        (transaction,) = layout.backups.glob("txn-*")
        command = [
            sys.executable,
            str(ROOT / "scripts/ai-dev-standards"),
            "upgrade-rules",
            "--project",
            str(self.project),
            "--recover",
            str(transaction),
        ]
        self.assertEqual(json.loads(subprocess.check_output(command))["status"], "recovery_preview")
        self.assertEqual(
            json.loads(subprocess.check_output([*command, "--apply"]))["status"], "recovered"
        )
        self.assertEqual((self.managed / self.comments).read_bytes(), before)
        self.assertFalse(layout.lock.exists())


if __name__ == "__main__":
    unittest.main()
