"""读取模板清单，并按组合生成文件、规范采用配置和安装计划。"""

from __future__ import annotations

import json
from pathlib import Path

from bootstrap.model import BootstrapError, digest, json_bytes, relative_path
from bootstrap.storage import source_version

CATALOG = "templates/projects/catalog.json"
MANIFEST = ".ai-dev-scaffold/manifest.json"
COMMAND = "scripts/ai-dev-standards"


def catalog_files(toolkit: Path) -> dict[str, bytes]:
    """清单同时约束创建与发布，避免复制依赖缓存或本机配置。"""
    root = toolkit / "templates/projects"
    listing = root / "catalog.json"
    if root.is_symlink() or listing.is_symlink():
        raise BootstrapError("模板清单必须是工具包内的普通文件")
    data = json.loads(listing.read_bytes())
    if data["schema_version"] != 1:
        raise BootstrapError("模板清单版本不受支持")
    resources = {CATALOG: listing.read_bytes()}
    for key, component in data["components"].items():
        for name in component["files"]:
            relative_path(name)
            candidate = root / relative_path(key) / name
            if (
                not candidate.is_file()
                or not candidate.resolve().is_relative_to(root.resolve())
                or candidate.is_symlink()
            ):
                raise BootstrapError(f"模板资源缺失或路径无效：{key}/{name}")
            resources[candidate.relative_to(toolkit).as_posix()] = candidate.read_bytes()
    return resources


def render(
    toolkit: Path, template: str, project_name: str, existing: bool
) -> tuple[dict[str, bytes], dict, list[dict]]:
    """渲染声明的模板文件，检查命令随采用配置统一提供给 M4 和验证器。"""
    resources = catalog_files(toolkit)
    catalog = json.loads(resources[CATALOG])
    if template not in catalog["templates"]:
        raise BootstrapError(f"未知模板：{template}")
    backend = catalog["templates"][template]["backend"]
    components = ["shared", "react-vite", *([backend] if backend else [])]
    files = {}
    stacks = {}
    checks = []
    installs = []
    instructions = {
        None: "本组合只启动前端。修改 API 配置前，请补充实际后端服务。",
        "fastapi": (
            "另开终端，在工程根目录启动 API。\n\n"
            "```bash\ncd apps/api\nuv sync --locked\n"
            "uv run --no-sync uvicorn app:create_app --factory --reload\n```"
        ),
        "nestjs-fastify": (
            "另开终端，在工程根目录启动 API。\n\n"
            "```bash\ncd apps/api\npnpm install --frozen-lockfile\npnpm dev\n```"
        ),
    }
    for key in components:
        component = catalog["components"][key]
        destination = relative_path(component["destination"])
        if key != "shared":
            stacks[key] = [destination]
            installs.append({"cwd": destination, "argv": component["install"]})
            checks.extend(
                {"name": f"{key} {' '.join(argv)}", "cwd": destination, "argv": argv}
                for argv in component["checks"]
            )
        for name in component["files"]:
            if name == "scripts/smoke.py" and not backend:
                continue
            data = resources[f"templates/projects/{key}/{name}"]
            if name == "README.md.in":
                name = "DEVELOPMENT.md" if existing else "README.md"
                if backend:
                    smoke = (
                        f"也可在根目录执行 `python3 scripts/smoke.py {template}`。"
                        "冒烟检查使用临时端口，需要先安装依赖并完成构建。"
                    )
                else:
                    smoke = ""
                data = (
                    data.decode()
                    .replace("{{project}}", project_name)
                    .replace("{{template}}", template)
                    .replace("{{api_instructions}}", instructions[backend])
                    .replace("{{smoke_instructions}}", smoke)
                    .encode()
                )
            if key == "react-vite" and name == "starter.json":
                data = json_bytes({"hasApi": bool(backend)})
            target = (Path(destination) / name).as_posix()
            if target in files:
                raise BootstrapError(f"模板重复输出：{target}")
            files[target] = data
    if backend:
        checks.append(
            {
                "name": "全栈连通与失联检查",
                "cwd": ".",
                "argv": ["python3", "scripts/smoke.py", template],
            }
        )
    hashes = {name: digest(data) for name, data in files.items()}
    fingerprint = digest(json_bytes({name: digest(data) for name, data in resources.items()}))
    source = source_version(
        toolkit, fingerprint, paths=["templates/projects", "scripts/scaffold", COMMAND]
    )
    files[MANIFEST] = json_bytes(
        {
            "schema_version": 1,
            "template": template,
            "parameters": {"project": project_name, "existing": existing},
            "source": source,
            "files": hashes,
        }
    )
    config = {
        "schema_version": 1,
        "stacks": stacks,
        "checks": checks,
        "deviations": [],
        "commit_policy": "local",
    }
    return files, config, installs
