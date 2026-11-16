# 开发收尾使用说明

M4 提供 [finish-task Skill](../skills/finish-task/SKILL.md) 和 `scripts/finish_task.py`，需要完整工具包、Python 3.11+ 与 Git。支持任务范围预览、真实检查、本地提交，以及单独预览和推送已有提交。本阶段未安装用户级 Skill 或改写全局规则。

## 策略与职责

Skill 判断需求是否完成、修改归属、检查是否充分与推送是否获授权；脚本验证明确输入并执行 Git 操作。脚本参数不能独立证明用户授权，也不能判断业务验收是否充分。

| 项目策略或当前指令 | 行为 |
| --- | --- |
| `local` | 可独立验收的任务通过必要检查后自动本地提交 |
| `manual` | 预览说明，可单独检查；明确要求本次提交时才提交 |
| 本次不要提交 | 当前指令优先，不运行提交入口 |
| 明确要求推送或明确启用推送策略 | 本地提交后单独核实目标与全部待推送历史再推送 |

M3 的 `project.json` 仍只支持 local/manual；M4 没有把推送变成默认值。已有 `git-commit-message` 用户级 Skill 未被修改；新流程吸收其范围核对与中文信息规则，但直接调用 finish-task 不附带推送授权。M2 已提供旧入口检测与明确保留选项，具体见[安装说明](installation.md)。

## 任务请求

以[请求示例](../templates/finish-task/request.example.json)为结构，把文件放在仓库外临时位置。已初始化项目从 `.ai-dev-standards/project.json` 读取检查和策略，请求不能覆盖它们。尚未初始化的项目可以额外显式填写 `checks` 和 `commit_policy`，检查结构与 [M3 配置](project-bootstrap.md)相同。

```json
{
  "schema_version": 1,
  "mode": "index",
  "paths": ["src/order.ts", "tests/order.test.ts"],
  "message": "fix: 修复订单空列表处理\n\n- 保留分页筛选并补齐空列表边界\n"
}
```

- `paths` 必须是审核过的精确相对文件路径，不接受目录、glob、符号链接、子模块、特殊索引项或越界路径。重命名必须列出新旧路径；普通新增、修改与删除均支持。
- `index` 从真实索引中只选指定文件，保留同文件未暂存部分；不能因为暂存区有内容就认定全是本任务改动。
- `worktree` 选指定文件完整工作区内容；同文件存在部分暂存时拒绝执行，防止扩大提交范围。同一文件含用户与本任务混合修改时，需要先可靠地形成所需暂存补丁，再用 index；工具不自动推断补丁归属。
- `message` 由审核过的净 diff 撰写，标题格式 `<type>: <中文摘要>`，可按项目要求加 scope；正文按需列中文修改项。项目 commitlint 等限制继续由现有 hook 校验。

## 预览与执行

在工具包根目录运行，替换示例路径：

```bash
python3 scripts/finish_task.py task --project ../my-project --request ../task-request.json
python3 scripts/finish_task.py task --project ../my-project --request ../task-request.json --check
python3 scripts/finish_task.py task --project ../my-project --request ../task-request.json --apply --expected-head <预览的完整HEAD> --expected-tree <预览的完整tree>
```

第一条输出候选 diff、HEAD 和 tree，不运行项目命令，不改工作文件、真实索引或分支；构建候选树可能在 Git 对象库写入无引用对象。第二条只运行检查，不提交。第三条需要与已审核预览一致，并重新运行检查后提交。manual 策略下，已获明确授权时额外加 `--authorize-commit`。没有净变更时报告 no_changes，不创建空提交或顺带推送历史。

检查以参数数组直接执行，不经 shell；默认每项超时 600 秒，可通过 `--timeout` 调整。空清单、非零退出、超时、检查改动受监测的已跟踪文件或所选文件，以及索引或 HEAD 发生变化都会停止提交，保留现场。清单由项目维护者核实，不能通过登记无意义命令声称已验收。超时不保证结束检查工具自行创建的所有子进程，处理现场前需核实是否仍在运行。

检查运行于真实工作区，hook 则正常使用候选索引。部分暂存或其他改动可能参与工作区检查；报告固定标记 checks_context 为 working_tree，不声称候选提交在干净快照中已独立通过。若 CI 或项目要求验证提交快照，应在隔离环境额外执行并明确记录结果。工具不自动重建依赖环境，也不监测全部未跟踪、忽略文件或外部服务副作用；检查命令须由项目维护者确认。

临时索引从 HEAD 构建，只带入指定路径；真实索引在成功后仅同步选中项，其他暂存和未暂存内容保留。提交调用现有 `git commit`，不跳过 hook、不自动 amend。根目录、已存在 HEAD、正常分支与无中间操作是前提；首次提交、detached HEAD、split index、sparse checkout 和冲突需先人工处理。支持 Git worktree，恢复目录位于对应的实际 Git 目录。

## 失败与中断恢复

进入提交前在 Git 目录创建 `ai-dev-standards/finish-*` 记录，保留原始索引、提交信息、通过的检查和候选 tree；这些本机恢复资料不进入业务提交。真实 index.lock 在提交与索引同步期间保留，避免其他遵循 Git 锁协议的写入。

| 记录状态 | 含义与处理 |
| --- | --- |
| `prepared` | 已备份，提交结果需查询 HEAD 和 reflog；中断可能发生在提交成功而记录尚未更新的间隙 |
| `committed_pending_index` | 已记录实际 SHA，索引尚未同步或 hook 改写候选范围；不要重复提交 |
| `committed_needs_review` | 已提交并同步对应索引，但 hook 改动工作区或有异常，需重新验证 |
| `committed` | 本地提交与索引同步完成；不代表推送已发生 |

检查失败不回滚业务文件。hook 拒绝且 HEAD 未变化时，真实索引原字节保留；hook 改写候选 tree 或 HEAD 时，保留实际 SHA 和恢复资料，不重写历史。成功提交后的异常也可能返回非零退出码，必须先查 HEAD、记录及 diff 再判断。

强制终止可能留下 index.lock。先确认所有相关 Git/检查进程结束，保存现场副本，查询 `git rev-parse --absolute-git-dir`、HEAD、reflog 和报告，比较原始索引、候选提交与当前索引；仅确认锁属于已结束流程时清理。备份只用于比较和恢复依据，不能直接覆盖可能已有后续修改的索引。无法确认所有权时保留并人工处理。当前不提供自动中断恢复，不保证跨文件及 Git 引用的事务原子性，也不防范绕过 Git 锁协议的并发写入。

## 独立推送与重试

只有已获授权才执行推送；先使用目标远程、目标分支和当前完整 HEAD 预览：

```bash
python3 scripts/finish_task.py push --project ../my-project --remote origin --branch main --expected-head <完整SHA>
python3 scripts/finish_task.py push --project ../my-project --remote origin --branch main --expected-head <完整SHA> --allow-commit <待推送SHA1> --allow-commit <待推送SHA2> --apply
```

远程和分支由 Skill 核实；CLI 不猜目标、不配置 upstream。只支持远程 fetch URL 与 push URL 唯一且相同，避免查询一个仓库却向另一个写入。预览会查询并获取指定远程分支的对象，但不改 tracking ref 或 FETCH_HEAD。网络或认证失败与“分支不存在”分开处理；远程领先、分叉或无共同历史时停止，不自动整合。

`--allow-commit` 必须精确列出目标分支尚未拥有的全部祖先提交，包括历史遗留提交；新分支可能包含从初始提交起的全部历史，不能只核对最后一条。推送仅指定一个分支，不强推、不带标签。push 成功后核对远程 SHA；若核对失败，报告“push 已返回成功但同步未核实”。

推送失败不撤销本地提交，重试运行同一个 push 子命令；已同步则直接返回 already_synced，不创建新提交。M4 的推送验证只使用临时本地 bare 远程，不涉及真实业务仓库。

## 验证

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

实际结果与边界见 [M4 验证记录](verification/m4-finish-task.md)。用户级安装、自动触发和新会话加载通过 M2 部署后在最后统一验收。
