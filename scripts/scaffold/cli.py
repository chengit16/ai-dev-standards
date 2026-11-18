"""统一 CLI 复用现有 M2–M4 入口，创建和验证使用同一份项目采用配置。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from bootstrap.model import BootstrapError
from lifecycle.model import InstallError

from .project import create, run_steps, verify
from .release import build

DELEGATES = {
    **{name: "toolkit.py" for name in ("install", "update", "doctor", "uninstall", "recover")},
    "bootstrap": "project_bootstrap.py",
    "finish": "finish_task.py",
}
TEMPLATES = ("react-fastapi", "react-vite", "react-nestjs")


def main(argv: list[str] | None = None) -> int:
    """从源码或安装副本运行相同命令，转发旧入口的原有参数。"""
    args = list(sys.argv[1:] if argv is None else argv)
    toolkit = Path(__file__).resolve().parents[2]
    if args and args[0] in DELEGATES:
        action = args[0]
        forwarded = args if DELEGATES[action] == "toolkit.py" else args[1:]
        return subprocess.call(
            [sys.executable, str(toolkit / "scripts" / DELEGATES[action]), *forwarded]
        )
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    make = sub.add_parser("create", help="预览或创建空白工程并接入规范")
    make.add_argument("project", type=Path)
    make.add_argument("--template", choices=TEMPLATES, required=True)
    make.add_argument("--existing", action="store_true", help="保留已有规划文件")
    make.add_argument("--apply", action="store_true", help="写入工程，默认只预览")
    make.add_argument("--install", action="store_true", help="应用后从锁文件安装依赖")
    make.add_argument("--verify", action="store_true", help="应用后运行采用配置中的检查")
    make.add_argument("--git", action="store_true", help="初始化独立 Git 仓库")
    check = sub.add_parser("verify", help="运行项目采用配置中的检查")
    check.add_argument("--project", type=Path, default=Path("."))
    release = sub.add_parser("release", help="从固定 Git 提交构建发行包")
    release.add_argument("--ref", required=True)
    release.add_argument("--output", type=Path, required=True)
    for action, script in DELEGATES.items():
        sub.add_parser(action, help=f"运行 {script} 对应入口")
    for entry in (make, check):
        entry.add_argument("--timeout", type=int, default=300, help="单项命令最长运行秒数")
    options = parser.parse_args(args)
    if getattr(options, "timeout", 1) <= 0:
        parser.error("--timeout 必须大于零")
    try:
        if options.action == "release":
            package, checksum = build(toolkit, options.ref, options.output)
            print(f"发行包：{package}\n校验文件：{checksum}")
            return 0
        raw = options.project.expanduser()
        if raw.is_symlink():
            raise BootstrapError("目标不能是符号链接")
        project = raw.resolve()
        if options.action == "verify":
            return 0 if verify(project, options.timeout) else 1
        report, installs = create(
            toolkit,
            project,
            options.template,
            existing=options.existing,
            apply=options.apply,
            init_git=options.git,
        )
        report["install_requested"] = installs if options.install else []
        report["verify_requested"] = options.verify
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        if options.apply:
            if options.install and not run_steps(project, installs, "依赖安装", options.timeout):
                if options.verify:
                    print("验证未运行：依赖安装失败")
                return 1
            if options.verify and not verify(project, options.timeout):
                return 1
        return 0
    except (
        BootstrapError,
        InstallError,
        OSError,
        ValueError,
        KeyError,
        subprocess.SubprocessError,
    ) as error:
        print(f"操作停止：{error}", file=sys.stderr)
        return 1
