"""从 GitHub 获取指定版本，校验后预览或应用工具包安装。"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

API = "https://api.github.com/repos/chengit16/ai-dev-standards"
VERSION = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
COMMIT = re.compile(r"[0-9a-f]{40}")
STAMP = "_toolkit-source.json"


class ReleaseError(ValueError):
    """报告下载、校验或来源问题，保留目标安装现场。"""


def request_bytes(endpoint: str, accept: str = "application/vnd.github+json") -> bytes:
    request = Request(f"{API}/{endpoint}", headers={"Accept": accept})
    with urlopen(request, timeout=30) as response:
        if urlsplit(response.geturl()).scheme != "https":
            raise ReleaseError("GitHub 下载重定向到了非 HTTPS 地址")
        return response.read()


def tag_commit(version: str) -> str:
    ref = json.loads(request_bytes(f"git/ref/tags/{version}"))
    if ref["ref"] != f"refs/tags/{version}":
        raise ReleaseError(f"GitHub 返回的标签与 {version} 不一致")
    # 首发使用附注标签，自动发布使用轻量标签，最终一律核对提交 SHA。
    target = ref["object"]
    followed = set()
    while target["type"] == "tag":
        sha = target["sha"]
        if not COMMIT.fullmatch(sha) or sha in followed:
            raise ReleaseError(f"{version} 的标签对象无效")
        followed.add(sha)
        target = json.loads(request_bytes(f"git/tags/{sha}"))["object"]
    if target["type"] != "commit" or not COMMIT.fullmatch(target["sha"]):
        raise ReleaseError(f"{version} 未指向有效的 Git 提交")
    return target["sha"]


def asset_bytes(assets: list[dict], name: str) -> bytes:
    matches = [asset for asset in assets if asset["name"] == name]
    if len(matches) != 1 or matches[0]["state"] != "uploaded":
        raise ReleaseError(f"GitHub Release 缺少可下载的附件 {name}")
    asset = matches[0]
    asset_id = asset["id"]
    if type(asset_id) is not int or asset_id <= 0:
        raise ReleaseError(f"附件 {name} 的 GitHub 标识无效")
    data = request_bytes(f"releases/assets/{asset_id}", "application/octet-stream")
    if asset.get("digest") and asset["digest"] != "sha256:" + hashlib.sha256(data).hexdigest():
        raise ReleaseError(f"附件 {name} 的 SHA-256 与 GitHub 记录不一致")
    return data


def download(version: str) -> tuple[str, bytes]:
    if not VERSION.fullmatch(version):
        raise ReleaseError("请指定固定的正式版本号，例如 v0.1.1")
    try:
        release = json.loads(request_bytes(f"releases/tags/{version}"))
    except HTTPError as error:
        if error.code == 404:
            raise ReleaseError(f"找不到已发布的正式版本 {version}") from error
        raise
    if release["tag_name"] != version or release["draft"] or release["prerelease"]:
        raise ReleaseError(f"{version} 未公开为正式版本")

    commit = tag_commit(version)
    stem = f"ai-dev-standards-{commit[:12]}"
    assets = release["assets"]
    checksum = asset_bytes(assets, f"{stem}.sha256")
    payload = asset_bytes(assets, f"{stem}.pyz")
    digest = hashlib.sha256(payload).hexdigest()
    if checksum != f"{digest}  {stem}.pyz\n".encode():
        raise ReleaseError(f"{stem}.pyz 与同版本的 .sha256 校验文件不一致")
    return commit, payload


def unpack(payload: bytes, source: Path, version: str, commit: str) -> None:
    with ZipFile(io.BytesIO(payload)) as archive:
        stamp = json.loads(archive.read(STAMP))
        origin = stamp["source"]
        if (
            stamp["owner"] != "ai-dev-standards"
            or stamp["schema_version"] != 1
            or origin["git_commit"] != commit
            or origin["working_tree_dirty"] is not False
            or origin.get("release_version", version) != version
        ):
            raise ReleaseError(f"发行包来源与标签 {version} 的提交 {commit} 不一致")
        names = set(archive.namelist())
        if (
            len(names) != len(archive.infolist())
            or names != {*stamp["files"], "__main__.py", STAMP}
            or "scripts/toolkit.py" not in names
            or any(
                "\\" in name or any(part in ("", ".", "..") for part in name.split("/"))
                for name in names
            )
        ):
            raise ReleaseError("发行包文件名或资源清单无效")
        archive.extractall(source, names - {"__main__.py", STAMP})
    # 标签在打包后才分配，校验 GitHub 标签后补记在临时来源中，兼容已发行的旧包。
    origin["release_version"] = version
    (source / STAMP).write_text(json.dumps(stamp) + "\n", encoding="utf-8")


def run_release(action: str, version: str, args: argparse.Namespace) -> int:
    try:
        commit, payload = download(version)
        with tempfile.TemporaryDirectory(prefix="ai-dev-verified-release-") as folder:
            source = Path(folder).resolve()
            unpack(payload, source, version, commit)
            print(f"已校验发行版 {version}（Git {commit}）", file=sys.stderr)
            command = [sys.executable, str(source / "scripts/toolkit.py"), action]
            for option in ("home", "codex_home", "legacy_policy"):
                value = getattr(args, option)
                if value is not None:
                    command.extend(["--" + option.replace("_", "-"), str(value)])
            if args.apply:
                command.append("--apply")
            return subprocess.call(command)
    except HTTPError as error:
        raise ReleaseError(f"GitHub 请求失败（HTTP {error.code}）") from error
    except (URLError, TimeoutError, HTTPException) as error:
        raise ReleaseError(f"连接 GitHub 失败：{error}") from error
    except (
        json.JSONDecodeError,
        UnicodeError,
        BadZipFile,
        KeyError,
        TypeError,
        AttributeError,
    ) as error:
        raise ReleaseError(f"GitHub 返回的发行信息或发行包无效：{error}") from error


def add_target_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--home", type=Path, help="隔离验收的用户目录；指定后不继承 CODEX_HOME")
    parser.add_argument("--codex-home", type=Path, help="显式 Codex 配置目录")
    parser.add_argument("--apply", action="store_true", help="实际写入；默认只预览")
    parser.add_argument("--legacy-policy", choices=("stop", "keep"), help="明确保留旧提交 Skill")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "update"))
    parser.add_argument("--version", required=True, help="指定 GitHub 正式发行版本，例如 v0.1.1")
    add_target_options(parser)
    args = parser.parse_args()
    try:
        return run_release(args.action, args.version, args)
    except (ReleaseError, OSError) as error:
        print(f"操作停止：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
