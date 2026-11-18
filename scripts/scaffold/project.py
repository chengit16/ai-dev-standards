"""生成项目，复用 M3 处理规范，并从同一采用配置运行真实检查。"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import tempfile
from pathlib import Path

from bootstrap.model import DIRECTORY, BootstrapError, digest, validate_config
from bootstrap.model import render as render_rules
from bootstrap.storage import apply as apply_rules
from bootstrap.storage import inspect, read_regular, source_version
from lifecycle.model import plain_parents

from .catalog import MANIFEST, render

PLANNING = {
    ".git",
    ".gitignore",
    ".DS_Store",
    "README.md",
    "docs",
    "AGENTS.md",
    "AGENTS.override.md",
}


def create(
    toolkit: Path,
    project: Path,
    template: str,
    *,
    existing: bool,
    apply: bool,
    init_git: bool,
) -> tuple[dict, list[dict]]:
    """预检全部输出；仅写入足够确定的目标，原有规则由 M3 负责。"""
    plain_parents(project)
    if project.is_symlink() or (project.exists() and not project.is_dir()):
        raise BootstrapError("目标必须是普通目录")
    if project == toolkit or project.is_relative_to(toolkit) or toolkit.is_relative_to(project):
        raise BootstrapError("业务工程须位于工具包以外")
    if not project.parent.is_dir():
        raise BootstrapError("目标父目录必须已存在")
    if not re.fullmatch(r"\w[\w .-]{0,79}", project.name):
        raise BootstrapError("项目目录名须以字母、数字或下划线开头，可包含空格、点和连字符")
    marker = project / ".ai-dev-scaffold.lock"
    if marker.exists() or marker.is_symlink():
        raise BootstrapError("创建锁已存在，请检查中断现场")
    plain_parents(project / MANIFEST)
    files, config, installs = render(toolkit, template, project.name, existing)
    # 来源提交变化不影响已有文件比对，保留首次生成所记录的原始来源。
    record = read_regular(project / MANIFEST) if project.exists() else None
    if record is not None:
        before = json.loads(record)
        planned = json.loads(files[MANIFEST])
        if not isinstance(before, dict) or any(
            before.get(key) != planned[key]
            for key in ("schema_version", "template", "parameters", "files")
        ):
            raise BootstrapError("创建清单不匹配，保留现有工程")
        all_same = True
    else:
        all_same = False
        names = {item.name for item in project.iterdir()} if project.exists() else set()
        if names and (not existing or names - PLANNING):
            raise BootstrapError("目标已有内容，只有规划目录可用 --existing 接入")
    rules, block, identity = render_rules(toolkit, config)
    original, adopted = inspect(project, rules, block, identity)
    for name, data in files.items():
        path = project / name
        plain_parents(path)
        current = read_regular(path)
        if name == MANIFEST and all_same:
            continue
        if (all_same and data != current) or (not all_same and current is not None):
            raise BootstrapError(f"文件冲突或已改动：{name}")
    if all_same and not adopted:
        raise BootstrapError("已有创建清单但规范尚未完成；请检查中断现场")
    if adopted and not all_same:
        raise BootstrapError("目标已采用规范，工程创建不会接管已有初始化")
    if init_git:
        repo = subprocess.run(
            [
                "git",
                "-C",
                str(project if project.is_dir() else project.parent),
                "rev-parse",
                "--show-toplevel",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if repo.returncode == 0:
            if not all_same or Path(repo.stdout.strip()).resolve() != project:
                raise BootstrapError("目标已位于 Git 仓库内，无需另行初始化")
            init_git = False
    report = {
        "status": "unchanged" if all_same else ("created" if apply else "preview"),
        "project": str(project),
        "template": template,
        "files": sorted(
            [
                *files,
                "AGENTS.md",
                f"{DIRECTORY}/manifest.json",
                *(f"{DIRECTORY}/{name}" for name in rules),
            ]
        ),
        "git_init": init_git,
        "source": json.loads(record or files[MANIFEST])["source"],
    }
    if apply and not all_same:
        publish(toolkit, project, files, config, rules, block, identity, original)
    if apply and init_git:
        # 创建完成后才初始化 Git。失败时工程仍可检查，随后可独立重试 git init。
        subprocess.run(["git", "init", str(project)], check=True)
    return report, installs


def publish(
    toolkit: Path,
    project: Path,
    files: dict[str, bytes],
    config: dict,
    rules: dict[str, bytes],
    block: bytes,
    identity: str,
    original: bytes | None,
) -> None:
    """同目录临时副本确保文件完整，硬链接发布拒绝覆盖期间出现的文件。"""
    version = source_version(toolkit, identity)
    project.mkdir(exist_ok=True)
    lock = project / ".ai-dev-scaffold.lock"
    created = []
    directories = []
    with lock.open("x") as handle:
        handle.write(f"pid={os.getpid()}\n")
    try:
        with tempfile.TemporaryDirectory(
            prefix=".ai-dev-scaffold-stage-", dir=project
        ) as temporary:
            stage = Path(temporary)
            lock.write_text(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "stage": stage.name,
                        "files_sha256": {name: digest(data) for name, data in files.items()},
                    },
                    ensure_ascii=False,
                )
            )
            for name, data in files.items():
                candidate = stage / name
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_bytes(data)
            try:
                # 清单最后发布，出现中断时锁或孤立文件阻止悄悄覆盖。
                for name in sorted(files, key=lambda name: name == MANIFEST):
                    target = project / name
                    for parent in reversed(target.parents):
                        if parent != project and parent.is_relative_to(project):
                            plain_parents(parent)
                            if parent.is_symlink():
                                raise BootstrapError(f"输出路径指向链接：{parent.name}")
                            if not parent.exists():
                                parent.mkdir()
                                directories.append(parent)
                    candidate = stage / name
                    os.link(candidate, target)
                    created.append((candidate, target))
                validate_config(config, project)
                apply_rules(project, rules, block, version, original)
            except BaseException:
                for candidate, target in reversed(created):
                    # 同目录链接共享内容，比较计划字节可保留发布后用户写入的内容。
                    if (
                        not target.is_symlink()
                        and target.exists()
                        and candidate.samefile(target)
                        and target.read_bytes() == files[target.relative_to(project).as_posix()]
                    ):
                        target.unlink()
                for directory in reversed(directories):
                    if (
                        not directory.is_symlink()
                        and directory.exists()
                        and not any(directory.iterdir())
                    ):
                        directory.rmdir()
                raise
    finally:
        lock.unlink(missing_ok=True)


def run_steps(project: Path, steps: list[dict], kind: str, timeout: int) -> bool:
    """顺序执行检查或安装，失败后记录尚未运行的入口以及实际退出结果。"""
    good = True
    for step in steps:
        label = step.get("name") or " ".join(step["argv"])
        if not good:
            print(f"{kind}未运行：{label}", flush=True)
            continue
        print(f"{kind}开始：{label}", flush=True)
        try:
            status_code = invoke(step["argv"], project / step["cwd"], timeout)
            status = str(status_code)
            good = status_code == 0
        except (OSError, subprocess.TimeoutExpired) as error:
            status = str(error)
            good = False
        print(f"{kind}{'通过' if good else '失败'}：{label}（{status}）", flush=True)
    return good


def invoke(argv: list[str], cwd: Path, timeout: int) -> int:
    """超时或中断时终止本步骤的进程组，避免遗留包管理器和临时服务。"""
    process = subprocess.Popen(argv, cwd=cwd, start_new_session=True)
    try:
        return process.wait(timeout=timeout)
    except (KeyboardInterrupt, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=8)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            pass
        finally:
            # 即使组长先退出，也要处理仍存活的子进程。
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        raise


def verify(project: Path, timeout: int) -> bool:
    """只执行项目实际登记的命令，不生成文件或同步依赖。"""
    config = validate_config(
        json.loads((project / DIRECTORY / "project.json").read_bytes()), project
    )
    if not config["checks"]:
        raise BootstrapError("项目没有登记检查命令")
    return run_steps(project, config["checks"], "验证", timeout)
