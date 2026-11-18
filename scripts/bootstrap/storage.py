"""保存初始化结果，保护原有规则并检测重复执行与手工修改。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .model import (
    BEGIN,
    DIRECTORY,
    END,
    OWNER,
    BootstrapError,
    digest,
    json_bytes,
    relative_path,
)


def read_regular(path: Path) -> bytes | None:
    """只读取普通文件；拒绝符号链接和目录，避免跟随已有同名入口。"""
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise BootstrapError(f"目标不是普通文件：{path.name}")
    return path.read_bytes() if path.exists() else None


def check_tree(root: Path) -> None:
    """拒绝受管目录内的符号链接，后续比较不跨越项目边界。"""
    if root.is_symlink() or not root.is_dir():
        raise BootstrapError("受管路径不是普通目录")
    for folder, dirs, files in os.walk(root):
        for name in dirs + files:
            if (Path(folder) / name).is_symlink():
                raise BootstrapError("受管目录包含符号链接，不能自动处理")


def source_version(toolkit: Path, content_id: str, *, paths: list[str] | None = None) -> dict:
    """记录 Git 提交及快照指纹，支持未发布工作树而不伪称固定发行版。"""

    def git(*args: str) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(toolkit), *args], capture_output=True, text=True, check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None

    top = git("rev-parse", "--show-toplevel")
    if top is None or Path(top).resolve() != toolkit.resolve():
        # 安装副本没有 .git，使用安装时的内容清单追溯；手工修改必须标记为脏快照。
        stamp_path = toolkit / "_toolkit-source.json"
        if stamp_path.exists() or stamp_path.is_symlink():
            stamp = json.loads(read_regular(stamp_path))
            if (
                not isinstance(stamp, dict)
                or stamp.get("owner") != OWNER
                or stamp.get("schema_version") != 1
                or not isinstance(stamp.get("files"), dict)
                or not isinstance(stamp.get("source"), dict)
            ):
                raise BootstrapError("安装来源记录无效，请先运行 doctor")
            changed = False
            for name, expected in stamp["files"].items():
                path = toolkit / relative_path(name)
                if not path.resolve().is_relative_to(toolkit.resolve()):
                    raise BootstrapError("安装来源记录包含越界路径")
                data = read_regular(path)
                if data is None or digest(data) != expected:
                    changed = True
            source = stamp["source"]
            return {
                "repository": OWNER,
                "git_commit": source.get("git_commit"),
                "working_tree_dirty": True if changed else source.get("working_tree_dirty"),
                "content_sha256": content_id,
                "installation_content_sha256": source.get("content_sha256"),
            }
        return {
            "repository": OWNER,
            "git_commit": None,
            "working_tree_dirty": None,
            "content_sha256": content_id,
        }
    revision = git("rev-parse", "HEAD")
    dirty = git(
        "status",
        "--porcelain",
        "--",
        *(
            paths
            if paths is not None
            else [
                "standards",
                "templates/project-bootstrap",
                "scripts/bootstrap",
                "scripts/project_bootstrap.py",
            ]
        ),
    )
    return {
        "repository": OWNER,
        "git_commit": revision,
        "working_tree_dirty": bool(dirty) if dirty is not None else None,
        "content_sha256": content_id,
    }


def inspect(
    project: Path, files: dict[str, bytes], block: bytes, content_id: str
) -> tuple[bytes | None, bool]:
    """先完整核对冲突；已有结果必须内容一致，初始化不兼任隐式升级。"""
    lock = project / ".ai-dev-standards.lock"
    if lock.exists() or lock.is_symlink():
        raise BootstrapError("初始化锁已存在；确认无运行进程并检查中断现场后再继续")
    override = read_regular(project / "AGENTS.override.md")
    if override and override.strip():
        raise BootstrapError("根目录存在非空 AGENTS.override.md；请先确定有效入口，当前不写入")
    original = read_regular(project / "AGENTS.md")
    if original is not None:
        original.decode("utf-8")
    managed = project / DIRECTORY
    if not managed.exists() and not managed.is_symlink():
        if original and (BEGIN.encode() in original or END.encode() in original):
            raise BootstrapError("已有受管标记但没有来源记录，拒绝认领")
        return original, False
    # 1. 不凭目录名认领文件；清单缺失或不匹配时保留现场。
    check_tree(managed)
    try:
        manifest = json.loads((managed / "manifest.json").read_text())
    except (OSError, ValueError) as error:
        raise BootstrapError("受管目录缺少有效 manifest.json，可能是同名内容或中断结果") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("owner") != OWNER
        or type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != 1
    ):
        raise BootstrapError("受管目录不属于本工具包或清单版本不支持")
    hashes = {name: digest(data) for name, data in files.items()}
    if (
        manifest.get("files") != hashes
        or not isinstance(manifest.get("source"), dict)
        or manifest["source"].get("content_sha256") != content_id
    ):
        raise BootstrapError("配置或工具包来源已变化；需要显式升级或人工合并，初始化不会覆盖")
    # 2. 校验每个受管文件，不删除或接管清单外的项目资料。
    for name, data in files.items():
        if read_regular(managed / name) != data:
            raise BootstrapError(f"受管文件已被修改或丢失，保留现场：{name}")
    # 3. 只比较受管区块；用户可在区块前后继续维护自己的规则。
    if original is None or original.count(BEGIN.encode()) != 1 or original.count(END.encode()) != 1:
        raise BootstrapError("AGENTS.md 受管区块缺失或重复，保留现场")
    start = original.index(BEGIN.encode())
    stop = original.index(END.encode()) + len(END.encode())
    actual = original[start:stop]
    if actual != block.rstrip(b"\n") or manifest.get("agents_block_sha256") != digest(block):
        raise BootstrapError("AGENTS.md 受管区块已变化，保留现场")
    return original, True


def apply(
    project: Path, files: dict[str, bytes], block: bytes, source: dict, original: bytes | None
) -> None:
    """先暂存全部内容再发布；可捕获失败回滚，中断残留在下次明确报冲突。"""
    lock = project / ".ai-dev-standards.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise BootstrapError("初始化锁已存在；确认没有运行中的进程后检查中断现场") from error
    os.close(descriptor)
    managed = project / DIRECTORY
    try:
        with tempfile.TemporaryDirectory(
            prefix=".ai-dev-standards-stage-", dir=project
        ) as temporary:
            staging = Path(temporary)
            output = staging / "bundle"
            output.mkdir()
            # 1. 全部规范与来源先在临时目录生成，不在目标中留下半份文本。
            for name, data in files.items():
                target = output / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            manifest = {
                "owner": OWNER,
                "schema_version": 1,
                "source": source,
                "files": {name: digest(data) for name, data in files.items()},
                "agents_block_sha256": digest(block),
            }
            (output / "manifest.json").write_bytes(json_bytes(manifest))
            separator = b"" if not original else (b"\n" if original.endswith(b"\n") else b"\n\n")
            merged = (original or b"") + separator + block
            candidate = staging / "AGENTS.md"
            candidate.write_bytes(merged)
            if original is not None:
                candidate.chmod((project / "AGENTS.md").stat().st_mode & 0o777)
            # 2. 写入前再次比较入口与所有权；不覆盖检查期间出现的用户修改。
            if (
                read_regular(project / "AGENTS.md") != original
                or managed.exists()
                or managed.is_symlink()
            ):
                raise BootstrapError("检查后目标发生变化，请重新预览")
            override = read_regular(project / "AGENTS.override.md")
            if override and override.strip():
                raise BootstrapError("检查后出现覆盖入口，请重新预览")
            os.rename(output, managed)
            # 3. AGENTS 最后替换；失败时只撤销本次目录，原入口仍保留。
            try:
                os.replace(candidate, project / "AGENTS.md")
            except BaseException:
                shutil.rmtree(managed)
                raise
    finally:
        # 强制杀进程或掉电无法保证跨文件原子性；锁或孤立清单阻止静默重跑。
        lock.unlink(missing_ok=True)
