"""核对安装归属、宿主配置与旧入口，生成预览后交给事务层写入。"""

from __future__ import annotations

import json
import tempfile
import tomllib
from pathlib import Path

from .model import (
    BEGIN,
    END,
    OWNER,
    SKILLS,
    InstallError,
    Layout,
    bundle,
    encoded,
    global_block,
    locate_block,
    node,
    regular,
    tree_files,
)
from .transaction import transact


def installed(layout: Layout) -> tuple[dict | None, bytes | None]:
    """仅认领完整清单和精确匹配的资源；清单外文件不被升级或卸载吞掉。"""
    agents = regular(layout.codex / "AGENTS.md")
    if agents is not None:
        agents.decode()
    root = node(layout.root)
    if root["kind"] == "missing":
        if agents and (BEGIN.encode() in agents or END.encode() in agents):
            raise InstallError("发现孤立全局区块，缺少安装清单，不能自动认领")
        if any(node(layout.skills / name)["kind"] != "missing" for name in SKILLS):
            raise InstallError("同名 Skill 已存在但没有安装清单，不能自动认领")
        return None, agents
    if root["kind"] != "directory":
        raise InstallError("同名安装路径不是受管目录")
    raw = regular(layout.root / "manifest.json")
    if raw is None:
        raise InstallError("同名目录没有安装清单，不能覆盖")
    state = json.loads(raw)
    if (
        not isinstance(state, dict)
        or state.get("owner") != OWNER
        or type(state.get("schema_version")) is not int
        or state["schema_version"] != 1
        or state.get("layout") != layout.identity()
        or not isinstance(state.get("files"), dict)
        or not isinstance(state.get("block"), str)
        or not state["block"].startswith(BEGIN + "\n")
        or not state["block"].endswith(END + "\n")
        or not isinstance(state.get("source"), dict)
        or type(state.get("agents_created")) is not bool
        or state.get("separator") not in ("", "\n", "\n\n")
        or state.get("legacy_policy") not in ("stop", "keep")
    ):
        raise InstallError("安装清单结构、归属或布局不匹配")
    actual = tree_files(layout.root)
    actual.pop("manifest.json", None)
    if actual != state["files"]:
        raise InstallError("安装副本被修改、缺失或新增文件；保留现场，先比较备份")
    if agents is None:
        raise InstallError("安装记录存在但全局入口已丢失")
    locate_block(agents, state["block"].encode())
    for name in SKILLS:
        expected = {"kind": "link", "target": str(layout.root / "bundle/skills" / name)}
        if node(layout.skills / name) != expected:
            raise InstallError(f"Skill 链接被修改或丢失：{name}")
    return state, agents


def host_issues(layout: Layout, legacy_policy: str) -> tuple[list[str], list[str]]:
    """只读检查所选用户布局；项目、管理员和插件层仍需新会话核实。"""
    errors, warnings = [], []
    override = regular(layout.codex / "AGENTS.override.md")
    if override and override.strip():
        errors.append("非空 AGENTS.override.md 会遮蔽受管全局入口")
    raw = regular(layout.codex / "config.toml")
    config = tomllib.loads(raw.decode()) if raw else {}
    entries = config.get("skills", {}).get("config", [])
    if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
        raise InstallError("config.toml 的 skills.config 结构无效")
    for name in SKILLS:
        enabled = True
        paths = {
            str(layout.skills / name / "SKILL.md"),
            str(layout.root / "bundle/skills" / name / "SKILL.md"),
        }
        for entry in entries:
            if entry.get("name") == name or entry.get("path") in paths:
                enabled = entry.get("enabled", True)
        if enabled is False:
            errors.append(f"config.toml 已禁用 Skill：{name}")
    # 旧路径只用于冲突探测，绝不自动修改使用者的 Skill 或配置。
    roots = {layout.skills, layout.codex / "skills", layout.home / ".codex/skills"}
    legacy = []
    for root in sorted(roots):
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            skill = entry / "SKILL.md"
            if not skill.is_file():
                continue
            text = skill.read_text()
            declared = next(
                (
                    line.partition(":")[2].strip().strip("'\"")
                    for line in text.splitlines()
                    if line.startswith("name:")
                ),
                entry.name,
            )
            if declared == "git-commit-message":
                legacy.append(str(skill))
            if declared in SKILLS and entry != layout.skills / declared:
                errors.append(f"其他用户目录有同名 Skill：{skill}")
    if legacy:
        message = "检测到旧 git-commit-message；" + "、".join(legacy)
        if legacy_policy == "keep":
            warnings.append(
                message + "；已明确保留，默认收尾使用 finish-task，旧入口仅明确点名时使用"
            )
        else:
            errors.append(message + "；确认保留时使用 --legacy-policy keep，不自动改写旧 Skill")
    return errors, warnings


def doctor(layout: Layout) -> dict:
    """部署校验与实际宿主加载分开报告，不能用文件存在冒充会话验证通过。"""
    layout.validate()
    problems, warnings = [], []
    state = None
    try:
        state, agents = installed(layout)
        errors, warnings = host_issues(layout, state["legacy_policy"] if state else "stop")
        problems.extend(errors)
        if agents and len(agents) > 32768:
            warnings.append("全局入口超过 32 KiB，请核对宿主实际加载预算和项目规则总量")
    except (InstallError, ValueError, OSError, AttributeError) as error:
        problems.append(str(error))
    interrupted = layout.lock.exists() or layout.lock.is_symlink()
    transactions = []
    if layout.backups.is_dir():
        for directory in sorted(layout.backups.glob("txn-*")):
            try:
                record = json.loads(regular(directory / "journal.json") or b"null")
                if isinstance(record, dict) and record.get("status") == "applying":
                    transactions.append(str(directory))
            except (InstallError, ValueError, OSError):
                problems.append("存在无法读取的事务记录，需要人工核对")
    if interrupted:
        problems.append("安装锁存在；确认进程退出后使用 recover 核对事务")
    if state and state.get("source", {}).get("working_tree_dirty"):
        warnings.append("当前部署来自未提交工作树快照，不等同于固定发行版")
    return {
        "status": "interrupted"
        if interrupted
        else ("conflict" if problems else ("deployed" if state else "not_installed")),
        "files_deployed": state is not None,
        "host_loading": "not_verified",
        "layout": layout.identity(),
        "problems": problems,
        "warnings": warnings,
        "unfinished_transactions": transactions,
        "source": state.get("source") if state else None,
    }


def prepare(layout: Layout, source: Path, action: str, legacy: str | None, stage: Path) -> dict:
    """生成与目标分离的完整结果；不接触用户配置即可展示变更范围。"""
    state, original = installed(layout)
    if action == "uninstall" and state is None:
        return {"status": "not_installed"}
    if action == "update" and state is None:
        raise InstallError("尚未安装，请先 install")
    policy = legacy or (state["legacy_policy"] if state else "stop")
    errors, warnings = host_issues(layout, policy)
    if action != "uninstall" and errors:
        raise InstallError("；".join(errors))
    expected = {key: node(path) for key, path in layout.targets().items()}
    if action == "uninstall":
        start, stop = locate_block(original, state["block"].encode())
        separator = state["separator"].encode()
        if separator and original[:start].endswith(separator):
            start -= len(separator)
        updated = original[:start] + original[stop:]
        if updated or not state["agents_created"]:
            (stage / "agents").write_bytes(updated)
            (stage / "agents").chmod(expected["agents"]["mode"])
        desired = {key: node(stage / key) for key in layout.targets()}
    else:
        files, version = bundle(source)
        block = global_block(source)
        if state:
            start, stop = locate_block(original, state["block"].encode())
            updated = original[:start] + block + original[stop:]
            separator, created = state["separator"], state["agents_created"]
        else:
            for name in SKILLS:
                if expected[name]["kind"] != "missing":
                    raise InstallError(f"Skill 目录同名内容不属于本工具包：{name}")
            separator = "" if not original else ("\n" if original.endswith(b"\n") else "\n\n")
            updated = (original or b"") + separator.encode() + block
            created = original is None
        for name, data in files.items():
            target = stage / "root/bundle" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            # 命令随整个安装目录受管，无需写入用户现有 PATH 目录。
            target.chmod(0o755 if name == "scripts/ai-dev-standards" else 0o644)
        manifest = {
            "owner": OWNER,
            "schema_version": 1,
            "layout": layout.identity(),
            "files": tree_files(stage / "root"),
            "source": version,
            "block": block.decode(),
            "separator": separator,
            "agents_created": created,
            "legacy_policy": policy,
        }
        (stage / "root/manifest.json").write_bytes(encoded(manifest))
        (stage / "root/manifest.json").chmod(0o644)
        (stage / "agents").write_bytes(updated)
        (stage / "agents").chmod(expected["agents"].get("mode", 0o644))
        for name in SKILLS:
            (stage / name).symlink_to(
                layout.root / "bundle/skills" / name, target_is_directory=True
            )
        desired = {key: node(stage / key) for key in layout.targets()}
        if action == "install" and state and expected != desired:
            raise InstallError("已安装内容与来源不同；请使用 update 显式更新")
    changes = [key for key in desired if expected[key] != desired[key]]
    previous_files = expected["root"].get("files", {})
    next_files = desired["root"].get("files", {})
    changed_files = [
        name
        for name in sorted(previous_files.keys() | next_files.keys())
        if previous_files.get(name) != next_files.get(name)
    ]
    return {
        "status": "preview" if changes else "unchanged",
        "operation": action,
        "changes": changes,
        "changed_files": changed_files,
        "source": manifest["source"] if action != "uninstall" else state["source"],
        "expected": expected,
        "desired": desired,
        "warnings": warnings,
        "layout": layout.identity(),
    }


def manage(
    layout: Layout, source: Path, action: str, apply: bool, legacy: str | None = None
) -> dict:
    layout.validate()
    if layout.lock.exists() or layout.lock.is_symlink():
        raise InstallError("安装锁存在；先 doctor，再核对运行进程与恢复记录")
    # 发布时不能自我覆盖；卸载仅读取现有清单，允许从已载入的安装副本执行。
    if action != "uninstall" and (
        layout.root.is_relative_to(source.resolve()) or source.resolve().is_relative_to(layout.root)
    ):
        raise InstallError("来源与安装目录不能互相嵌套；使用独立克隆副本执行安装或更新")
    with tempfile.TemporaryDirectory(prefix="toolkit-plan-") as temporary:
        # macOS 的系统临时目录可能经 /var 链接返回，内部路径先规范化再检查用户边界。
        stage = Path(temporary).resolve()
        plan = prepare(layout, source, action, legacy, stage)
        result = {key: value for key, value in plan.items() if key not in ("expected", "desired")}
        if not apply or plan["status"] != "preview":
            return result
        transaction = transact(layout, action, plan["expected"], plan["desired"], stage)
        return dict(
            result,
            status="uninstalled" if action == "uninstall" else "deployed",
            backup=str(transaction),
            host_loading="not_verified",
        )
