"""为 main 的已验收提交分配版本，并在附件完整后公开 GitHub Release。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from zipfile import BadZipFile

from verify_release import verify_package

STABLE = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def version_key(tag: str) -> tuple[int, ...]:
    match = STABLE.fullmatch(tag)
    return tuple(map(int, match.groups())) if match else ()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def api(repo: str, path: str, *args: str, payload: dict | None = None):
    command = ["gh", "api", f"repos/{repo}/{path}", *args]
    if payload is not None:
        command += ["--input", "-"]
    data = None if payload is None else json.dumps(payload)
    result = subprocess.run(command, input=data, stdout=subprocess.PIPE, check=True, text=True)
    return json.loads(result.stdout)


def list_releases(repo: str) -> list[dict]:
    pages = api(repo, "releases?per_page=100", "--paginate", "--slurp")
    return [release for page in pages for release in page]


def upgrade_base(releases: list[dict], commit: str) -> str:
    stable = [
        release["tag_name"]
        for release in releases
        if not release["draft"] and not release["prerelease"] and version_key(release["tag_name"])
    ]
    if not stable:
        raise ValueError("找不到可用于升级验收的已发布正式版本")
    base = max(stable, key=version_key)
    base_commit = git("rev-parse", "--verify", f"refs/tags/{base}^{{commit}}")
    # 延迟运行或重跑历史提交时，不能把旧代码当成当前版本的升级发布。
    common = git("merge-base", base_commit, commit)
    if common == commit:
        print(f"- 提交 `{commit}` 已包含在正式版本 `{base}`，跳过自动发布。", flush=True)
        return ""
    if common != base_commit:
        raise ValueError(f"候选提交与正式版本 {base} 的历史已分叉")
    return base


def draft_for(releases: list[dict], commit: str, base: str) -> tuple[dict | None, str]:
    marker = f"<!-- ai-dev-standards:auto-release:{commit} -->"
    drafts = [
        release
        for release in releases
        if release["draft"] and marker in (release.get("body") or "").splitlines()
    ]
    if drafts:
        draft = drafts[0]
        tag = draft["tag_name"]
        if (
            len(drafts) != 1
            or draft["prerelease"]
            or draft["target_commitish"] != commit
            or version_key(tag) <= version_key(base)
        ):
            raise ValueError("自动发布草稿与当前提交或版本不一致，请在 GitHub 核对草稿")
        return draft, tag

    # 已存在的手工标签和草稿也占用版本号，分配版本时保留这些记录。
    reserved = set(git("tag", "--list", "v*").splitlines())
    reserved.update(release["tag_name"] for release in releases)
    major, minor, patch = version_key(base)
    tag = f"v{major}.{minor}.{patch + 1}"
    while tag in reserved:
        patch += 1
        tag = f"v{major}.{minor}.{patch + 1}"
    return None, tag


def verify_assets(assets: list[dict], checksums: dict[str, str], *, complete: bool) -> None:
    seen = set()
    for asset in assets:
        name = asset["name"]
        if (
            name in seen
            or name not in checksums
            or asset["state"] != "uploaded"
            or asset["digest"] != checksums[name]
        ):
            raise ValueError(f"草稿附件 {name} 与已验收产物不一致，请在 GitHub 核对附件")
        seen.add(name)
    if complete and seen != checksums.keys():
        raise ValueError("草稿缺少已验收的发行包或校验文件")


def ensure_tag(repo: str, tag: str, commit: str) -> None:
    ref = f"refs/tags/{tag}"
    matches = api(repo, f"git/matching-refs/tags/{tag}")
    existing = next((item for item in matches if item["ref"] == ref), None)
    if existing is None:
        # 先创建指向固定提交的标签。若其他发布者抢先占用编号，GitHub 拒绝创建。
        existing = api(repo, "git/refs", "--method", "POST", payload={"ref": ref, "sha": commit})
    if existing["object"]["type"] != "commit" or existing["object"]["sha"] != commit:
        raise ValueError(f"标签 {tag} 已由其他发布占用")


def verify_draft(draft: dict, tag: str, commit: str) -> None:
    if not draft["draft"] or draft["tag_name"] != tag or draft["target_commitish"] != commit:
        raise ValueError(f"发布前草稿 {tag} 的状态或目标提交发生变化")


def publish(repo: str, commit: str, tested_base: str, folder: Path) -> None:
    package = verify_package(folder, commit)
    files = [package, package.with_suffix(".sha256")]
    checksums = {
        path.name: "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() for path in files
    }
    releases = list_releases(repo)
    base = upgrade_base(releases, commit)
    if not base:
        return
    if base != tested_base:
        raise ValueError(f"升级基线已由 {tested_base} 变为 {base}，请重新运行全部作业")
    draft, tag = draft_for(releases, commit, base)
    if draft is None:
        server = os.environ["GITHUB_SERVER_URL"]
        run_id = os.environ["GITHUB_RUN_ID"]
        body = "\n".join(
            (
                f"<!-- ai-dev-standards:auto-release:{commit} -->",
                f"- 来源提交 `{commit}`",
                f"- [查看相对 {base} 的变更]({server}/{repo}/compare/{base}...{commit})",
                f"- [查看构建与安装验收]({server}/{repo}/actions/runs/{run_id})",
                f"- [安装与升级说明]({server}/{repo}/blob/{commit}/docs/installation.md)",
            )
        )
        draft = api(
            repo,
            "releases",
            "--method",
            "POST",
            payload={
                "tag_name": tag,
                "name": tag,
                "target_commitish": commit,
                "draft": True,
                "body": body,
            },
        )

    endpoint = f"releases/{draft['id']}"
    verify_draft(draft, tag, commit)
    assets = draft["assets"]
    verify_assets(assets, checksums, complete=False)
    present = {asset["name"] for asset in assets}
    missing = [str(path) for path in files if path.name not in present]
    if missing:
        subprocess.run(["gh", "release", "upload", tag, *missing, "--repo", repo], check=True)

    # 重读草稿及 GitHub 计算的摘要，确保发布的是同一对已验收文件。
    current = api(repo, endpoint)
    verify_draft(current, tag, commit)
    verify_assets(current["assets"], checksums, complete=True)
    ensure_tag(repo, tag, commit)
    release = api(
        repo, endpoint, "--method", "PATCH", payload={"draft": False, "make_latest": "true"}
    )
    if release["draft"] or release["tag_name"] != tag:
        raise ValueError(f"GitHub 返回的发布状态或版本与 {tag} 不一致")
    verify_assets(release["assets"], checksums, complete=True)
    print(f"- 已发布 [{tag}]({release['html_url']})，来源提交 `{commit}`。", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "publish"))
    parser.add_argument("commit")
    parser.add_argument("--base")
    parser.add_argument("--folder", type=Path)
    args = parser.parse_args()
    repo = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit) or git("rev-parse", "HEAD") != args.commit:
        parser.error("参数必须是检出的完整提交 SHA")
    try:
        if args.action == "plan":
            base = upgrade_base(list_releases(repo), args.commit)
            with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
                output.write(f"previous_version={base}\nskip={'false' if base else 'true'}\n")
        else:
            if args.base is None or args.folder is None:
                parser.error("publish 需要 --base 和 --folder")
            publish(repo, args.commit, args.base, args.folder)
    except (OSError, ValueError, KeyError, BadZipFile, subprocess.SubprocessError) as error:
        raise SystemExit(f"自动发布停止：{error}") from error


if __name__ == "__main__":
    main()
