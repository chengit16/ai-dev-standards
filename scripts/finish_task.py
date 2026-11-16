"""开发收尾 CLI：预览精确范围、执行检查、本地提交；推送独立重试。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from bootstrap.model import BootstrapError
from finish.git import Repository
from finish.push import push
from finish.task import finish, load_request


def main(argv: list[str] | None = None) -> int:
    """默认只读；CLI 标志表达已获得的授权，本身不能替代用户指令。"""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    task = commands.add_parser("task", help="预览、检查或提交任务")
    task.add_argument("--project", type=Path, required=True)
    task.add_argument("--request", type=Path, required=True)
    action = task.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--check", action="store_true", help="只运行检查，不提交")
    task.add_argument("--expected-tree")
    task.add_argument("--expected-head")
    task.add_argument(
        "--authorize-commit", action="store_true", help="本次明确授权覆盖 manual 策略"
    )
    task.add_argument("--timeout", type=int, default=600, help="每项检查超时秒数")
    remote = commands.add_parser("push", help="核对并推送已存在的提交，不创建提交")
    remote.add_argument("--project", type=Path, required=True)
    remote.add_argument("--remote", required=True)
    remote.add_argument("--branch", required=True)
    remote.add_argument("--expected-head", required=True)
    remote.add_argument("--allow-commit", action="append", default=[])
    remote.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        repo = Repository(args.project)
        if args.command == "task":
            if args.timeout < 1:
                raise BootstrapError("timeout 必须大于 0")
            result = finish(
                repo,
                load_request(args.request, repo),
                apply=args.apply,
                check_only=args.check,
                expected_tree=args.expected_tree,
                expected_head=args.expected_head,
                authorize_commit=args.authorize_commit,
                timeout=args.timeout,
            )
        else:
            result = push(
                repo, args.remote, args.branch, args.expected_head, args.allow_commit, args.apply
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (BootstrapError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"收尾停止：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
