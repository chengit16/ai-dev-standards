"""工具包安装、诊断、更新、卸载与恢复，写操作默认预览。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 安装副本的源码哈希必须稳定，运行 CLI 不应产生未登记的字节码缓存。
sys.dont_write_bytecode = True

from bootstrap.model import BootstrapError
from install_release import add_target_options, run_release
from lifecycle.manager import doctor, manage
from lifecycle.model import InstallError, Layout
from lifecycle.transaction import recover


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "update", "doctor", "uninstall", "recover"))
    add_target_options(parser)
    parser.add_argument("--version", help="install 或 update 使用指定 GitHub 正式发行版本")
    parser.add_argument("--transaction", type=Path, help="doctor 输出的未完成事务目录")
    args = parser.parse_args(argv)
    try:
        if args.version is not None:
            if args.action not in ("install", "update"):
                parser.error("只有 install 和 update 可指定发行版本")
            return run_release(args.action, args.version, args)
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
    except (
        BootstrapError,
        InstallError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ) as error:
        print(f"生命周期操作停止：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
