"""推送已有提交；核实远程历史后仅推一个明确分支，重试不创建提交。"""

from __future__ import annotations

import re

from .git import FinishError, Repository


def remote_head(repo: Repository, remote: str, ref: str) -> str | None:
    """只有 ls-remote 的缺失退出码表示分支不存在，认证失败不能当作新分支。"""
    result = repo.run("ls-remote", "--exit-code", "--heads", remote, ref, check=False)
    if result.returncode == 2:
        return None
    if result.returncode:
        raise FinishError("查询远程失败，请检查认证、网络或权限；未将失败视为分支不存在")
    rows = [row.split() for row in result.stdout.decode().splitlines()]
    exact = [sha for sha, name in rows if name == ref]
    if len(exact) != 1:
        raise FinishError("远程返回的目标分支不明确")
    return exact[0]


def push(
    repo: Repository, remote: str, branch: str, expected_head: str, allowed: list[str], apply: bool
) -> dict:
    """预览全部待推送祖先；应用必须精确授权这些提交，且禁止强推与自动整合。"""
    if remote not in repo.text("remote").splitlines() or remote == ".":
        raise FinishError("必须指定已配置的远程名称")
    # 同一远程多个 pushurl 或 pushurl 与 fetch URL 不同会破坏查询与写入的一致性。
    fetch_urls = repo.text("remote", "get-url", "--all", remote).splitlines()
    push_urls = repo.text("remote", "get-url", "--push", "--all", remote).splitlines()
    if len(fetch_urls) != 1 or push_urls != fetch_urls:
        raise FinishError("当前只支持查询和推送地址相同且唯一的远程")
    if (
        not branch
        or branch.startswith("-")
        or repo.run("check-ref-format", "refs/heads/" + branch, check=False).returncode
    ):
        raise FinishError("目标分支名称无效")
    if expected_head != repo.head or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", expected_head):
        raise FinishError("expected-head 必须与当前完整 HEAD 一致")
    ref = "refs/heads/" + branch
    old = remote_head(repo, remote, ref)
    if old == repo.head:
        return {"status": "already_synced", "commit": repo.head, "remote": remote, "branch": branch}
    if old:
        # 不写 tracking ref/FETCH_HEAD，避免临时检查改变用户已有的远程跟踪状态。
        fetched = repo.run(
            "fetch",
            "--no-tags",
            "--no-prune",
            "--no-prune-tags",
            "--no-write-fetch-head",
            "--refmap=",
            "--recurse-submodules=no",
            remote,
            ref,
            check=False,
        )
        if fetched.returncode:
            raise FinishError("获取目标分支失败；未推送")
        if remote_head(repo, remote, ref) != old:
            raise FinishError("查询期间远程发生变化，请重新预览")
        if repo.run("merge-base", "--is-ancestor", old, repo.head, check=False).returncode:
            raise FinishError("目标分支领先、分叉或历史无关；不自动合并、变基或强推")
    pending = repo.text(
        "rev-list", "--reverse", f"{old}..{repo.head}" if old else repo.head
    ).splitlines()
    result = {
        "status": "push_preview",
        "commit": repo.head,
        "remote": remote,
        "branch": branch,
        "pending_commits": pending,
        "remote_head": old,
    }
    if not apply:
        return result
    if len(allowed) != len(set(allowed)) or set(allowed) != set(pending):
        raise FinishError("allow-commit 必须精确列明全部待推送提交；请核对历史后再应用")
    repo.ensure_idle()
    if (
        repo.text("rev-parse", "HEAD") != repo.head
        or repo.text("symbolic-ref", "--short", "HEAD") != repo.branch
    ):
        raise FinishError("推送前 HEAD 或分支发生变化")
    outcome = repo.run(
        "push",
        "--no-follow-tags",
        "--recurse-submodules=no",
        remote,
        repo.head + ":" + ref,
        check=False,
    )
    if outcome.returncode:
        raise FinishError(
            f"本地提交 {repo.head} 保留，远程推送失败；核查网络、权限或分支保护后重试 push 子命令"
        )
    # push 返回成功与远程 SHA 核实是两件事，后者失败时不能声称同步已确认。
    try:
        confirmed = remote_head(repo, remote, ref)
    except FinishError as error:
        raise FinishError(
            f"push 已返回成功，但远程 SHA 未核实；本地提交 {repo.head}，请先查询再重试"
        ) from error
    if confirmed != repo.head:
        raise FinishError(f"push 已返回成功，但远程 SHA 已变化；本地提交 {repo.head}，请复核")
    return dict(result, status="pushed")
