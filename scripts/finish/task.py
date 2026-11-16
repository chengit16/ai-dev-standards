"""在隔离索引中构建任务提交，成功后仅同步对应真实索引项。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from bootstrap.model import relative_path, validate_config

from .git import FinishError, Repository, file_path


def load_request(path: Path, repo: Repository) -> dict:
    """项目采用配置是策略权威来源；未初始化仓库须在任务请求显式提供策略。"""
    request = json.loads(path.read_text())
    required = {"schema_version", "mode", "paths", "message"}
    if (
        not isinstance(request, dict)
        or not required <= request.keys()
        or request.keys() - (required | {"checks", "commit_policy"})
    ):
        raise FinishError("任务请求字段无效")
    if type(request["schema_version"]) is not int or request["schema_version"] != 1:
        raise FinishError("不支持的任务请求版本")
    if request["mode"] not in ("index", "worktree"):
        raise FinishError("mode 必须为 index 或 worktree")
    paths = request["paths"]
    if not isinstance(paths, list) or not paths:
        raise FinishError("paths 必须明确列出本任务文件")
    paths = [file_path(value) for value in paths]
    if len(paths) != len(set(paths)):
        raise FinishError("paths 不能重复")
    request["paths"] = paths
    message = request["message"]
    if (
        not isinstance(message, str)
        or not re.match(r"^[a-z]+(?:\([^\n()]+\))?!?: [^\n]*[\u4e00-\u9fff][^\n]*(?:\n|$)", message)
        or "\x00" in message
        or "\r" in message
    ):
        raise FinishError("提交标题须采用 <type>: <中文摘要>，scope 按项目要求填写")
    adopted = repo.root / ".ai-dev-standards/project.json"
    if adopted.exists():
        if "checks" in request or "commit_policy" in request:
            raise FinishError("已初始化项目使用 project.json 的检查和策略，不能在请求中覆盖")
        config = validate_config(json.loads(adopted.read_text()), repo.root)
    else:
        if "checks" not in request or "commit_policy" not in request:
            raise FinishError("未初始化项目须显式提供 checks 和 commit_policy")
        # 复用 M3 的命令及路径校验；此处的占位栈不生成也不声明项目技术栈。
        config = validate_config(
            {
                "schema_version": 1,
                "stacks": {"react-vite": ["."]},
                "deviations": [],
                "checks": request["checks"],
                "commit_policy": request["commit_policy"],
            },
            repo.root,
        )
    request["checks"] = config["checks"]
    request["commit_policy"] = config["commit_policy"]
    return request


def validate_paths(repo: Repository, paths: list[str]) -> None:
    """首版只处理普通文件与删除；不猜测目录、子模块或特殊索引项的归属。"""
    for name in paths:
        target = repo.root / name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise FinishError(f"只支持普通文件或删除：{name}")
        if not target.parent.resolve().is_relative_to(repo.root):
            raise FinishError(f"文件路径越出仓库：{name}")
        # 删除后的目录仍可被 Git 当作路径前缀；必须核对索引和 HEAD 中的精确名称。
        indexed = repo.run("ls-files", "-z", "--", name).stdout.split(b"\x00")
        historical = repo.run(
            "ls-tree", "-r", "--name-only", "-z", "HEAD", "--", name
        ).stdout.split(b"\x00")
        if any(item and item != name.encode() for item in indexed + historical):
            raise FinishError(f"必须列出目录内的精确文件，不能选择目录前缀：{name}")
        visible = repo.run(
            "diff", "--cached", "--name-only", "-z", "--ita-visible-in-index", "--", name
        ).stdout
        invisible = repo.run(
            "diff", "--cached", "--name-only", "-z", "--ita-invisible-in-index", "--", name
        ).stdout
        if visible != invisible:
            raise FinishError(f"文件仅标记 intent-to-add，尚未真正暂存：{name}")
        flags = repo.run("ls-files", "-v", "-z", "--", name).stdout.split(b"\x00")
        if any(item and item[:1] != b"H" for item in flags):
            raise FinishError(f"路径含特殊索引标记：{name}")
        for item in repo.entries([name]).split(b"\x00"):
            if item and item.split(b" ", 1)[0] not in (b"100644", b"100755"):
                raise FinishError(f"不自动处理子模块或符号链接：{name}")


def snapshot(repo: Repository, paths: list[str]) -> tuple:
    """检查或 hook 改变已审核状态时停止；不靠 stash 隐藏其他人的修改。"""
    files = []
    for name in paths:
        target = repo.root / name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise FinishError(f"所选文件类型发生变化：{name}")
        files.append(
            (
                name,
                target.read_bytes() if target.exists() else None,
                target.stat().st_mode if target.exists() else None,
            )
        )
    return (
        repo.text("rev-parse", "HEAD"),
        repo.text("symbolic-ref", "--short", "HEAD"),
        repo.index_bytes(),
        repo.run("diff", "--no-ext-diff", "--no-textconv", "--binary").stdout,
        tuple(files),
    )


def candidate(repo: Repository, request: dict, folder: Path) -> tuple[dict, str]:
    """候选索引从 HEAD 起步，仅导入已核对的任务范围。"""
    env = dict(repo.env, GIT_INDEX_FILE=str(folder / "candidate-index"))
    repo.run("read-tree", repo.head, env=env)
    if request["mode"] == "index":
        repo.set_entries(request["paths"], repo.entries(request["paths"]), env)
    else:
        # 同文件部分暂存不能用全文件 add 扩大范围，需改为 index 或人工分离。
        for name in request["paths"]:
            staged = bool(repo.run("diff", "--cached", "--name-only", "-z", "--", name).stdout)
            # diff --quiet 可能刷新真实索引的 stat 缓存；预览必须保持原索引字节。
            unstaged = bool(
                repo.run("diff", "--no-ext-diff", "--no-textconv", "--binary", "--", name).stdout
            )
            # 已暂存删除后又重建的同名文件属于未跟踪内容，普通 diff 不会显示。
            # 仍按部分暂存处理，避免用全文件选择撤销用户暂存的删除。
            if (repo.root / name).exists() and not repo.entries([name]):
                unstaged = True
            if staged and unstaged:
                raise FinishError(f"文件存在部分暂存，请使用 index 模式或人工分离：{name}")
        repo.run("add", "--all", "--", *request["paths"], env=env)
    repo.run("diff", "--cached", "--check", env=env)
    return env, repo.text("write-tree", env=env)


def run_checks(repo: Repository, request: dict, timeout: int) -> list[dict]:
    """在真实工作区执行已核实命令；不把模型声明的通过当作工具结果。"""
    if not request["checks"]:
        raise FinishError("检查清单为空；请先建立适用检查，不能自动认定验收通过")
    results = []
    for check in request["checks"]:
        cwd = repo.root / relative_path(check["cwd"])
        if not cwd.is_dir() or not cwd.resolve().is_relative_to(repo.root):
            raise FinishError("检查目录已变化或越出项目")
        print(f"执行检查：{check['name']}", flush=True)
        result = subprocess.run(check["argv"], cwd=cwd, env=repo.env, timeout=timeout, check=False)
        results.append({"name": check["name"], "returncode": result.returncode})
        if result.returncode:
            raise FinishError(f"检查失败：{check['name']}（退出码 {result.returncode}）；未提交")
    return results


def finish(
    repo: Repository,
    request: dict,
    *,
    apply: bool,
    check_only: bool,
    expected_tree: str | None,
    expected_head: str | None,
    authorize_commit: bool,
    timeout: int,
) -> dict:
    """先预览或检查，显式应用时验证快照并保留真实索引的非任务内容。"""
    validate_paths(repo, request["paths"])
    before = snapshot(repo, request["paths"])
    with tempfile.TemporaryDirectory(prefix="finish-task-") as temporary:
        env, tree = candidate(repo, request, Path(temporary))
        if snapshot(repo, request["paths"]) != before:
            raise FinishError("准备范围时仓库发生变化，请重新预览")
        base_tree = repo.text("rev-parse", "HEAD^{tree}")
        result = {
            "status": "preview",
            "head": repo.head,
            "tree": tree,
            "mode": request["mode"],
            "checks_context": "working_tree",
            "commit_policy": request["commit_policy"],
        }
        print(json.dumps(result, ensure_ascii=False), flush=True)
        print(repo.text("diff", "--cached", "--no-ext-diff", "--no-textconv", "--binary", env=env))
        if tree == base_tree:
            return dict(result, status="no_changes")
        if not apply and not check_only:
            return result
        if apply and (expected_tree != tree or expected_head != repo.head):
            raise FinishError("候选内容或 HEAD 与预览不一致，请重新审核后提供 expected-tree/head")
        if apply and request["commit_policy"] == "manual" and not authorize_commit:
            raise FinishError("当前为 manual 策略；仅明确授权提交时使用 --authorize-commit")
        checks = run_checks(repo, request, timeout)
        if snapshot(repo, request["paths"]) != before:
            raise FinishError("检查改变了文件、索引或 HEAD；保留现场，请重新审核并运行检查")
        if check_only:
            return dict(result, status="checked", checks=checks)
        return commit(repo, request, env, tree, before, checks)


def commit(
    repo: Repository, request: dict, env: dict, tree: str, before: tuple, checks: list[dict]
) -> dict:
    """真实索引用排他锁保护；钩子仍运行，失败不恢复过时工作树或改写历史。"""
    lock = Path(str(repo.index) + ".lock")
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    report_dir = None
    try:
        repo.ensure_idle()
        if snapshot(repo, request["paths"]) != before:
            raise FinishError("提交前仓库状态发生变化，请重新预览")
        state = repo.gitdir / "ai-dev-standards"
        state.mkdir(exist_ok=True)
        report_dir = Path(tempfile.mkdtemp(prefix="finish-", dir=state))
        original = repo.index_bytes()
        if original is None:
            raise FinishError("真实索引缺失；请先核实仓库状态")
        (report_dir / "original-index").write_bytes(original)
        next_index = report_dir / "next-index"
        next_index.write_bytes(original)
        next_env = dict(repo.env, GIT_INDEX_FILE=str(next_index))
        repo.set_entries(request["paths"], repo.entries(request["paths"], env), next_env)
        record = {
            "status": "prepared",
            "base": repo.head,
            "tree": tree,
            "paths": request["paths"],
            "checks": checks,
            "checks_context": "working_tree",
            "original_index_sha256": hashlib.sha256(original).hexdigest(),
        }
        report = report_dir / "report.json"
        report.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        message = report_dir / "message.txt"
        message.write_text(request["message"].rstrip() + "\n")
        outcome = repo.run("commit", "--file", str(message), env=env, check=False)
        current = repo.text("rev-parse", "HEAD")
        if current == repo.head:
            raise FinishError(
                "提交未成功，真实索引保持原状：" + outcome.stderr.decode(errors="replace")
            )
        # 先落盘 SHA；即使后续索引同步失败，也能按该记录恢复，不能重做一次提交。
        record.update(status="committed_pending_index", commit=current)
        report.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        actual_tree = repo.text("rev-parse", "HEAD^{tree}")
        if (
            actual_tree != tree
            or repo.text("rev-parse", "HEAD^") != repo.head
            or repo.text("symbolic-ref", "--short", "HEAD") != repo.branch
            or repo.index_bytes() != original
        ):
            raise FinishError(
                f"HEAD 已变化为 {current}，hook 或并发操作改变审核范围；保留恢复记录 {report}"
            )
        # hook 如改动工作区，提交仍已存在，但必须报告未验证状态并阻止自动推送。
        worktree_changed = snapshot(repo, request["paths"])[3:] != before[3:]
        os.replace(next_index, repo.index)
        record["status"] = "committed_needs_review" if worktree_changed else "committed"
        report.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        print(outcome.stdout.decode(errors="replace"), end="")
        if worktree_changed or outcome.returncode:
            raise FinishError(
                f"本地已提交 {current}，hook 改动或异常需复核；不推送。记录：{report}"
            )
        return dict(record, report=str(report))
    except Exception as error:
        # commit 成功后的文件系统失败不能伪装成“没有提交”，否则重试会制造错误提交。
        # 不自动恢复旧索引；提示实际 HEAD 和已保留的恢复目录供核对。
        head = repo.run("rev-parse", "HEAD", check=False)
        actual = head.stdout.decode(errors="replace").strip()
        if actual and actual != repo.head:
            raise FinishError(
                f"HEAD 已变化为 {actual}，后续收尾未确认完成；请勿重复提交。"
                f"恢复目录：{report_dir}；原因：{error}"
            ) from error
        raise
    finally:
        lock.unlink(missing_ok=True)
