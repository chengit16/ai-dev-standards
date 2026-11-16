"""项目规则初始化 CLI；默认预览，显式 --apply 才写入项目。"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

# 安装副本需保持清单一致，运行入口不生成受管目录外的字节码缓存。
sys.dont_write_bytecode = True

from bootstrap.model import DIRECTORY, BootstrapError, render, validate_config
from bootstrap.storage import apply, inspect, source_version


def main(argv: list[str] | None = None) -> int:
    """解析显式采用配置，先报告计划，再按选项生成仓库内规则。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True, help="已有项目目录")
    parser.add_argument(
        "--config", type=Path, required=True, help="采用配置 JSON；可来自已生成的 project.json"
    )
    parser.add_argument("--apply", action="store_true", help="实际写入；默认只读预览")
    args = parser.parse_args(argv)
    try:
        # 1. 配置由 Skill 核对后提供，脚本不通过框架名称猜测检查命令。
        project = args.project.resolve()
        toolkit = Path(__file__).resolve().parents[1]
        if not project.is_dir() or project == toolkit or project.is_relative_to(toolkit):
            raise BootstrapError("目标必须是工具包之外的已有项目目录")
        config = validate_config(json.loads(args.config.read_text()), project)
        files, block, content_id = render(toolkit, config)
        original, unchanged = inspect(project, files, block, content_id)
        if unchanged:
            print("已初始化且内容一致：无需写入。")
            return 0
        # 2. 输出受影响文件及入口差异，保证生成前可以核对具体结果。
        print(
            "新增："
            + ", ".join(f"{DIRECTORY}/{name}" for name in sorted(files))
            + f", {DIRECTORY}/manifest.json"
        )
        separator = b"" if not original else (b"\n" if original.endswith(b"\n") else b"\n\n")
        merged = (original or b"") + separator + block
        print(
            "".join(
                difflib.unified_diff(
                    (original or b"").decode().splitlines(True),
                    merged.decode().splitlines(True),
                    fromfile="AGENTS.md（原有）",
                    tofile="AGENTS.md（生成后）",
                )
            )
        )
        # 3. 只生成，不执行检查、提交、安装依赖或修改用户级配置。
        if args.apply:
            apply(project, files, block, source_version(toolkit, content_id), original)
            inspect(project, files, block, content_id)
            print("已生成项目规范；项目检查尚未执行，宿主加载尚待新会话验证。")
        else:
            print("预览完成，未写入；使用 --apply 应用同一配置。")
        return 0
    except (BootstrapError, OSError, ValueError) as error:
        print(f"初始化停止：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
