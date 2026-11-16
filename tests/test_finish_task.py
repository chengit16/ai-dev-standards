"""临时 Git 仓库验证真实提交、索引保留、hook 失败及本地远程推送。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from finish.git import FinishError, Repository
from finish.push import push
from finish.task import finish, load_request


class FinishTests(unittest.TestCase):
    """全部身份、hook 与远程均限于测试仓库，不改使用者 Git 配置。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / "带 空格项目"
        self.project.mkdir()
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        environment = patch.dict(os.environ, self.env)
        environment.start()
        self.addCleanup(environment.stop)
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "收尾测试")
        self.git("config", "user.email", "test@example.invalid")
        for name in ("task.txt", "other.txt", "partial.txt"):
            (self.project / name).write_text("第一行\n第二行\n第三行\n")
        self.git("add", "--", "task.txt", "other.txt", "partial.txt")
        self.git("commit", "-qm", "chore: 建立测试仓库")
        self.initial = self.git("rev-parse", "HEAD")
        self.request = self.base / "request.json"
        self.data = {
            "schema_version": 1,
            "mode": "worktree",
            "paths": ["task.txt"],
            "message": "fix: 完成临时项目功能\n\n- 处理边界输入\n",
            "checks": [
                {
                    "name": "真实 Python 编译检查",
                    "cwd": ".",
                    "argv": [sys.executable, "-c", "compile('x = 1', 'check', 'exec')"],
                }
            ],
            "commit_policy": "local",
        }
        self.save()

    def git(self, *args):
        result = subprocess.run(
            ["git", "-C", str(self.project), *args],
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def save(self):
        self.request.write_text(json.dumps(self.data, ensure_ascii=False))

    def change(self, name="task.txt", text="本任务修改\n"):
        (self.project / name).write_text(text)

    def repo(self):
        return Repository(self.project)

    def preview(self):
        repo = self.repo()
        return finish(
            repo,
            load_request(self.request, repo),
            apply=False,
            check_only=False,
            expected_tree=None,
            expected_head=None,
            authorize_commit=False,
            timeout=5,
        )

    def execute(self, preview=None, authorize=False):
        plan = preview or self.preview()
        repo = self.repo()
        return finish(
            repo,
            load_request(self.request, repo),
            apply=True,
            check_only=False,
            expected_tree=plan["tree"],
            expected_head=plan["head"],
            authorize_commit=authorize,
            timeout=5,
        )

    def index(self):
        return (self.project / ".git/index").read_bytes()

    def hook(self, name, content):
        path = self.project / ".git/hooks" / name
        path.write_text("#!/bin/sh\n" + content)
        path.chmod(0o755)

    def remote(self):
        bare = self.base / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], env=self.env, check=True)
        self.git("remote", "add", "origin", str(bare))
        self.git("push", "-q", "origin", "HEAD:refs/heads/main")
        return bare

    def test_preview_and_no_changes_do_not_write(self):
        before = self.index()
        self.assertEqual(self.preview()["status"], "no_changes")
        self.change()
        self.assertEqual(self.preview()["status"], "preview")
        self.assertEqual(self.index(), before)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.initial)

    def test_local_commit_preserves_other_staged_and_unstaged_changes(self):
        self.change()
        self.change("other.txt", "其他人的暂存\n")
        self.git("add", "other.txt")
        staged = self.git("diff", "--cached", "--binary", "--", "other.txt")
        self.change("other.txt", "其他人的未暂存\n")
        unstaged = self.git("diff", "--binary", "--", "other.txt")
        result = self.execute()
        self.assertEqual(result["status"], "committed")
        self.assertEqual(self.git("show", "--format=", "--name-only", "HEAD"), "task.txt")
        self.assertEqual(self.git("diff", "--cached", "--binary", "--", "other.txt"), staged)
        self.assertEqual(self.git("diff", "--binary", "--", "other.txt"), unstaged)
        before_repeat = self.index()
        self.assertEqual(self.execute()["status"], "no_changes")
        self.assertEqual(self.index(), before_repeat)
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), "2")

    def test_index_mode_preserves_partial_staging(self):
        self.change(text="本任务已暂存\n第二行\n第三行\n")
        self.git("add", "task.txt")
        self.change(text="本任务已暂存\n第二行\n其他未暂存修改\n")
        self.data["mode"] = "index"
        self.save()
        unstaged = self.git("diff", "--binary", "--", "task.txt")
        self.execute()
        self.assertEqual(self.git("show", "HEAD:task.txt"), "本任务已暂存\n第二行\n第三行")
        self.assertEqual(self.git("diff", "--binary", "--", "task.txt"), unstaged)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")

    def test_worktree_rejects_partial_staging(self):
        self.change()
        self.git("add", "task.txt")
        self.change(text="又修改\n")
        before = self.index()
        with self.assertRaises(FinishError):
            self.preview()
        self.assertEqual(self.index(), before)

    def test_staged_delete_with_recreated_file_preserves_boundary(self):
        self.git("rm", "-q", "task.txt")
        self.change(text="暂存删除后的新内容\n")
        before = self.index()
        with self.assertRaises(FinishError):
            self.preview()
        self.assertEqual(self.index(), before)
        self.data["mode"] = "index"
        self.save()
        self.execute()
        self.assertEqual(self.git("ls-tree", "--name-only", "HEAD", "--", "task.txt"), "")
        self.assertEqual((self.project / "task.txt").read_text(), "暂存删除后的新内容\n")

    def test_check_failure_keeps_head_and_index(self):
        self.change()
        self.data["checks"][0]["argv"] = [sys.executable, "-c", "raise SystemExit(3)"]
        self.save()
        before = self.index()
        with self.assertRaises(FinishError):
            self.execute()
        self.assertEqual(self.index(), before)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.initial)

    def test_check_mutation_stops_commit_without_reverting_files(self):
        self.change()
        self.data["checks"][0]["argv"] = [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('task.txt').write_text('检查工具修改')",
        ]
        self.save()
        with self.assertRaises(FinishError):
            self.execute()
        self.assertEqual(self.git("rev-parse", "HEAD"), self.initial)
        self.assertEqual((self.project / "task.txt").read_text(), "检查工具修改")

    def test_manual_policy_requires_explicit_commit_authorization(self):
        self.change()
        self.data["commit_policy"] = "manual"
        self.save()
        with self.assertRaises(FinishError):
            self.execute()
        self.assertEqual(self.execute(authorize=True)["status"], "committed")

    def test_empty_checks_and_stale_review_stop_commit(self):
        self.change()
        plan = self.preview()
        self.change(text="审核后改动\n")
        with self.assertRaises(FinishError):
            self.execute(plan)
        self.data["checks"] = []
        self.save()
        with self.assertRaises(FinishError):
            self.execute()
        self.assertEqual(self.git("rev-parse", "HEAD"), self.initial)

    def test_hook_failure_keeps_real_index_exact(self):
        self.change()
        self.change("other.txt")
        self.git("add", "other.txt")
        before = self.index()
        self.hook("pre-commit", "exit 1\n")
        with self.assertRaises(FinishError):
            self.execute()
        self.assertEqual(self.git("rev-parse", "HEAD"), self.initial)
        self.assertEqual(self.index(), before)
        self.assertFalse((self.project / ".git/index.lock").exists())

    def test_hook_changes_candidate_records_sha_for_recovery(self):
        self.change()
        before = self.index()
        self.hook("pre-commit", "git add -- other.txt\n")
        self.change("other.txt", "钩子加入的内容\n")
        with self.assertRaises(FinishError):
            self.execute()
        self.assertNotEqual(self.git("rev-parse", "HEAD"), self.initial)
        self.assertEqual(self.index(), before)
        reports = list((self.project / ".git/ai-dev-standards").glob("*/report.json"))
        report = json.loads(reports[0].read_text())
        self.assertEqual(report["commit"], self.git("rev-parse", "HEAD"))
        self.assertEqual(report["status"], "committed_pending_index")

    def test_hook_worktree_change_reports_committed_needs_review(self):
        self.change()
        self.hook("post-commit", "printf '钩子修改\n' > task.txt\n")
        with self.assertRaises(FinishError):
            self.execute()
        self.assertNotEqual(self.git("rev-parse", "HEAD"), self.initial)
        report = next((self.project / ".git/ai-dev-standards").glob("*/report.json"))
        self.assertEqual(json.loads(report.read_text())["status"], "committed_needs_review")

    def test_index_publish_failure_reports_existing_commit(self):
        self.change()
        before = self.index()
        plan = self.preview()
        with (
            patch("finish.task.os.replace", side_effect=OSError("模拟索引发布失败")),
            self.assertRaises(FinishError) as caught,
        ):
            self.execute(plan)
        actual = self.git("rev-parse", "HEAD")
        self.assertNotEqual(actual, self.initial)
        self.assertIn(actual, str(caught.exception))
        self.assertEqual(self.index(), before)
        report = next((self.project / ".git/ai-dev-standards").glob("*/report.json"))
        self.assertEqual(json.loads(report.read_text())["status"], "committed_pending_index")

    def test_new_file_delete_and_rename(self):
        self.git("mv", "task.txt", "重命名.txt")
        self.change("新 文件.txt", "新文件\n")
        (self.project / "partial.txt").unlink()
        self.data["paths"] = ["task.txt", "重命名.txt", "新 文件.txt", "partial.txt"]
        self.save()
        self.execute()
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.git("show", "HEAD:新 文件.txt"), "新文件")

    def test_adopted_config_cannot_be_overridden(self):
        adopted = self.project / ".ai-dev-standards/project.json"
        adopted.parent.mkdir()
        adopted.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "stacks": {"fastapi": ["."]},
                    "checks": self.data["checks"],
                    "deviations": [],
                    "commit_policy": "manual",
                }
            )
        )
        with self.assertRaises(FinishError):
            load_request(self.request, self.repo())
        del self.data["checks"]
        del self.data["commit_policy"]
        self.save()
        self.assertEqual(load_request(self.request, self.repo())["commit_policy"], "manual")

    def test_invalid_paths_and_symlinks_stop_preview(self):
        for value in ("../other", ".", "task.txt\n", ".git/config"):
            self.data["paths"] = [value]
            self.save()
            with self.assertRaises(FinishError):
                self.preview()
        (self.project / "link").symlink_to(self.base)
        self.data["paths"] = ["link/outside.txt"]
        self.save()
        with self.assertRaises(FinishError):
            self.preview()

    def test_conflict_operation_detached_and_lock_stop(self):
        self.change()
        for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"):
            target = self.project / ".git" / marker
            target.write_text(self.initial)
            with self.assertRaises(FinishError):
                self.preview()
            target.unlink()
        self.git("checkout", "--detach", "-q")
        with self.assertRaises(FinishError):
            self.preview()
        self.git("checkout", "main", "-q")
        lock = self.project / ".git/index.lock"
        lock.write_text("用户已有锁")
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertEqual(lock.read_text(), "用户已有锁")

    def test_removed_directory_and_intent_to_add_are_not_file_scopes(self):
        folder = self.project / "nested"
        folder.mkdir()
        (folder / "one.txt").write_text("必须逐文件确认\n")
        self.git("add", "nested/one.txt")
        self.git("commit", "-qm", "chore: 建立嵌套文件")
        (folder / "one.txt").unlink()
        folder.rmdir()
        self.data["paths"] = ["nested"]
        self.save()
        with self.assertRaises(FinishError):
            self.preview()
        self.change("new.txt", "尚未暂存\n")
        self.git("add", "--intent-to-add", "new.txt")
        self.data.update(mode="index", paths=["new.txt"])
        self.save()
        before = self.index()
        with self.assertRaises(FinishError):
            self.preview()
        self.assertEqual(self.index(), before)

    def test_manual_check_only_runs_without_commit(self):
        self.change()
        self.data["commit_policy"] = "manual"
        self.save()
        before = self.index()
        repo = self.repo()
        result = finish(
            repo,
            load_request(self.request, repo),
            apply=False,
            check_only=True,
            expected_tree=None,
            expected_head=None,
            authorize_commit=False,
            timeout=5,
        )
        self.assertEqual(result["status"], "checked")
        self.assertEqual(result["checks"][0]["returncode"], 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.initial)
        self.assertEqual(self.index(), before)

    def test_check_timeout_never_reaches_commit(self):
        self.change()
        self.data["checks"][0]["argv"] = [sys.executable, "-c", "import time; time.sleep(5)"]
        self.save()
        plan = self.preview()
        repo = self.repo()
        before = self.index()
        with self.assertRaises(subprocess.TimeoutExpired):
            finish(
                repo,
                load_request(self.request, repo),
                apply=True,
                check_only=False,
                expected_tree=plan["tree"],
                expected_head=plan["head"],
                authorize_commit=False,
                timeout=1,
            )
        self.assertEqual(self.git("rev-parse", "HEAD"), self.initial)
        self.assertEqual(self.index(), before)

    def test_linked_worktree_uses_its_own_index(self):
        primary = self.project
        primary_index = self.index()
        linked = self.base / "linked"
        self.git("worktree", "add", "-q", "-b", "feature", str(linked))
        self.project = linked
        self.change()
        result = self.execute()
        self.assertEqual(result["status"], "committed")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertTrue(
            Path(result["report"]).is_relative_to((primary / ".git/worktrees").resolve())
        )
        self.project = primary
        self.assertEqual(self.index(), primary_index)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.initial)

    def test_push_preview_rejects_unapproved_history_and_retries_same_sha(self):
        bare = self.remote()
        self.change()
        commit = self.execute()["commit"]
        repo = self.repo()
        plan = push(repo, "origin", "main", commit, [], False)
        self.assertEqual(plan["pending_commits"], [commit])
        with self.assertRaises(FinishError):
            push(repo, "origin", "main", commit, [], True)
        hook = bare / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        with self.assertRaises(FinishError):
            push(repo, "origin", "main", commit, [commit], True)
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), "2")
        hook.unlink()
        self.assertEqual(push(repo, "origin", "main", commit, [commit], True)["status"], "pushed")
        self.assertEqual(push(repo, "origin", "main", commit, [], True)["status"], "already_synced")
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), "2")

    def test_push_divergence_and_unavailable_remote_stop(self):
        self.remote()
        self.change()
        self.execute()
        self.git("checkout", "-qb", "remote-change", self.initial)
        self.change("other.txt", "远程历史\n")
        self.git("add", "other.txt")
        self.git("commit", "-qm", "fix: 远程修改")
        self.git("push", "-q", "origin", "HEAD:main")
        self.git("checkout", "-q", "main")
        repo = self.repo()
        with self.assertRaises(FinishError):
            push(repo, "origin", "main", repo.head, [], False)
        self.git("remote", "set-url", "origin", str(self.base / "不存在.git"))
        with self.assertRaises(FinishError):
            push(self.repo(), "origin", "main", repo.head, [], True)

    def test_new_remote_branch_requires_all_ancestors(self):
        self.remote()
        self.change()
        commit = self.execute()["commit"]
        plan = push(self.repo(), "origin", "new", commit, [], False)
        self.assertEqual(plan["pending_commits"], [self.initial, commit])
        with self.assertRaises(FinishError):
            push(self.repo(), "origin", "new", commit, [commit], True)
        self.assertEqual(
            push(self.repo(), "origin", "new", commit, [self.initial, commit], True)["status"],
            "pushed",
        )

    def test_push_ignores_follow_tags_and_preserves_fetch_tracking(self):
        bare = self.remote()
        self.change()
        first = self.execute()["commit"]
        # 模拟另一端已收到上一提交，而本地 tracking ref 尚未更新。
        subprocess.run(
            [
                "git",
                "--git-dir",
                str(bare),
                "fetch",
                "-q",
                str(self.project),
                "HEAD:refs/heads/main",
            ],
            env=self.env,
            check=True,
        )
        self.change(text="第二次任务\n")
        second = self.execute()["commit"]
        self.assertNotEqual(first, second)
        self.git("config", "push.followTags", "true")
        self.git("tag", "-a", "must-stay-local", "-m", "本地标签")
        fetch_head = self.project / ".git/FETCH_HEAD"
        fetch_head.write_text("用户上次获取记录\n")
        tracked = self.git("rev-parse", "refs/remotes/origin/main")
        plan = push(self.repo(), "origin", "main", second, [], False)
        self.assertEqual(plan["pending_commits"], [second])
        self.assertEqual(self.git("rev-parse", "refs/remotes/origin/main"), tracked)
        self.assertEqual(fetch_head.read_text(), "用户上次获取记录\n")
        push(self.repo(), "origin", "main", second, [second], True)
        self.assertEqual(self.git("ls-remote", "--tags", "origin"), "")

    def test_cli_preview_is_read_only(self):
        self.change()
        before = self.index()
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/finish_task.py"),
                "task",
                "--project",
                str(self.project),
                "--request",
                str(self.request),
            ],
            capture_output=True,
            text=True,
            check=False,
            env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"status": "preview"', result.stdout)
        self.assertEqual(self.index(), before)


if __name__ == "__main__":
    unittest.main()
