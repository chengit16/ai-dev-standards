"""工具包安装、诊断、更新、卸载与恢复；默认预览，不联网更新来源。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 安装副本的源码哈希必须稳定，运行 CLI 不应产生未登记的字节码缓存。
sys.dont_write_bytecode = True

from lifecycle.manager import doctor, manage
from lifecycle.model import InstallError, Layout
from lifecycle.transaction import recover


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "update", "doctor", "uninstall", "recover"))
    parser.add_argument("--home", type=Path, help="隔离验收的用户目录；指定后不继承 CODEX_HOME")
    parser.add_argument("--codex-home", type=Path, help="显式 Codex 配置目录")
    parser.add_argument("--apply", action="store_true", help="实际写入；默认只预览")
    parser.add_argument("--legacy-policy", choices=("stop", "keep"), help="明确保留旧提交 Skill")
    parser.add_argument("--transaction", type=Path, help="doctor 输出的未完成事务目录")
    args = parser.parse_args(argv)
    try:
        layout = Layout.create(args.home, args.codex_home)
        if args.action == "doctor":
            result = doctor(layout)
        elif args.action == "recover":
            layout.validate()
            if args.transaction is None:
                raise InstallError("recover 需要 --transaction 指定 doctor 输出的事务目录")
            result = recover(layout, args.transaction.expanduser().absolute(), args.apply)
        else:
            result = manage(
                layout,
                Path(__file__).resolve().parents[1],
                args.action,
                args.apply,
                args.legacy_policy,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("problems") else 0
    except (InstallError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"生命周期操作停止：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
