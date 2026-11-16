"""验证项目采用配置并渲染仓库内规则；不执行项目检查命令。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

OWNER = "ai-dev-standards"
DIRECTORY = ".ai-dev-standards"
BEGIN = "<!-- AI-DEV-STANDARDS:BEGIN -->"
END = "<!-- AI-DEV-STANDARDS:END -->"
STACKS = {"react-vite": "frontend", "nestjs-fastify": "backend", "fastapi": "backend"}


class BootstrapError(Exception):
    """可向用户展示的配置、归属或文件冲突。"""


def digest(data: bytes) -> str:
    """计算内容指纹，用于追溯来源及检测手工修改。"""
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    """使用稳定格式，确保相同输入不会产生重复写入。"""
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def relative_path(value: object) -> str:
    """仅接受规范化项目相对路径，排除穿越、Windows 绝对路径和转义。"""
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise BootstrapError("路径必须是使用 / 的项目相对路径")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise BootstrapError(f"路径必须规范化且不能越出项目：{value}")
    return value


def validate_config(raw: object, project: Path) -> dict:
    """验证显式采用配置；路径必须存在，命令仅记录而不执行。"""
    project = project.resolve()
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version",
        "stacks",
        "checks",
        "deviations",
        "commit_policy",
    }:
        raise BootstrapError(
            "配置必须包含 schema_version、stacks、checks、deviations、commit_policy，不能有未知字段"
        )
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise BootstrapError("不支持的配置版本")
    stacks = raw["stacks"]
    if not isinstance(stacks, dict) or not stacks or not set(stacks) <= STACKS.keys():
        raise BootstrapError("stacks 至少选择 react-vite、nestjs-fastify、fastapi 之一")
    # 1. 范围明确为目录，避免生成一个看似精确、实际无法匹配的 glob 规则。
    for stack, scopes in stacks.items():
        if (
            not isinstance(scopes, list)
            or not scopes
            or any(not isinstance(s, str) for s in scopes)
            or len(scopes) != len(set(scopes))
        ):
            raise BootstrapError(f"{stack} 必须提供不重复的目录列表")
        for scope in scopes:
            scope = relative_path(scope)
            folder = project / scope
            if not folder.is_dir() or not folder.resolve().is_relative_to(project):
                raise BootstrapError(f"技术栈范围不存在或越出项目：{scope}")
    # 2. 检查命令是项目配置，不据此运行 shell，也不推断已经验证通过。
    checks = raw["checks"]
    if not isinstance(checks, list):
        raise BootstrapError("checks 必须是列表，可为空")
    for check in checks:
        if not isinstance(check, dict) or set(check) != {"name", "cwd", "argv"}:
            raise BootstrapError("每项检查必须包含 name、cwd、argv")
        if not isinstance(check["name"], str) or not check["name"].strip():
            raise BootstrapError("检查名称不能为空")
        folder = project / relative_path(check["cwd"])
        if not folder.is_dir() or not folder.resolve().is_relative_to(project):
            raise BootstrapError("检查目录不存在或越出项目")
        if (
            not isinstance(check["argv"], list)
            or not check["argv"]
            or any(
                not isinstance(arg, str) or not arg or "\x00" in arg or "\n" in arg or "\r" in arg
                for arg in check["argv"]
            )
        ):
            raise BootstrapError("argv 必须是非空参数数组，不能有空参数、换行或 NUL")
    # 3. 差异由项目所有者维护；拒绝未知策略，避免默认推送。
    if not isinstance(raw["deviations"], list) or any(
        not isinstance(x, str) or not x.strip() for x in raw["deviations"]
    ):
        raise BootstrapError("deviations 必须是非空说明组成的列表，可为空")
    if raw["commit_policy"] not in ("manual", "local"):
        raise BootstrapError("commit_policy 仅支持 manual 或 local；推送仍须单独授权")
    return raw


def markdown_text(text: str) -> str:
    """转义配置中的 Markdown 控制符，避免破坏采用说明的结构。"""
    return re.sub(r"([\\`*_{}\[\]<>#|])", r"\\\1", text).replace("\n", " ").replace("\r", " ")


def collect_standards(toolkit: Path, config: dict) -> dict[str, bytes]:
    """收集选定规范及本地链接依赖，保持离线副本中的相对链接有效。"""
    pending = ["common/engineering.md", "common/comments.md"]
    pending += [f"{STACKS[name]}/{name}.md" for name in sorted(config["stacks"])]
    result: dict[str, bytes] = {}
    root = (toolkit / "standards").resolve()
    while pending:
        name = pending.pop()
        if name in result:
            continue
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            raise BootstrapError(f"规范来源缺失或不在 standards 内：{name}")
        data = path.read_bytes()
        result[name] = data
        # 引用闭包只保留文档依赖；随附文档不会自动成为项目启用的技术栈。
        for href in re.findall(r"\[[^\]\n]+\]\(([^)\n]+)\)", data.decode()):
            url = urlsplit(href)
            if url.scheme or url.netloc or not url.path:
                continue
            dependency = (path.parent / unquote(url.path)).resolve()
            if not dependency.is_relative_to(root) or dependency.suffix != ".md":
                raise BootstrapError(f"规范引用越出 standards 或不是 Markdown：{name}")
            pending.append(dependency.relative_to(root).as_posix())
    return result


def render(toolkit: Path, config: dict) -> tuple[dict[str, bytes], bytes, str]:
    """生成选定规范、采用说明和受管入口；规范正文仅从权威来源复制。"""
    standards = collect_standards(toolkit, config)
    template = (toolkit / "templates/project-bootstrap/AGENTS.block.md").read_bytes()
    source_files = {"standards/" + name: digest(data) for name, data in standards.items()}
    source_files["templates/project-bootstrap/AGENTS.block.md"] = digest(template)
    source_id = digest(json_bytes(source_files))
    files = {"standards/" + name: data for name, data in standards.items()}
    files["project.json"] = json_bytes(config)
    rules = [
        f"- 所有修改必读 [通用工程规范]({DIRECTORY}/standards/common/engineering.md) 和 [中文注释规范]({DIRECTORY}/standards/common/comments.md)。"
    ]
    for name, scopes in sorted(config["stacks"].items()):
        scope_text = "、".join(markdown_text(s) for s in scopes)
        rules.append(
            f"- 修改 {scope_text} 下的 {name} 职责时，必读 [{name} 规范]({DIRECTORY}/standards/{STACKS[name]}/{name}.md)。"
        )
    block = template.decode().replace("{{reading_rules}}", "\n".join(rules)).encode()
    details = [
        "# 项目规范采用说明",
        "",
        "本文件由初始化工具生成。显式采用配置见 [project.json](project.json)，来源内容指纹与受管文件见 [manifest.json](manifest.json)。",
        "",
        "## 选定技术栈",
        "",
    ]
    for name, scopes in sorted(config["stacks"].items()):
        details.append(
            f"- [{name}](standards/{STACKS[name]}/{name}.md)："
            + "、".join(markdown_text(s) for s in scopes)
        )
    details += ["", "## 项目差异", ""]
    details += ["- " + markdown_text(d) for d in config["deviations"]] or [
        "当前未记录差异；已有项目约定仍需读取，不能据此认定不存在冲突。"
    ]
    details += [
        "",
        "## 检查清单",
        "",
        "命令由采用配置提供，仅表示已登记；初始化没有执行它们。按改动确定适用项，运行后记录真实结果。",
        "",
    ]
    for check in config["checks"]:
        details += [
            "- " + markdown_text(check["name"]) + "；工作目录：" + markdown_text(check["cwd"]),
            "",
            "    参数数组：" + markdown_text(json.dumps(check["argv"], ensure_ascii=False)),
            "",
        ]
    if not config["checks"]:
        details += ["尚未配置项目检查命令；这是验收缺口，开发时须补齐适用工具，不能声称检查通过。"]
    policy = (
        "验证通过后只提交本任务改动；默认不推送。"
        if config["commit_policy"] == "local"
        else "仅按用户明确指令提交；默认不推送。"
    )
    details += [
        "",
        "## 提交策略",
        "",
        policy,
        "当前明确指令优先于规范中的默认策略。",
        "",
        "## 来源与副本",
        "",
        f"规范及入口模板内容集合 SHA-256：{source_id}",
        "规范正文中的参考项目提交用于追溯提取依据；工具包来源信息见 manifest.json。",
        "随附规范可能包含为保持相对链接有效而带入的文档；只有上述选定技术栈默认适用。",
        "项目内容全部使用仓库内相对引用。工具包更新不自动改写本项目；手工修改后再次执行会检测差异并停止覆盖。",
        "",
    ]
    files["PROJECT.md"] = "\n".join(details).encode()
    return files, block, source_id
