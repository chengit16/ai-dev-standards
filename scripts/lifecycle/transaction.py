"""保存逐资源前后快照，以归属校验支撑失败回滚和显式中断恢复。"""

from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
import uuid
from pathlib import Path
from typing import Protocol

from .model import OWNER, InstallError, encoded, node, regular


class TransactionLayout(Protocol):
    """安装与项目规则升级各自限定事务可写资源和备份归属。"""

    @property
    def lock(self) -> Path: ...

    @property
    def backups(self) -> Path: ...

    def targets(self) -> dict[str, Path]: ...

    def identity(self) -> dict: ...


def save(path: Path, value: object) -> None:
    """日志用同目录临时文件原子替换，不留下可误读的半份 JSON。"""
    candidate = path.with_name(path.name + ".tmp")
    with candidate.open("wb") as handle:
        handle.write(encoded(value))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(candidate, path)


def copy_node(source: Path, destination: Path, description: dict) -> None:
    kind = description["kind"]
    if kind == "directory":
        shutil.copytree(source, destination)
    elif kind == "file":
        shutil.copy2(source, destination)
    elif kind == "link":
        destination.symlink_to(description["target"], target_is_directory=True)
    elif kind != "missing":
        raise InstallError("备份中包含未知资源类型")


def publish(target: Path, stored: Path, description: dict, transaction: Path) -> None:
    """资源级原子替换；非空目录先移入备份，间隙由 pending 记录识别。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    current = node(target)
    if current["kind"] == "directory":
        retired = transaction / "retired"
        retired.mkdir(exist_ok=True)
        os.rename(target, retired / uuid.uuid4().hex)
    if description["kind"] == "missing":
        if target.is_symlink() or target.exists():
            target.unlink()
        return
    # 链接可能位于另一个文件系统，临时资源必须与最终目标同目录。
    staging = Path(tempfile.mkdtemp(prefix=".ai-dev-standards-publish-", dir=target.parent))
    try:
        candidate = staging / "resource"
        copy_node(stored, candidate, description)
        os.replace(candidate, target)
    finally:
        shutil.rmtree(staging)


def read_journal(layout: TransactionLayout, transaction: Path) -> dict:
    if (
        transaction.parent != layout.backups
        or not transaction.name.startswith("txn-")
        or transaction.is_symlink()
    ):
        raise InstallError("恢复目标必须是本布局下的事务目录")
    data = regular(transaction / "journal.json")
    if data is None:
        raise InstallError("事务日志不存在")
    journal = json.loads(data)
    if (
        not isinstance(journal, dict)
        or journal.get("owner") != OWNER
        or journal.get("schema_version") != 1
        or journal.get("layout") != layout.identity()
        or not isinstance(journal.get("actions"), dict)
        or not set(journal["actions"]) <= layout.targets().keys()
        or not isinstance(journal.get("touched"), list)
        or any(key not in journal["actions"] for key in journal["touched"])
    ):
        raise InstallError("事务归属、布局或结构不匹配")
    return journal


def rollback(layout: TransactionLayout, transaction: Path, journal: dict) -> None:
    """先完整核对后续修改，再恢复；不能用过时备份覆盖用户的新内容。"""
    targets = layout.targets()
    for key in journal["touched"]:
        entry = journal["actions"][key]
        if node(transaction / "before" / key) != entry["before"]:
            raise InstallError("恢复备份已变化，停止回滚")
        current = node(targets[key])
        gap = (
            key == "root"
            and key in (journal.get("pending"), journal.get("rollback_pending"))
            and current["kind"] == "missing"
        )
        if current not in (entry["before"], entry["after"]) and not gap:
            raise InstallError(f"恢复前发现后续修改，保留现场：{key}")
    for key in reversed(journal["touched"]):
        before = journal["actions"][key]["before"]
        if node(targets[key]) != before:
            journal["rollback_pending"] = key
            save(transaction / "journal.json", journal)
            publish(targets[key], transaction / "before" / key, before, transaction)
    journal.update(status="rolled_back", pending=None, rollback_pending=None)
    save(transaction / "journal.json", journal)


def transact(
    layout: TransactionLayout, action: str, expected: dict, desired: dict, staging: Path
) -> Path:
    """apply 唯一写入口；异常可回滚，无法确认完成时保留锁和日志。"""
    layout.lock.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(layout.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    settled = False
    transaction = None
    journal = None
    try:
        lock_record = {
            "owner": OWNER,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "transaction": None,
        }
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded(lock_record))
        marker = layout.backups / "owner.json"
        if layout.backups.exists():
            data = regular(marker)
            if data is None or json.loads(data) != {"owner": OWNER, "schema_version": 1}:
                raise InstallError("同名备份目录无有效归属记录")
        else:
            layout.backups.mkdir(mode=0o700)
            save(marker, {"owner": OWNER, "schema_version": 1})
        for key, description in expected.items():
            if node(layout.targets()[key]) != description:
                raise InstallError("预览后目标发生变化，请重新检查")
        transaction = Path(tempfile.mkdtemp(prefix="txn-", dir=layout.backups))
        lock_record["transaction"] = transaction.name
        save(layout.lock, lock_record)
        (transaction / "before").mkdir()
        (transaction / "after").mkdir()
        actions = {}
        for key, after in desired.items():
            if expected[key] == after:
                continue
            copy_node(layout.targets()[key], transaction / "before" / key, expected[key])
            copy_node(staging / key, transaction / "after" / key, after)
            if (
                node(transaction / "before" / key) != expected[key]
                or node(transaction / "after" / key) != after
            ):
                raise InstallError("备份或待发布快照与预览不一致，停止写入")
            actions[key] = {"before": expected[key], "after": after}
        journal = {
            "owner": OWNER,
            "schema_version": 1,
            "layout": layout.identity(),
            "operation": action,
            "status": "applying",
            "actions": actions,
            "touched": [],
            "pending": None,
        }
        save(transaction / "journal.json", journal)
        for key, entry in actions.items():
            if node(layout.targets()[key]) != entry["before"]:
                raise InstallError(f"写入前目标发生变化：{key}")
            journal["touched"].append(key)
            journal["pending"] = key
            save(transaction / "journal.json", journal)
            publish(layout.targets()[key], transaction / "after" / key, entry["after"], transaction)
            journal["pending"] = None
            save(transaction / "journal.json", journal)
        if any(node(layout.targets()[key]) != value for key, value in desired.items()):
            raise InstallError("写入后的资源核对失败")
        journal["status"] = "complete"
        save(transaction / "journal.json", journal)
        settled = True
        return transaction
    except Exception as error:
        if journal is not None:
            try:
                rollback(layout, transaction, journal)
            except (InstallError, OSError, ValueError, KeyError, TypeError) as recovery_error:
                raise InstallError(
                    f"操作失败且恢复受阻：{recovery_error}；保留锁与事务 {transaction}"
                ) from error
        settled = True
        raise
    finally:
        if settled:
            layout.lock.unlink(missing_ok=True)


def recover(layout: TransactionLayout, transaction: Path, apply: bool) -> dict:
    """以系统文件锁串行化恢复，进程异常退出后锁自动释放，不新增二次残留锁。"""
    if not layout.lock.exists() or layout.lock.is_symlink():
        return recover_locked(layout, transaction, apply)
    try:
        import fcntl
    except ImportError as error:
        raise InstallError("当前显式恢复依赖 POSIX 文件锁；本平台尚未支持，请保留现场") from error
    with layout.lock.open("rb") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise InstallError("另一个恢复进程正在操作，保留现场") from error
        return recover_locked(layout, transaction, apply)


def recover_locked(layout: TransactionLayout, transaction: Path, apply: bool) -> dict:
    """恢复只回滚未完成事务；活动进程与无法归属的锁不能自动删除。"""
    journal = read_journal(layout, transaction)
    if journal["status"] not in ("applying", "complete", "rolled_back"):
        raise InstallError("不支持的事务状态")
    lock_data = regular(layout.lock)
    if lock_data is None:
        if journal["status"] in ("complete", "rolled_back"):
            return {"status": "no_recovery_needed"}
        raise InstallError("未完成事务缺少锁，无法确认现场；请人工核对")
    lock = json.loads(lock_data)
    if (
        lock.get("owner") != OWNER
        or lock.get("host") != socket.gethostname()
        or type(lock.get("pid")) is not int
        or lock["pid"] <= 0
        or lock.get("transaction") != transaction.name
    ):
        raise InstallError("不能确认锁的归属或所在主机")
    try:
        os.kill(lock["pid"], 0)
    except ProcessLookupError:
        pass
    except PermissionError as error:
        raise InstallError("无法确认锁进程已退出") from error
    else:
        raise InstallError("锁记录的进程仍在运行；不执行恢复")
    result = {
        "status": "recovery_preview",
        "transaction": str(transaction),
        "operation": journal["operation"],
    }
    if not apply:
        return result
    if journal["status"] == "applying":
        rollback(layout, transaction, journal)
    else:
        # 完成日志写入后进程可能中断，确认终态资源仍一致才清理残留锁。
        side = "after" if journal["status"] == "complete" else "before"
        for key, entry in journal["actions"].items():
            if node(layout.targets()[key]) != entry[side]:
                raise InstallError("终态后资源发生变化，保留锁供人工核查")
    layout.lock.unlink()
    return dict(result, status="recovered")
