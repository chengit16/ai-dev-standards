"""限定 Git 操作环境，避免路径解释、外部 diff 与继承索引干扰收尾范围。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from bootstrap.model import BootstrapError, relative_path


class FinishError(BootstrapError):
    """可报告且不应通过强制 Git 操作绕过的收尾阻碍。"""


class Repository:
    """仅在已有提交的仓库根目录收尾；支持普通仓库和 Git worktree。"""

    def __init__(self, root: Path):
        self.root = root.resolve()
        # 外部 GIT_INDEX_FILE/GIT_DIR 会改变操作对象，不能悄悄继承。
        if any(key in os.environ for key in ("GIT_INDEX_FILE", "GIT_DIR", "GIT_WORK_TREE")):
            raise FinishError("请先清除 GIT_INDEX_FILE、GIT_DIR、GIT_WORK_TREE 后再运行")
        self.env = dict(
            os.environ, GIT_LITERAL_PATHSPECS="1", GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0"
        )
        if Path(self.text("rev-parse", "--show-toplevel")).resolve() != self.root:
            raise FinishError("project 必须是 Git 仓库根目录")
        self.head = self.text("rev-parse", "--verify", "HEAD")
        self.branch = self.text("symbolic-ref", "--quiet", "--short", "HEAD")
        self.gitdir = Path(self.text("rev-parse", "--absolute-git-dir"))
        index = Path(self.text("rev-parse", "--git-path", "index"))
        self.index = index if index.is_absolute() else self.root / index
        if self.index.is_symlink():
            raise FinishError("不自动处理符号链接索引")
        if self.text("rev-parse", "--shared-index-path"):
            raise FinishError("暂不支持 split index；保留现场")
        sparse = self.run("config", "--bool", "core.sparseCheckout", check=False)
        if sparse.stdout.strip() == b"true":
            raise FinishError("暂不支持 sparse checkout；保留现场")
        self.ensure_idle()

    def run(
        self, *args: str, env: dict | None = None, data: bytes | None = None, check: bool = True
    ) -> subprocess.CompletedProcess:
        """参数数组直传 Git；保留原始错误用于诊断，不执行 shell。"""
        # 普通 git diff 会刷新 stat 缓存，单靠 OPTIONAL_LOCKS 不能保证原索引字节不变。
        # 命令级覆盖仅约束本工具读操作，不写入项目或用户的 Git 配置。
        result = subprocess.run(
            ["git", "-c", "diff.autoRefreshIndex=false", "-C", str(self.root), *args],
            env=env or self.env,
            input=data,
            capture_output=True,
            check=False,
        )
        if check and result.returncode:
            raise FinishError(result.stderr.decode(errors="replace").strip() or "Git 操作失败")
        return result

    def text(self, *args: str, env: dict | None = None) -> str:
        return self.run(*args, env=env).stdout.decode().strip()

    def ensure_idle(self) -> None:
        """未解决冲突及中间操作需要原工作流收尾，不能创建普通任务提交。"""
        for name in (
            "MERGE_HEAD",
            "CHERRY_PICK_HEAD",
            "REVERT_HEAD",
            "rebase-merge",
            "rebase-apply",
            "sequencer",
            "BISECT_LOG",
        ):
            path = Path(self.text("rev-parse", "--git-path", name))
            if (path if path.is_absolute() else self.root / path).exists():
                raise FinishError(f"存在未完成 Git 操作：{name}")
        if self.run("ls-files", "--unmerged", "-z").stdout:
            raise FinishError("存在未解决冲突")

    def index_bytes(self) -> bytes | None:
        """保留真实索引原字节，失败时无需 reset 或 stash 用户内容。"""
        return self.index.read_bytes() if self.index.exists() else None

    def entries(self, paths: list[str], env: dict | None = None) -> bytes:
        """输出精确文件项；删除文件可返回空项，重命名由两条路径表示。"""
        return self.run("ls-files", "--stage", "-z", "--", *paths, env=env).stdout

    def set_entries(self, paths: list[str], entries: bytes, env: dict) -> None:
        """仅替换选择路径，其他暂存文件及索引标志保持原状。"""
        self.run("update-index", "--force-remove", "--", *paths, env=env)
        if entries:
            self.run("update-index", "-z", "--index-info", data=entries, env=env)


def file_path(value: object) -> str:
    """使用精确文件路径，禁用目录、控制字符和 Git 路径语法的隐式扩张。"""
    try:
        result = relative_path(value)
    except BootstrapError as error:
        raise FinishError(str(error)) from error
    if result == "." or any(ord(char) < 32 or ord(char) == 127 for char in result):
        raise FinishError("paths 必须是无控制字符的精确文件路径")
    if any(part.lower() == ".git" for part in Path(result).parts):
        raise FinishError("不能把 Git 元数据纳入提交范围")
    return result
