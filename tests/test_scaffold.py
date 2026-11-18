"""在隔离目录验证新建工程、旧仓库保护及失败后的行为。"""

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
from bootstrap.model import BootstrapError
from lifecycle.model import bundle
from scaffold.catalog import MANIFEST
from scaffold.project import create, verify


class ScaffoldTests(unittest.TestCase):
    """覆盖独立 CLI 所依赖的创建、资源打包和检查边界。"""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.project = self.root / "试验工程"

    def create(self, template="react-fastapi", *, apply=True, existing=False):
        return create(ROOT, self.project, template, existing=existing, apply=apply, init_git=False)

    def test_preview_then_create_all_combinations_and_repeat(self):
        for template in ("react-fastapi", "react-vite", "react-nestjs"):
            with self.subTest(template=template):
                self.project = self.root / template
                preview, _ = self.create(template, apply=False)
                self.assertEqual(preview["status"], "preview")
                self.assertFalse(self.project.exists())
                completed, _ = self.create(template)
                self.assertEqual(completed["status"], "created")
                self.assertEqual(preview["files"], completed["files"])
                config = json.loads((self.project / ".ai-dev-standards/project.json").read_text())
                self.assertEqual(config["stacks"]["react-vite"], ["apps/web"])
                web = json.loads((self.project / "apps/web/starter.json").read_text())
                self.assertEqual(web["hasApi"], template != "react-vite")
                self.assertEqual((self.project / "apps/api").exists(), web["hasApi"])
                self.assertTrue(config["checks"])
                self.assertEqual(self.create(template)[0]["status"], "unchanged")

    def test_existing_planning_repo_keeps_index_readme_and_rules(self):
        self.project.mkdir()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        for name, data in (("README.md", b"# Plan\n"), ("AGENTS.md", b"# Rules\n")):
            (self.project / name).write_bytes(data)
        subprocess.run(["git", "-C", str(self.project), "add", "README.md"], check=True)
        index = (self.project / ".git/index").read_bytes()
        self.create(existing=True)
        self.assertEqual((self.project / "README.md").read_bytes(), b"# Plan\n")
        self.assertEqual((self.project / ".git/index").read_bytes(), index)
        self.assertIn(b"# Rules\n", (self.project / "AGENTS.md").read_bytes())
        self.assertTrue((self.project / "DEVELOPMENT.md").is_file())

    def test_existing_conflict_and_user_source_are_not_overwritten(self):
        self.project.mkdir()
        ignore = self.project / ".gitignore"
        ignore.write_text("custom\n")
        with self.assertRaises(BootstrapError):
            self.create(existing=True)
        self.assertEqual(ignore.read_text(), "custom\n")
        self.assertFalse((self.project / "apps").exists())
        ignore.unlink()
        self.create()
        file = self.project / "apps/web/src/main.tsx"
        file.write_text("user source\n")
        with self.assertRaises(BootstrapError):
            self.create()
        self.assertEqual(file.read_text(), "user source\n")

    def test_failed_rules_publish_rolls_back_only_new_files(self):
        self.project.mkdir()
        readme = self.project / "README.md"
        readme.write_text("原计划\n")
        with (
            patch("scaffold.project.apply_rules", side_effect=OSError("写入失败")),
            self.assertRaises(OSError),
        ):
            self.create(existing=True)
        self.assertEqual(list(self.project.iterdir()), [readme])
        self.assertEqual(self.create(existing=True)[0]["status"], "created")

    def test_verify_reports_failed_command_and_skips_later_commands(self):
        self.create("react-vite")
        path = self.project / ".ai-dev-standards/project.json"
        config = json.loads(path.read_text())
        config["checks"] = [
            {"name": "通过", "cwd": ".", "argv": [sys.executable, "-c", "pass"]},
            {"name": "失败", "cwd": ".", "argv": [sys.executable, "-c", "raise SystemExit(7)"]},
            {"name": "跳过", "cwd": ".", "argv": [sys.executable, "-c", "open('skipped', 'w')"]},
        ]
        path.write_text(json.dumps(config))
        self.assertFalse(verify(self.project, 15))
        self.assertFalse((self.project / "skipped").exists())

    def test_bundle_includes_only_explicit_template_resources(self):
        files, _ = bundle(ROOT)
        for path in (
            "scripts/ai-dev-standards",
            "templates/projects/shared/.gitignore",
            "templates/projects/react-vite/src/main.tsx",
            "templates/projects/react-vite/pnpm-lock.yaml",
            "templates/projects/fastapi/.env.example",
            "templates/projects/fastapi/uv.lock",
        ):
            self.assertIn(path, files)
        self.assertFalse(any("node_modules/" in name or "/.venv/" in name for name in files))
        self.assertNotIn(MANIFEST, files)


if __name__ == "__main__":
    unittest.main()
