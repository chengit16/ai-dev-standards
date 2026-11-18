"""从项目旧清单预览并显式升级规范，通过事务保留备份与恢复边界。"""

from __future__ import annotations

import difflib
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from lifecycle.model import node, plain_parents
from lifecycle.transaction import recover, transact

from .model import (
    BEGIN,
    DIRECTORY,
    END,
    OWNER,
    BootstrapError,
    digest,
    json_bytes,
    relative_path,
    render,
    validate_config,
)
from .storage import read_regular, source_version


@dataclass(frozen=True)
class ProjectLayout:
    """共享初始化锁，Git 项目的备份留在其 Git 元数据目录。"""

    project: Path
    backups: Path

    @property
    def lock(self) -> Path:
        return self.project / ".ai-dev-standards.lock"

    def targets(self) -> dict[str, Path]:
        return {
            "root": self.project / DIRECTORY,
            "agents": self.project / "AGENTS.md",
            "override": self.project / "AGENTS.override.md",
        }

    def identity(self) -> dict:
        return {"project": str(self.project)}

    @classmethod
    def create(cls, project: Path) -> ProjectLayout:
        """无 Git 的目录同样可升级，备份在项目根保留供人工核对。"""
        if not project.is_dir():
            raise BootstrapError("目标项目目录不存在")
        git = subprocess.run(
            ["git", "-C", str(project), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        parent = project
        if git.returncode == 0 and Path(git.stdout.strip()).resolve() == project:
            git_dir = subprocess.check_output(
                ["git", "-C", str(project), "rev-parse", "--absolute-git-dir"], text=True
            )
            parent = Path(git_dir.strip()).resolve()
        layout = cls(project, parent / ".ai-dev-standards-upgrade-backups")
        plain_parents(layout.backups)
        if layout.backups.is_symlink():
            raise BootstrapError("规范升级备份目录不能是符号链接")
        if project.stat().st_dev != parent.stat().st_dev:
            raise BootstrapError("项目与备份目录须位于同一文件系统")
        return layout


def old_manifest(root: Path, snapshot: dict) -> tuple[dict, dict[str, bytes]]:
    """核对旧版清单已登记内容，要求人工处理受管区内的本地修改。"""
    if snapshot["kind"] != "directory":
        raise BootstrapError("未找到已初始化的规范目录，请先使用 bootstrap")
    raw = read_regular(root / "manifest.json")
    if raw is None:
        raise BootstrapError("项目缺少规范来源清单")
    manifest = json.loads(raw)
    if (
        not isinstance(manifest, dict)
        or manifest.get("owner") != OWNER
        or type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1
        or not isinstance(manifest.get("files"), dict)
        or not isinstance(manifest.get("source"), dict)
        or not isinstance(manifest["source"].get("content_sha256"), str)
        or not {"project.json", "PROJECT.md"} <= manifest["files"].keys()
    ):
        raise BootstrapError("项目规范清单结构或归属不匹配")
    files = {}
    for name, checksum in manifest["files"].items():
        path = relative_path(name)
        if path not in {"project.json", "PROJECT.md"} and not (
            path.startswith("standards/") and path.endswith(".md")
        ):
            raise BootstrapError(f"清单包含未识别的受管文件：{path}")
        data = read_regular(root / path)
        if data is None or digest(data) != checksum:
            raise BootstrapError(f"受管文件已改动或缺失，请先保留并整理本地差异：{path}")
        files[path] = data
    return manifest, files


def replace_block(original: bytes | None, previous_hash: object, updated: bytes) -> bytes:
    """以旧清单校验标记区块，完整保留标记外的字节及换行。"""
    if original is None or original.count(BEGIN.encode()) != 1 or original.count(END.encode()) != 1:
        raise BootstrapError("AGENTS.md 受管区块缺失或重复")
    begin = original.index(BEGIN.encode())
    end = original.index(END.encode()) + len(END.encode())
    if begin >= end or digest(original[begin:end] + b"\n") != previous_hash:
        raise BootstrapError("AGENTS.md 受管区块已改动，请先保留并整理本地规则")
    return original[:begin] + updated.rstrip(b"\n") + original[end:]


def show_diff(before: dict[str, bytes], after: dict[str, bytes]) -> bool:
    """输出可审阅的正文差异，包括新增、移除和采用配置变化。"""
    changed = False
    for name in sorted(before.keys() | after.keys()):
        if before.get(name) == after.get(name):
            continue
        changed = True
        print(
            "".join(
                difflib.unified_diff(
                    before.get(name, b"").decode().splitlines(keepends=True),
                    after.get(name, b"").decode().splitlines(keepends=True),
                    fromfile=f"{name}（当前）",
                    tofile=f"{name}（目标）",
                )
            )
        )
    return changed


def upgrade(toolkit: Path, project: Path, configuration: Path | None, apply: bool) -> str:
    """保留原采用配置或采用显式输入，只更新确认归属的规范和入口。"""
    layout = ProjectLayout.create(project)
    if layout.lock.exists() or layout.lock.is_symlink():
        raise BootstrapError("项目规范锁已存在，请先核对中断记录")
    targets = layout.targets()
    expected = {name: node(path) for name, path in targets.items()}
    override = read_regular(targets["override"])
    if override and override.strip():
        raise BootstrapError("根目录的 AGENTS.override.md 会遮蔽受管入口")
    manifest, before = old_manifest(targets["root"], expected["root"])
    config = validate_config(
        json.loads(configuration.read_bytes() if configuration else before["project.json"]),
        project,
    )
    after, block, content_id = render(toolkit, config)
    original = read_regular(targets["agents"])
    merged = replace_block(original, manifest.get("agents_block_sha256"), block)
    for name in after.keys() - before.keys():
        candidate = targets["root"] / name
        plain_parents(candidate)
        if candidate.exists() or candidate.is_symlink():
            raise BootstrapError(f"新规范与项目自有文件冲突：{name}")
    left = {f"{DIRECTORY}/{name}": data for name, data in before.items()}
    right = {f"{DIRECTORY}/{name}": data for name, data in after.items()}
    left["AGENTS.md"], right["AGENTS.md"] = original, merged
    changed = show_diff(left, right)
    if not changed and manifest["source"]["content_sha256"] == content_id:
        print("项目规范已与目标一致。")
        return "unchanged"
    version = source_version(toolkit, content_id)
    print(f"当前来源：{json.dumps(manifest['source'], ensure_ascii=False)}")
    print(f"目标来源：{json.dumps(version, ensure_ascii=False)}")
    if not apply:
        print("预览完成，添加 --apply 可应用升级。")
        return "preview"
    with tempfile.TemporaryDirectory(prefix="ai-dev-project-upgrade-") as folder:
        stage = Path(folder).resolve()
        staged = stage / "root"
        # 快照包含项目自有文件；只替换旧清单拥有的条目，或新增已检查的路径。
        shutil.copytree(targets["root"], staged, symlinks=True)
        if node(staged) != expected["root"]:
            raise BootstrapError("复制期间规范目录发生变化，请重新预览")
        for name in before.keys() - after.keys():
            (staged / name).unlink()
        for name, data in after.items():
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (staged / "manifest.json").write_bytes(
            json_bytes(
                dict(
                    manifest,
                    source=version,
                    files={k: digest(v) for k, v in after.items()},
                    agents_block_sha256=digest(block),
                )
            )
        )
        (stage / "agents").write_bytes(merged)
        (stage / "agents").chmod(expected["agents"]["mode"])
        desired = dict(expected, root=node(staged), agents=node(stage / "agents"))
        transaction = transact(layout, "upgrade-rules", expected, desired, stage)
    print(f"已升级项目规范。备份：{transaction}")
    return "upgraded"


def recover_upgrade(project: Path, transaction: Path, apply: bool) -> dict:
    """复用既有事务恢复，限定在当前项目的升级备份。"""
    return recover(ProjectLayout.create(project), transaction, apply)
