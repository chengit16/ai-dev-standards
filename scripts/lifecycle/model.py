"""定义受管布局与资源快照；所有路径归属判断在写入前完成。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

OWNER = "ai-dev-standards"
SKILLS = ("project-bootstrap", "finish-task")
BEGIN = "<!-- AI-DEV-STANDARDS:GLOBAL:BEGIN -->"
END = "<!-- AI-DEV-STANDARDS:GLOBAL:END -->"
STAMP = "_toolkit-source.json"


class InstallError(Exception):
    """保留用户现场、可直接报告的安装或恢复阻碍。"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def plain_parents(path: Path) -> None:
    """拒绝受管路径上的符号链接与非目录父级；输入根目录已解析为真实路径。"""
    for parent in path.parents:
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise InstallError(f"父目录不是普通目录：{parent}")


def regular(path: Path) -> bytes | None:
    plain_parents(path)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise InstallError(f"路径不是普通文件：{path}")
    return path.read_bytes() if path.exists() else None


def tree_files(root: Path) -> dict[str, dict]:
    """目录快照不跟随链接，不把未知文件默默忽略，以防更新或卸载删除用户内容。"""
    result = {}
    for folder, dirs, files in os.walk(root):
        for name in dirs + files:
            path = Path(folder) / name
            if path.is_symlink():
                raise InstallError(f"受管目录出现符号链接：{path}")
        for name in dirs:
            path = Path(folder) / name
            result[path.relative_to(root).as_posix() + "/"] = {
                "kind": "directory",
                "mode": stat.S_IMODE(path.stat().st_mode),
            }
        for name in files:
            path = Path(folder) / name
            if not stat.S_ISREG(path.stat().st_mode):
                raise InstallError(f"受管目录出现特殊文件：{path}")
            result[path.relative_to(root).as_posix()] = {
                "sha256": digest(path.read_bytes()),
                "mode": stat.S_IMODE(path.stat().st_mode),
            }
    return result


def node(path: Path) -> dict:
    """记录顶层链接本身；目录中的链接另行拒绝，恢复时不跨出所管理的资源。"""
    plain_parents(path)
    if path.is_symlink():
        return {"kind": "link", "target": os.readlink(path)}
    if not path.exists():
        return {"kind": "missing"}
    if path.is_file():
        return {
            "kind": "file",
            "sha256": digest(path.read_bytes()),
            "mode": stat.S_IMODE(path.stat().st_mode),
        }
    if path.is_dir():
        return {"kind": "directory", "files": tree_files(path)}
    raise InstallError(f"不支持的文件类型：{path}")


@dataclass(frozen=True)
class Layout:
    """home 隔离 Skill 发现目录，codex 独立支持 CODEX_HOME。"""

    home: Path
    codex: Path

    @classmethod
    def create(cls, home: Path | None = None, codex: Path | None = None) -> Layout:
        chosen = (home or Path.home()).expanduser().resolve()
        # --home 用于隔离验收，不能继续继承真实环境的 CODEX_HOME。
        default = (
            chosen / ".codex"
            if home is not None
            else Path(os.environ.get("CODEX_HOME", chosen / ".codex"))
        )
        return cls(chosen, (codex or default).expanduser().resolve())

    @property
    def root(self) -> Path:
        return self.codex / OWNER

    @property
    def skills(self) -> Path:
        return self.home / ".agents/skills"

    @property
    def lock(self) -> Path:
        return self.codex / ".ai-dev-standards.lock"

    @property
    def backups(self) -> Path:
        return self.codex / ".ai-dev-standards-backups"

    def targets(self) -> dict[str, Path]:
        return {
            "root": self.root,
            **{name: self.skills / name for name in SKILLS},
            "agents": self.codex / "AGENTS.md",
        }

    def identity(self) -> dict:
        return {"home": str(self.home), "codex_home": str(self.codex)}

    def validate(self) -> None:
        if not self.home.is_dir():
            raise InstallError("home 必须是已有目录")
        for path in [*self.targets().values(), self.lock, self.backups]:
            plain_parents(path)
        if self.backups.is_symlink():
            raise InstallError("备份目录不能是符号链接")


def bundle(source: Path) -> tuple[dict[str, bytes], dict]:
    """只发布明确目录中的源码资源，不复制本机配置、Git 数据或缓存。"""
    files = {}
    for name in ("README.md", "AGENTS.md"):
        data = regular(source / name)
        if data is None:
            raise InstallError(f"工具包缺少 {name}")
        files[name] = data
    # 正式发行和安装副本都要携带仓库授权声明；旧来源可继续更新。
    for name in ("LICENSE", "NOTICE"):
        data = regular(source / name)
        if data is not None:
            files[name] = data
    # M5 模板按精确清单打包，保留点文件、锁文件和各类源码。
    manifest = source / "templates/projects/catalog.json"
    if manifest.exists():
        from scaffold.catalog import COMMAND, catalog_files

        files.update(catalog_files(source))
        command = regular(source / COMMAND)
        if command is None:
            raise InstallError("工具包缺少统一命令入口")
        files[COMMAND] = command
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
        root = source / area
        if root.is_symlink() or not root.is_dir():
            raise InstallError(f"工具包目录无效：{area}")
        for folder, dirs, names in os.walk(root):
            dirs[:] = [
                x
                for x in dirs
                if x not in ("__pycache__", ".ruff_cache")
                and (Path(folder) / x) != source / "templates/projects"
            ]
            for name in dirs + names:
                if (Path(folder) / name).is_symlink():
                    raise InstallError("发布资源不能包含符号链接")
            for name in names:
                path = Path(folder) / name
                if path.suffix in (".md", ".py", ".json", ".yaml", ".toml"):
                    files[path.relative_to(source).as_posix()] = path.read_bytes()
    for required in (
        "rules/global.md",
        "scripts/project_bootstrap.py",
        "scripts/finish_task.py",
        "scripts/toolkit.py",
    ):
        if required not in files:
            raise InstallError(f"工具包资源不完整：{required}")
    hashes = {name: digest(data) for name, data in files.items()}

    def git(*args: str) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(source), *args], capture_output=True, text=True, check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None

    top = git("rev-parse", "--show-toplevel")
    own = top is not None and Path(top).resolve() == source.resolve()
    version = {
        "git_commit": git("rev-parse", "HEAD") if own else None,
        "working_tree_dirty": bool(git("status", "--porcelain")) if own else None,
        "content_sha256": digest(encoded(hashes)),
    }
    if not own and (source / STAMP).is_file():
        # 发行包展开后没有 Git 元数据，沿用已经校验的固定提交与来源。
        stamp = json.loads(regular(source / STAMP))
        if (
            stamp.get("owner") != OWNER
            or stamp.get("schema_version") != 1
            or stamp.get("files") != hashes
            or stamp.get("source", {}).get("content_sha256") != version["content_sha256"]
        ):
            raise InstallError("发行包资源与来源清单不一致")
        version = stamp["source"]
    # 安装副本无 .git；把完整来源快照随包保存，供项目初始化继续追溯。
    files[STAMP] = encoded(
        {"owner": OWNER, "schema_version": 1, "source": version, "files": hashes}
    )
    return files, version


def global_block(source: Path) -> bytes:
    data = regular(source / "rules/global.md")
    if data is None or BEGIN in data.decode() or END in data.decode():
        raise InstallError("全局规则来源缺失或含保留标记")
    return (BEGIN + "\n").encode() + data.rstrip() + ("\n" + END + "\n").encode()


def locate_block(original: bytes, block: bytes) -> tuple[int, int]:
    if original.count(BEGIN.encode()) != 1 or original.count(END.encode()) != 1:
        raise InstallError("全局受管区块缺失或重复，保留现场")
    start = original.index(BEGIN.encode())
    stop = start + len(block)
    if original[start:stop] != block:
        raise InstallError("全局受管区块被修改，保留现场")
    return start, stop
