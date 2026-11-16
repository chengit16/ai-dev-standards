"""在临时项目中验证初始化的隔离、重复运行与冲突保护，不接触用户配置。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bootstrap.model import BEGIN, DIRECTORY, BootstrapError, render, validate_config
from bootstrap.storage import apply


def config(stacks=None):
    """生成只涉及合成目录的采用输入，不声明未提供的测试工具。"""
    return {
        "schema_version": 1,
        "stacks": stacks or {"react-vite": ["."]},
        "checks": [],
        "deviations": [],
        "commit_policy": "local",
    }


class BootstrapTests(unittest.TestCase):
    """通过 CLI 结果及落盘内容核验跨次运行行为。"""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.project = self.base / "带 空格的项目"
        self.project.mkdir()
        self.configuration = self.base / "input.json"
        self.configuration.write_text(json.dumps(config()))

    def run_cli(self, apply_changes=False):
        """以独立进程运行公开入口，配置路径不进入目标项目。"""
        args = [
            sys.executable,
            str(ROOT / "scripts/project_bootstrap.py"),
            "--project",
            str(self.project),
            "--config",
            str(self.configuration),
        ]
        if apply_changes:
            args.append("--apply")
        return subprocess.run(args, capture_output=True, text=True, check=False)

    def snapshot(self):
        """捕获文件内容与时间，防止幂等检查偷偷重写相同内容。"""
        return {
            p.relative_to(self.project).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in self.project.rglob("*")
            if p.is_file()
        }

    def test_preview_no_writes(self):
        self.assertEqual(self.run_cli().returncode, 0)
        self.assertEqual(list(self.project.iterdir()), [])

    def test_first_run_preserves_agents_and_git_index(self):
        original = b"# Existing rules\r\nKeep my conventions."
        (self.project / "AGENTS.md").write_bytes(original)
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        subprocess.run(["git", "-C", str(self.project), "add", "AGENTS.md"], check=True)
        index = (self.project / ".git/index").read_bytes()
        self.assertEqual(self.run_cli(True).returncode, 0)
        self.assertTrue((self.project / "AGENTS.md").read_bytes().startswith(original))
        self.assertEqual((self.project / ".git/index").read_bytes(), index)
        self.assertTrue((self.project / DIRECTORY / "standards/common/comments.md").is_file())
        self.assertFalse((self.project / DIRECTORY / "standards/backend/fastapi.md").exists())

    def test_repeat_is_byte_and_time_identical(self):
        self.assertEqual(self.run_cli(True).returncode, 0)
        before = self.snapshot()
        self.configuration = self.project / DIRECTORY / "project.json"
        self.assertEqual(self.run_cli(True).returncode, 0)
        self.assertEqual(before, self.snapshot())
        self.assertEqual((self.project / "AGENTS.md").read_text().count(BEGIN), 1)

    def test_user_rules_outside_block_survive_repeat(self):
        self.assertEqual(self.run_cli(True).returncode, 0)
        entry = self.project / "AGENTS.md"
        entry.write_text("# 用户开头\n" + entry.read_text() + "\n用户末尾\n")
        before = self.snapshot()
        self.assertEqual(self.run_cli(True).returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_all_stack_combinations_have_local_links(self):
        import re
        from urllib.parse import urlsplit

        for stacks in (
            {"nestjs-fastify": ["."]},
            {"fastapi": ["."]},
            {"react-vite": ["."], "fastapi": ["."], "nestjs-fastify": ["."]},
        ):
            with self.subTest(stacks=stacks):
                files, _, _ = render(ROOT, validate_config(config(stacks), self.project))
                for name, data in files.items():
                    if not name.startswith("standards/"):
                        continue
                    for href in re.findall(r"\[[^\]]+\]\(([^)]+)\)", data.decode()):
                        url = urlsplit(href)
                        if url.scheme or not url.path:
                            continue
                        resolved = (Path("/bundle") / name).parent / url.path
                        key = resolved.resolve().relative_to("/bundle").as_posix()
                        self.assertIn(key, files)

    def test_existing_foreign_directory_is_not_claimed(self):
        (self.project / DIRECTORY).mkdir()
        (self.project / DIRECTORY / "mine.txt").write_text("私有文件")
        before = self.snapshot()
        self.assertNotEqual(self.run_cli(True).returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_modified_files_and_block_are_not_overwritten(self):
        for target in (
            "standards/common/comments.md",
            "project.json",
            "PROJECT.md",
            "../AGENTS.md",
        ):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as folder:
                old_project = self.project
                self.project = Path(folder)
                self.assertEqual(self.run_cli(True).returncode, 0)
                path = self.project / DIRECTORY / target
                path.write_text(path.read_text().replace("规范", "项目定制", 1) + "\n")
                before = self.snapshot()
                self.assertNotEqual(self.run_cli(True).returncode, 0)
                self.assertEqual(before, self.snapshot())
                self.project = old_project

    def test_root_override_and_orphan_marker_block_writes(self):
        for name, text in (("AGENTS.override.md", "有效覆盖"), ("AGENTS.md", BEGIN)):
            path = self.project / name
            path.write_text(text)
            before = self.snapshot()
            self.assertNotEqual(self.run_cli(True).returncode, 0)
            self.assertEqual(before, self.snapshot())
            path.unlink()

    def test_symlink_does_not_write_outside_project(self):
        outside = self.base / "outside"
        outside.mkdir()
        (self.project / DIRECTORY).symlink_to(outside, target_is_directory=True)
        self.assertNotEqual(self.run_cli(True).returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])

    def test_changed_configuration_requires_explicit_upgrade(self):
        self.assertEqual(self.run_cli(True).returncode, 0)
        self.configuration.write_text(json.dumps(config({"fastapi": ["."]})))
        before = self.snapshot()
        self.assertNotEqual(self.run_cli(True).returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_interrupted_complete_output_still_reports_lock(self):
        self.assertEqual(self.run_cli(True).returncode, 0)
        (self.project / ".ai-dev-standards.lock").write_text("中断现场")
        before = self.snapshot()
        self.assertNotEqual(self.run_cli(True).returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_malformed_manifest_is_preserved(self):
        self.assertEqual(self.run_cli(True).returncode, 0)
        path = self.project / DIRECTORY / "manifest.json"
        data = json.loads(path.read_text())
        data["source"] = 42
        path.write_text(json.dumps(data))
        before = self.snapshot()
        result = self.run_cli(True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_invalid_scope_and_unknown_policy(self):
        for key, value in (
            ("stacks", {"react-vite": ["../"]}),
            ("stacks", {"unknown": ["."]}),
            ("commit_policy", "push"),
            ("schema_version", 2),
        ):
            data = config()
            data[key] = value
            self.configuration.write_text(json.dumps(data))
            self.assertNotEqual(self.run_cli(True).returncode, 0)
            self.assertEqual(list(self.project.iterdir()), [])

    def test_checks_are_recorded_without_execution(self):
        data = config()
        data["checks"] = [
            {"name": "合成检查", "cwd": ".", "argv": [sys.executable, "-c", "raise SystemExit(42)"]}
        ]
        self.configuration.write_text(json.dumps(data))
        self.assertEqual(self.run_cli(True).returncode, 0)
        saved = json.loads((self.project / DIRECTORY / "project.json").read_text())
        self.assertEqual(saved["checks"], data["checks"])

    def test_failed_entry_replace_restores_original(self):
        original = b"# keep original\n"
        (self.project / "AGENTS.md").write_bytes(original)
        files, block, source_id = render(ROOT, config())
        with (
            patch("bootstrap.storage.os.replace", side_effect=OSError("模拟写入失败")),
            self.assertRaises(OSError),
        ):
            apply(self.project, files, block, {"content_sha256": source_id}, original)
        self.assertEqual((self.project / "AGENTS.md").read_bytes(), original)
        self.assertEqual([p.name for p in self.project.iterdir()], ["AGENTS.md"])

    def test_concurrent_edit_and_lock_are_preserved(self):
        files, block, source_id = render(ROOT, config())
        (self.project / "AGENTS.md").write_text("后来修改")
        with self.assertRaises(BootstrapError):
            apply(self.project, files, block, {"content_sha256": source_id}, None)
        self.assertEqual((self.project / "AGENTS.md").read_text(), "后来修改")
        lock = self.project / ".ai-dev-standards.lock"
        lock.write_text("已有进程")
        self.assertNotEqual(self.run_cli(True).returncode, 0)
        self.assertEqual(lock.read_text(), "已有进程")


if __name__ == "__main__":
    unittest.main()
