"""使用临时用户目录验证完整生命周期，不读取真实配置作为测试夹具。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bootstrap.storage import source_version
from lifecycle.manager import doctor, manage
from lifecycle.model import BEGIN, InstallError, Layout
from lifecycle.transaction import publish, recover


class ToolkitTests(unittest.TestCase):
    """验证使用者内容保留、来源追溯和可操作恢复，命令只作用于合成目录。"""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.home = self.base / "用户目录"
        self.home.mkdir()
        self.source = self.base / "source"
        self.source.mkdir()
        for name in ("README.md", "AGENTS.md"):
            shutil.copy2(ROOT / name, self.source / name)
        for area in (
            "rules",
            "standards",
            "skills",
            "templates",
            "scripts",
            "docs",
            "versions",
            "tests",
        ):
            shutil.copytree(
                ROOT / area,
                self.source / area,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    ".ruff_cache",
                    "node_modules",
                    "dist",
                    ".venv",
                    ".mypy_cache",
                    ".pytest_cache",
                ),
            )
        self.layout = Layout.create(self.home)
        self.agents = self.layout.codex / "AGENTS.md"
        self.env = dict(
            os.environ,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            PYTHONDONTWRITEBYTECODE="1",
        )
        self.config = self.layout.codex / "config.toml"

    def install(self, apply=True, legacy=None):
        return manage(self.layout, self.source, "install", apply, legacy)

    def snapshot(self):
        result = {}
        for path in self.home.rglob("*"):
            if path.is_symlink():
                result[str(path)] = ("link", os.readlink(path), path.lstat().st_mtime_ns)
            elif path.is_file():
                result[str(path)] = ("file", path.read_bytes(), path.stat().st_mtime_ns)
        return result

    def seed(self, data=b"# My rules\r\nKeep existing conventions."):
        self.layout.codex.mkdir(parents=True, exist_ok=True)
        self.agents.write_bytes(data)
        self.config.write_text('model = "existing-model"\n')
        return data

    def test_preview_creates_no_user_files(self):
        self.assertEqual(self.install(False)["status"], "preview")
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(doctor(self.layout)["status"], "not_installed")
        self.assertEqual(list(self.home.iterdir()), [])

    def test_update_adds_root_license_and_notice_to_installed_bundle(self):
        self.install()
        declarations = {
            "LICENSE": b"fixture license\n",
            "NOTICE": b"fixture notice\n",
        }
        for name, data in declarations.items():
            (self.source / name).write_bytes(data)

        result = manage(self.layout, self.source, "update", True)
        self.assertEqual(result["status"], "deployed")
        for name, data in declarations.items():
            self.assertIn(f"bundle/{name}", result["changed_files"])
            self.assertEqual((self.layout.root / "bundle" / name).read_bytes(), data)
        self.assertEqual(doctor(self.layout)["status"], "deployed")
        self.assertEqual(manage(self.layout, self.source, "update", True)["status"], "unchanged")
        self.assertEqual(
            manage(self.layout, self.source, "uninstall", True)["status"], "uninstalled"
        )

    def test_install_preserves_original_rules_config_and_full_resources(self):
        original = self.seed()
        config = self.config.read_bytes()
        result = self.install()
        self.assertEqual(result["status"], "deployed")
        self.assertTrue(self.agents.read_bytes().startswith(original))
        self.assertEqual(self.config.read_bytes(), config)
        self.assertEqual(doctor(self.layout)["host_loading"], "not_verified")
        for name in ("project-bootstrap", "finish-task", "extract-standards", "git-commit-message"):
            link = self.layout.skills / name
            self.assertTrue(link.is_symlink())
            self.assertTrue((link / "SKILL.md").is_file())
            self.assertTrue((link / "../../scripts/toolkit.py").is_file())
        self.assertTrue((self.layout.root / "bundle/standards/common/comments.md").is_file())
        self.assertEqual((Path(result["backup"]) / "before/agents").read_bytes(), original)

    def test_legacy_two_skill_install_upgrades_without_claiming_user_skill(self):
        source = self.source / "skills/extract-standards/SKILL.md"
        new_skill = source.read_bytes()
        source.unlink()
        self.install()
        link = self.layout.skills / "extract-standards"
        self.assertFalse(link.exists())
        self.assertEqual(doctor(self.layout)["status"], "deployed")
        source.write_bytes(new_skill)
        link.mkdir()
        foreign = link / "SKILL.md"
        foreign.write_text("用户的同名 Skill\n")
        with self.assertRaises(InstallError):
            manage(self.layout, self.source, "update", True)
        self.assertEqual(foreign.read_text(), "用户的同名 Skill\n")
        self.assertEqual(doctor(self.layout)["status"], "deployed")
        foreign.unlink()
        link.rmdir()
        result = manage(self.layout, self.source, "update", True)
        self.assertIn("extract-standards", result["changes"])
        self.assertEqual((link / "SKILL.md").read_bytes(), new_skill)
        self.assertEqual(doctor(self.layout)["status"], "deployed")
        self.assertEqual(
            manage(self.layout, self.source, "uninstall", True)["status"], "uninstalled"
        )
        self.assertFalse(link.is_symlink())

    def test_repeat_keeps_bytes_mtimes_and_backups(self):
        self.install()
        before = self.snapshot()
        self.assertEqual(self.install()["status"], "unchanged")
        self.assertEqual(before, self.snapshot())
        self.assertEqual(len(list(self.layout.backups.glob("txn-*"))), 1)

    def test_update_preserves_new_user_rules_and_keeps_backup(self):
        self.seed()
        self.install()
        original = self.agents.read_bytes()
        self.agents.write_bytes("用户前言\n".encode() + original + "\n用户末尾\n".encode())
        before = self.agents.read_bytes()
        source_rules = self.source / "rules/global.md"
        source_rules.write_text(source_rules.read_text() + "\n- 新版规则示例。\n")
        with self.assertRaises(InstallError):
            self.install()
        preview = manage(self.layout, self.source, "update", False)
        self.assertEqual(preview["status"], "preview")
        self.assertEqual(self.agents.read_bytes(), before)
        result = manage(self.layout, self.source, "update", True)
        self.assertTrue(self.agents.read_text().startswith("用户前言\n"))
        self.assertTrue(self.agents.read_text().endswith("\n用户末尾\n"))
        self.assertIn("新版规则示例", self.agents.read_text())
        self.assertEqual((Path(result["backup"]) / "before/agents").read_bytes(), before)
        self.assertEqual(doctor(self.layout)["status"], "deployed")
        self.assertEqual(manage(self.layout, self.source, "update", True)["status"], "unchanged")

    def test_uninstall_preserves_later_edits_and_original_config(self):
        original = self.seed()
        self.install()
        self.agents.write_bytes(self.agents.read_bytes() + "用户后来追加\n".encode())
        self.config.write_text('model = "changed-by-user"\n')
        result = manage(self.layout, self.source, "uninstall", True)
        self.assertEqual(result["status"], "uninstalled")
        self.assertEqual(self.agents.read_bytes(), original + "用户后来追加\n".encode())
        self.assertIn("changed-by-user", self.config.read_text())
        self.assertFalse(self.layout.root.exists())
        self.assertFalse((self.layout.skills / "finish-task").is_symlink())
        self.assertTrue(Path(result["backup"]).is_dir())
        self.assertEqual(
            manage(self.layout, self.source, "uninstall", True)["status"], "not_installed"
        )

    def test_uninstall_restores_missing_vs_empty_original_entry(self):
        self.install()
        manage(self.layout, self.source, "uninstall", True)
        self.assertFalse(self.agents.exists())
        self.agents.write_bytes(b"")
        self.install()
        manage(self.layout, self.source, "uninstall", True)
        self.assertTrue(self.agents.exists())
        self.assertEqual(self.agents.read_bytes(), b"")

    def test_foreign_directory_and_skill_are_not_claimed(self):
        self.layout.root.mkdir(parents=True)
        (self.layout.root / "mine.txt").write_text("其他资料")
        before = self.snapshot()
        with self.assertRaises(InstallError):
            self.install()
        self.assertEqual(before, self.snapshot())
        shutil.rmtree(self.layout.root)
        skill = self.layout.skills / "project-bootstrap"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("用户自己的技能")
        before = self.snapshot()
        with self.assertRaises(InstallError):
            self.install()
        self.assertEqual(before, self.snapshot())

    def test_modified_resources_and_unknown_empty_directory_block_removal(self):
        self.install()
        target = self.layout.root / "bundle/rules/global.md"
        original = target.read_bytes()
        target.write_text("用户修改")
        before = self.snapshot()
        self.assertEqual(doctor(self.layout)["status"], "conflict")
        for action in ("update", "uninstall"):
            with self.assertRaises(InstallError):
                manage(self.layout, self.source, action, True)
            self.assertEqual(before, self.snapshot())
        target.write_bytes(original)
        (self.layout.root / "user-empty-folder").mkdir()
        with self.assertRaises(InstallError):
            manage(self.layout, self.source, "uninstall", True)

    def test_global_markers_and_replaced_skill_link_block_writes(self):
        self.install()
        original = self.agents.read_bytes()
        self.agents.write_text(self.agents.read_text().replace("AI 开发规范工具包", "用户修改", 1))
        with self.assertRaises(InstallError):
            manage(self.layout, self.source, "uninstall", True)
        self.agents.write_bytes(original + BEGIN.encode())
        with self.assertRaises(InstallError):
            self.install()
        self.agents.write_bytes(original)
        link = self.layout.skills / "finish-task"
        link.unlink()
        link.symlink_to(self.base)
        with self.assertRaises(InstallError):
            self.install()

    def test_override_disabled_skill_and_last_matching_configuration(self):
        self.seed()
        override = self.layout.codex / "AGENTS.override.md"
        override.write_text("用户覆盖规则")
        with self.assertRaises(InstallError):
            self.install()
        override.unlink()
        self.config.write_text('[[skills.config]]\nname = "finish-task"\nenabled = false\n')
        with self.assertRaises(InstallError):
            self.install()
        self.config.write_text(
            self.config.read_text() + '[[skills.config]]\nname = "finish-task"\nenabled = true\n'
        )
        self.assertEqual(self.install()["status"], "deployed")
        override.write_text("后加覆盖规则")
        self.assertEqual(doctor(self.layout)["status"], "conflict")
        self.assertEqual(
            manage(self.layout, self.source, "uninstall", True)["status"], "uninstalled"
        )
        self.assertEqual(override.read_text(), "后加覆盖规则")

    def test_personal_commit_skill_is_kept_only_after_explicit_choice(self):
        link = self.layout.skills / "git-commit-message"
        bundled = self.layout.root / "bundle/skills/git-commit-message/SKILL.md"
        for personal in (
            self.layout.codex / "skills/personal-commit/SKILL.md",
            link / "SKILL.md",
        ):
            with self.subTest(personal=personal):
                personal.parent.mkdir(parents=True)
                personal.write_text("---\nname: git-commit-message\n---\n用户原技能\n")
                before = personal.read_bytes()
                with self.assertRaisesRegex(InstallError, "--legacy-policy keep"):
                    self.install()
                self.assertEqual(self.install(legacy="keep")["status"], "deployed")
                self.assertEqual(self.install()["status"], "unchanged")
                report = doctor(self.layout)
                self.assertEqual(report["status"], "deployed")
                self.assertTrue(any(str(personal) in value for value in report["warnings"]))
                self.assertFalse(link.is_symlink())
                self.assertTrue(bundled.is_file())
                self.assertEqual(
                    manage(self.layout, self.source, "update", True)["status"], "unchanged"
                )
                manage(self.layout, self.source, "uninstall", True)
                self.assertEqual(personal.read_bytes(), before)
                personal.unlink()
                personal.parent.rmdir()

    def test_commit_skill_upgrades_old_manifest_with_or_without_personal_version(self):
        link = self.layout.skills / "git-commit-message"
        manifest = self.layout.root / "manifest.json"
        personal = self.layout.codex / "skills/git-commit-message/SKILL.md"
        previous_source = self.base / "previous-source"
        shutil.copytree(
            self.source, previous_source, ignore=shutil.ignore_patterns("git-commit-message")
        )
        for keep in (False, True):
            with self.subTest(keep=keep):
                if keep:
                    personal.parent.mkdir(parents=True)
                    personal.write_text("---\nname: git-commit-message\n---\n用户原技能\n")
                manage(self.layout, previous_source, "install", True, "keep" if keep else None)
                # 模拟旧发行版的清单格式及已记录的保留选择。
                state = json.loads(manifest.read_bytes())
                state["schema_version"] = 1
                del state["skill_links"]
                manifest.write_text(json.dumps(state))
                self.assertEqual(doctor(self.layout)["status"], "deployed")
                self.assertEqual(
                    manage(self.layout, self.source, "update", True)["status"], "deployed"
                )
                self.assertEqual(link.is_symlink(), not keep)
                self.assertEqual(doctor(self.layout)["status"], "deployed")
                manage(self.layout, self.source, "uninstall", True)
                self.assertFalse(link.is_symlink())
                self.assertEqual(personal.is_file(), keep)

    def test_update_can_switch_between_managed_and_personal_commit_skill(self):
        self.install()
        link = self.layout.skills / "git-commit-message"
        personal = self.layout.codex / "skills/git-commit-message/SKILL.md"
        personal.parent.mkdir(parents=True)
        personal.write_text("---\nname: git-commit-message\n---\n用户原技能\n")
        self.assertEqual(doctor(self.layout)["status"], "conflict")
        self.assertEqual(
            manage(self.layout, self.source, "update", True, "keep")["status"], "deployed"
        )
        self.assertFalse(link.is_symlink())
        self.assertEqual(personal.read_text(), "---\nname: git-commit-message\n---\n用户原技能\n")
        personal.unlink()
        self.assertEqual(manage(self.layout, self.source, "update", True)["status"], "deployed")
        self.assertTrue(link.is_symlink())

    def test_duplicate_declared_name_and_symlink_parent_rejected(self):
        duplicate = self.layout.codex / "skills/another-name/SKILL.md"
        duplicate.parent.mkdir(parents=True)
        duplicate.write_text("---\nname: finish-task\n---\n另一个入口\n")
        with self.assertRaises(InstallError):
            self.install()
        duplicate.unlink()
        (self.home / ".agents").symlink_to(self.base)
        with self.assertRaises(InstallError):
            self.install()

    def test_apply_failure_rolls_back_without_losing_original(self):
        original = self.seed()

        def fail_agents(target, stored, description, transaction):
            if target == self.agents and description["kind"] != "missing":
                raise OSError("模拟入口写入失败")
            return publish(target, stored, description, transaction)

        with (
            patch("lifecycle.transaction.publish", side_effect=fail_agents),
            self.assertRaises(OSError),
        ):
            self.install()
        self.assertEqual(self.agents.read_bytes(), original)
        self.assertFalse(self.layout.root.exists())
        self.assertFalse(self.layout.lock.exists())
        journal = next(self.layout.backups.glob("txn-*/journal.json"))
        self.assertEqual(json.loads(journal.read_text())["status"], "rolled_back")

    def crash_install(self):
        # 真子进程退出，保证 recover 验证的是已终止进程，而不是伪造活动锁。
        code = """
import os, sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from lifecycle.manager import manage
from lifecycle.model import Layout
from lifecycle.transaction import publish
layout = Layout.create(Path(sys.argv[2]))
def crash(target, stored, description, transaction):
    publish(target, stored, description, transaction)
    os._exit(91)
with patch("lifecycle.transaction.publish", side_effect=crash):
    manage(layout, Path(sys.argv[3]), "install", True)
"""
        result = subprocess.run(
            [sys.executable, "-c", code, str(ROOT / "scripts"), str(self.home), str(self.source)],
            env=self.env,
            check=False,
        )
        self.assertEqual(result.returncode, 91)
        return next(self.layout.backups.glob("txn-*"))

    def test_crash_is_diagnosed_and_recovery_rolls_back(self):
        original = self.seed()
        transaction = self.crash_install()
        self.assertTrue(self.layout.root.exists())
        report = doctor(self.layout)
        self.assertEqual(report["status"], "interrupted")
        self.assertIn(str(transaction), report["unfinished_transactions"])
        before = self.snapshot()
        self.assertEqual(recover(self.layout, transaction, False)["status"], "recovery_preview")
        self.assertEqual(before, self.snapshot())
        self.assertEqual(recover(self.layout, transaction, True)["status"], "recovered")
        self.assertEqual(self.agents.read_bytes(), original)
        self.assertFalse(self.layout.root.exists())
        self.assertFalse(self.layout.lock.exists())
        self.assertEqual(self.install()["status"], "deployed")

    def test_recovery_refuses_later_user_changes(self):
        transaction = self.crash_install()
        target = self.layout.root / "bundle/rules/global.md"
        target.write_text("中断后用户的新内容")
        with self.assertRaises(InstallError):
            recover(self.layout, transaction, True)
        self.assertEqual(target.read_text(), "中断后用户的新内容")
        self.assertTrue(self.layout.lock.exists())

    def test_active_lock_and_wrong_transaction_are_not_cleared(self):
        transaction = self.crash_install()
        lock = json.loads(self.layout.lock.read_text())
        lock["pid"] = os.getpid()
        self.layout.lock.write_text(json.dumps(lock))
        with self.assertRaises(InstallError):
            recover(self.layout, transaction, True)
        self.assertTrue(self.layout.lock.exists())
        with self.assertRaises(InstallError):
            self.install()

    def test_update_directory_swap_crash_restores_previous_version(self):
        self.seed()
        self.install()
        original = self.agents.read_bytes()
        old_source = doctor(self.layout)["source"]
        rules = self.source / "rules/global.md"
        rules.write_text(rules.read_text() + "\n- 更新中的内容。\n")
        code = """
import os, sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from lifecycle.manager import manage
from lifecycle.model import Layout
layout = Layout.create(Path(sys.argv[2]))
rename = os.rename
def crash(source, target):
    rename(source, target)
    if Path(source) == layout.root:
        os._exit(92)
with patch("lifecycle.transaction.os.rename", side_effect=crash):
    manage(layout, Path(sys.argv[3]), "update", True)
"""
        result = subprocess.run(
            [sys.executable, "-c", code, str(ROOT / "scripts"), str(self.home), str(self.source)],
            env=self.env,
            check=False,
        )
        self.assertEqual(result.returncode, 92)
        self.assertFalse(self.layout.root.exists())
        transaction = Path(doctor(self.layout)["unfinished_transactions"][0])
        recover(self.layout, transaction, True)
        self.assertEqual(self.agents.read_bytes(), original)
        self.assertEqual(doctor(self.layout)["source"], old_source)

    def test_uninstall_failure_restores_installation(self):
        self.install()
        original = self.agents.read_bytes()

        def fail_agents(target, stored, description, transaction):
            if target == self.agents:
                raise OSError("模拟卸载入口失败")
            return publish(target, stored, description, transaction)

        with (
            patch("lifecycle.transaction.publish", side_effect=fail_agents),
            self.assertRaises(OSError),
        ):
            manage(self.layout, self.source, "uninstall", True)
        self.assertEqual(self.agents.read_bytes(), original)
        self.assertEqual(doctor(self.layout)["status"], "deployed")

    def test_wrong_backup_transaction_cannot_clear_interrupted_lock(self):
        transaction = self.crash_install()
        other = self.layout.backups / "txn-unrelated"
        shutil.copytree(transaction, other)
        with self.assertRaises(InstallError):
            recover(self.layout, other, True)
        self.assertTrue(self.layout.lock.exists())
        self.assertTrue(self.layout.root.exists())

    def test_custom_codex_home_and_isolated_home_ignore_real_environment(self):
        with patch.dict(os.environ, {"CODEX_HOME": str(self.base / "must-not-be-used")}):
            self.assertEqual(Layout.create(self.home).codex, self.home / ".codex")
        custom = Layout.create(self.home, self.base / "custom-profile")
        manage(custom, self.source, "install", True)
        self.assertTrue((custom.codex / "AGENTS.md").exists())
        self.assertEqual(custom.skills, self.home / ".agents/skills")
        self.assertEqual(doctor(custom)["status"], "deployed")

    def test_installed_bootstrap_and_finish_run_without_source_checkout(self):
        self.install()
        installed = self.layout.root / "bundle"
        shutil.rmtree(self.source)
        project = self.base / "business"
        project.mkdir()
        (project / "calculator.py").write_text("def total(values):\n    return sum(values)\n")
        (project / "test_calculator.py").write_text(
            "import unittest\nfrom calculator import total\n\n"
            "class TotalTests(unittest.TestCase):\n"
            "    def test_values(self):\n        self.assertEqual(total([2, 3]), 5)\n"
        )
        (project / ".gitignore").write_text("__pycache__/\n")
        config = self.base / "project.json"
        config.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "stacks": {"fastapi": ["."]},
                    "checks": [
                        {
                            "name": "示例业务测试",
                            "cwd": ".",
                            "argv": [
                                sys.executable,
                                "-m",
                                "unittest",
                                "discover",
                                "-p",
                                "test_calculator.py",
                                "-v",
                            ],
                        }
                    ],
                    "deviations": [],
                    "commit_policy": "local",
                }
            )
        )
        environment = dict(self.env)
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        result = subprocess.run(
            [
                sys.executable,
                str(installed / "scripts/project_bootstrap.py"),
                "--project",
                str(project),
                "--config",
                str(config),
                "--apply",
            ],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        source = json.loads((project / ".ai-dev-standards/manifest.json").read_text())["source"]
        self.assertIn("installation_content_sha256", source)
        for args in (
            ["init", "-q", "--initial-branch=main"],
            ["config", "user.name", "安装链路测试"],
            ["config", "user.email", "test@example.invalid"],
            ["add", "."],
            ["commit", "-qm", "chore: 初始化示例"],
        ):
            subprocess.run(["git", "-C", str(project), *args], env=self.env, check=True)
        (project / "calculator.py").write_text("def total(values):\n    return sum(values or [])\n")
        tests = project / "test_calculator.py"
        tests.write_text(
            tests.read_text()
            + "\n    def test_none(self):\n        self.assertEqual(total(None), 0)\n"
        )
        request = self.base / "finish.json"
        request.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "mode": "worktree",
                    "paths": ["calculator.py", "test_calculator.py"],
                    "message": "fix: 支持空输入求和",
                }
            )
        )
        command = [
            sys.executable,
            str(installed / "scripts/finish_task.py"),
            "task",
            "--project",
            str(project),
            "--request",
            str(request),
        ]
        preview = subprocess.run(
            command, capture_output=True, text=True, env=environment, check=True
        )
        plan = json.loads(preview.stdout.splitlines()[0])
        completed = subprocess.run(
            command + ["--apply", "--expected-head", plan["head"], "--expected-tree", plan["tree"]],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Ran 2 tests", completed.stderr)
        committed = subprocess.check_output(
            ["git", "-C", str(project), "show", "--format=", "--name-only", "HEAD"],
            env=self.env,
            text=True,
        )
        self.assertEqual(set(committed.split()), {"calculator.py", "test_calculator.py"})
        result = subprocess.run(
            [sys.executable, str(installed / "scripts/finish_task.py"), "--help"],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(doctor(self.layout)["status"], "deployed")
        self.assertEqual(list(installed.rglob("__pycache__")), [])
        removed = subprocess.run(
            [
                sys.executable,
                str(installed / "scripts/toolkit.py"),
                "uninstall",
                "--home",
                str(self.home),
                "--apply",
            ],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertEqual(json.loads(removed.stdout)["status"], "uninstalled")
        self.assertFalse(self.layout.root.exists())

    def test_git_provenance_survives_installation(self):
        for args in (
            ["init", "-q", str(self.source)],
            ["-C", str(self.source), "config", "user.name", "安装测试"],
            ["-C", str(self.source), "config", "user.email", "test@example.invalid"],
            ["-C", str(self.source), "add", "."],
            ["-C", str(self.source), "commit", "-qm", "chore: 来源快照"],
        ):
            subprocess.run(["git", *args], env=self.env, check=True)
        sha = subprocess.check_output(
            ["git", "-C", str(self.source), "rev-parse", "HEAD"], env=self.env, text=True
        ).strip()
        self.install()
        state = json.loads((self.layout.root / "manifest.json").read_text())
        self.assertEqual(state["source"]["git_commit"], sha)
        self.assertFalse(state["source"]["working_tree_dirty"])
        installed_source = self.layout.root / "bundle"
        version = source_version(installed_source, "采用内容指纹")
        self.assertEqual(version["git_commit"], sha)
        self.assertFalse(version["working_tree_dirty"])
        (installed_source / "rules/global.md").write_text("安装后手工变更")
        self.assertTrue(source_version(installed_source, "采用内容指纹")["working_tree_dirty"])

    def test_cli_diagnostics_and_foreign_backups(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/toolkit.py"), "doctor", "--home", str(self.home)],
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "not_installed")
        self.layout.backups.mkdir(parents=True)
        (self.layout.backups / "private.txt").write_text("其他备份")
        with self.assertRaises(InstallError):
            self.install()
        self.assertFalse(self.layout.root.exists())
        self.assertFalse(self.layout.lock.exists())
        self.assertEqual((self.layout.backups / "private.txt").read_text(), "其他备份")


if __name__ == "__main__":
    unittest.main()
