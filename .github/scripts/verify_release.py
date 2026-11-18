"""校验候选包与已发布的升级基线，并在隔离目录演练发行包。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import BadZipFile, ZipFile


def verify_package(folder: Path, commit: str) -> Path:
    package = folder / f"ai-dev-standards-{commit[:12]}.pyz"
    checksum = hashlib.sha256(package.read_bytes()).hexdigest()
    # 校验文件必须只声明本次要执行的发行包，不能指向其他文件。
    if package.with_suffix(".sha256").read_bytes() != f"{checksum}  {package.name}\n".encode():
        raise ValueError(f"{package.name} 的 SHA-256 校验失败")
    with ZipFile(package) as archive:
        source = json.loads(archive.read("_toolkit-source.json"))["source"]
        if source["git_commit"] != commit or source["working_tree_dirty"] is not False:
            raise ValueError(f"{package.name} 的来源记录与提交 {commit} 不一致")
        license_text = archive.read("LICENSE")
    # 用对应提交的许可原文校验，上一版和候选版可以有各自的版权年份。
    expected_license = subprocess.check_output(["git", "show", f"{commit}:LICENSE"])
    if license_text != expected_license or not license_text.startswith(b"MIT License\n"):
        raise ValueError(f"{package.name} 的 MIT 许可与提交 {commit} 不一致")
    print(f"- `{package.name}` 通过 SHA-256、来源提交 `{commit}` 和 MIT 许可核对。", flush=True)
    return package


def run_lifecycle(
    package: Path, home: Path, action: str, status: str, *, apply: bool = False
) -> dict:
    command = [sys.executable, str(package), action, "--home", str(home)]
    if apply:
        command.append("--apply")
    result = json.loads(subprocess.check_output(command))
    if result["status"] != status or result.get("problems"):
        raise ValueError(f"{package.name} {action} 预期 {status}，实际结果为 {result}")
    return result


def verify_deployment(package: Path, home: Path, commit: str) -> None:
    report = run_lifecycle(package, home, "doctor", "deployed")
    if report["source"]["git_commit"] != commit:
        raise ValueError(f"doctor 报告的部署来源与提交 {commit} 不一致")


def rehearse(
    home: Path, package: Path, commit: str, baseline: tuple[Path, str] | None = None
) -> None:
    home.mkdir()
    codex = home / ".codex"
    codex.mkdir()
    agents = codex / "AGENTS.md"
    original_rules = "# 测试用户自己的规则\n".encode()
    agents.write_bytes(original_rules)
    config = codex / "config.toml"
    original_config = "# 测试用户自己的配置\n".encode()
    config.write_bytes(original_config)
    extra_rules = b""

    if baseline is None:
        run_lifecycle(package, home, "install", "deployed", apply=True)
    else:
        previous, previous_commit = baseline
        run_lifecycle(previous, home, "install", "deployed", apply=True)
        verify_deployment(previous, home, previous_commit)
        # 模拟上一版部署后用户在受管区块外追加自己的规则。
        extra_rules = "\n# 用户后来添加的规则\n".encode()
        with agents.open("ab") as handle:
            handle.write(extra_rules)
        run_lifecycle(package, home, "update", "deployed", apply=True)

    verify_deployment(package, home, commit)
    installed_rules = agents.read_bytes()
    if (
        not installed_rules.startswith(original_rules)
        or not installed_rules.endswith(extra_rules)
        or config.read_bytes() != original_config
    ):
        raise ValueError(f"{home.name} 安装或升级后用户配置有变化")
    run_lifecycle(package, home, "uninstall", "uninstalled", apply=True)
    run_lifecycle(package, home, "doctor", "not_installed")
    if (
        agents.read_bytes() != original_rules + extra_rules
        or config.read_bytes() != original_config
    ):
        raise ValueError(f"{home.name} 卸载后用户配置有变化")
    print(f"- {home.name}通过部署诊断、卸载及用户配置保留检查。", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commit")
    parser.add_argument("candidate_dir", type=Path)
    parser.add_argument("previous_commit")
    parser.add_argument("previous_dir", type=Path)
    args = parser.parse_args()
    try:
        candidate = verify_package(args.candidate_dir, args.commit)
        previous = verify_package(args.previous_dir, args.previous_commit)
        with tempfile.TemporaryDirectory(prefix="ai-dev-release-check-") as folder:
            home = Path(folder)
            rehearse(home / "全新安装", candidate, args.commit)
            rehearse(home / "上一个发行版升级", candidate, args.commit, (previous, args.previous_commit))
        print("- `doctor` 已检查部署状态。宿主实际规则与 Skill 加载待单独验收。")
    except (OSError, ValueError, KeyError, BadZipFile, subprocess.SubprocessError) as error:
        raise SystemExit(f"发行包验收失败：{error}") from error


if __name__ == "__main__":
    main()
