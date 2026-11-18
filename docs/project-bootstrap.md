# 接入项目规则

M3 已提供初始化 Skill、入口模板和确定性生成器。可直接从完整工具包副本运行，不依赖 M2 的用户级安装。当前生成仓库内规范与检查清单；依赖安装、业务脚手架、检查工具接入及规范升级不在此命令范围内。

[空白工程创建](project-scaffold.md)先生成应用与检查入口，再复用本生成器接入规范，最后按选项执行实际验证。已有项目可单独使用本命令。

## 运行条件与入口

需要 Python 3.11+ 和 Git，生成器只使用 Python 标准库。源码入口是 [project-bootstrap Skill](../skills/project-bootstrap/SKILL.md)，需连同工具包资源使用；M2 可部署到用户级发现目录，步骤见[安装说明](installation.md)；源码存在或部署完成不能据此声称已经自动加载。

首先阅读目标项目规则、技术栈配置与现有检查脚本。Skill 负责识别与取舍，生成器接受明确配置，不自行猜测技术栈或检查命令。新建项目至少已有一个目录；尚未建立检查工具时可把 checks 留空，生成结果会记录缺口。

## 配置

在工具包仓库根目录执行以下命令。配置文件放在目标项目之外，便于先检查和修改：

```bash
cp templates/project-bootstrap/config.example.json ../project-config.json
```

[采用配置示例](../templates/project-bootstrap/config.example.json)默认给仓库根目录的 React 项目使用，检查清单为空。按项目调整 `stacks`。单独使用后端时，只填写对应的后端键。

| 项目 | `stacks` 示例 |
| --- | --- |
| React 在仓库根目录 | `{"react-vite": ["."]}` |
| React + FastAPI | `{"react-vite": ["apps/web"], "fastapi": ["apps/api"]}` |
| React + NestJS（Fastify） | `{"react-vite": ["apps/web"], "nestjs-fastify": ["apps/api"]}` |

如果项目采用 `frontend/` 和 `backend/` 等结构，就填实际目录。下面是 React + FastAPI 的完整配置示例，假设前端确实声明了 `typecheck` 脚本：

```json
{
  "schema_version": 1,
  "stacks": {
    "react-vite": ["apps/web"],
    "fastapi": ["apps/api"]
  },
  "checks": [
    {"name": "前端类型检查", "cwd": "apps/web", "argv": ["pnpm", "typecheck"]}
  ],
  "deviations": ["现有前端请求层沿用已验证的 fetch Client，普通业务仍统一经过 Service；本次不迁移为 Axios。"],
  "commit_policy": "local"
}
```

- `stacks` 选 `react-vite`、`nestjs-fastify`、`fastapi` 中实际适用的一项或多项。目录使用仓库相对路径，根目录写 `.`，不接受 glob 或越出项目的路径。多栈共享目录时按修改职责适用。
- `checks` 是检查名称、相对工作目录和命令参数数组。只登记项目真实入口；生成器验证结构和目录，不证明命令可执行，也不会运行命令。参数不要包含秘密或本机绝对路径。
- `deviations` 写已确认的项目差异和原规范位置，保留具体有效约定。无需差异时为空列表。
- `commit_policy` 为 `local`（通过验证后按范围本地提交）或 `manual`（明确要求时才提交）；生成器本身不执行 Git 暂存、提交或推送。

初始化会将配置保存为 `.ai-dev-standards/project.json`。后续调整时，在仓库外准备新配置，再使用下文的升级命令。

## 预览与生成

在工具包根目录运行以下命令，将示例路径替换为目标项目和已准备的配置文件：

```bash
./scripts/ai-dev-standards bootstrap --project ../my-project --config ../project-config.json
./scripts/ai-dev-standards bootstrap --project ../my-project --config ../project-config.json --apply
```

第一条只显示拟生成的文件和 AGENTS 区块差异，不创建目录。第二条应用同一配置，不修改包管理配置、现有检查脚本或用户级规则。已有 `AGENTS.md` 的内容按原字节保留，在末尾追加一个带归属标记的区块。

应用后，若配置已登记检查命令，先按项目现有说明准备依赖，再运行：

```bash
./scripts/ai-dev-standards verify --project ../my-project
```

`bootstrap` 负责写入规则，`verify` 执行已登记的检查。检查清单为空时，`verify` 会报告没有登记命令。使用安装后的短命令或发行包时，见[命令入口](project-scaffold.md#命令入口)。

生成结构：

```text
目标项目/
  AGENTS.md                         原有内容 + 工具包区块
  .ai-dev-standards/
    PROJECT.md                      适用范围、差异、检查及提交策略
    project.json                    规范采用配置
    manifest.json                   工具包来源、内容指纹和受管文件哈希
    standards/
      common/                       通用工程与注释规则
      frontend/                     按选择复制
      backend/                      按选择复制
```

规范正文从 `standards/` 单一来源复制，不维护手写模板副本。生成器包含选定规范的 Markdown 链接依赖以保持离线可读；例如 FastAPI 文档引用 NestJS 选型说明时会随附该文件，但不会启用 NestJS 技术栈。所有文件使用仓库内相对引用，可独立于原工具包目录使用。

生成器以 SHA-256 精确记录规范和入口模板的内容集合，同时记录工具包 Git 提交与相关路径的工作树状态。未提交工作树生成的结果标记为工作树快照，不冒充发行版。参考来源按其公开范围记录，项目清单保留规范及工具包的版本。

## 重复执行与冲突

用生成的配置再次执行：

```bash
./scripts/ai-dev-standards bootstrap --project ../my-project --config ../my-project/.ai-dev-standards/project.json --apply
```

内容一致时不改文件或修改时间。用户在 AGENTS 受管区块外的新增内容不影响幂等检查；清单外的项目资料也不会被删除。

下列情况停止并保留现场：已有同名目录无合法来源清单、受管文件或区块被改动、配置或来源发生变化、重复或孤立标记、非空根 `AGENTS.override.md`、规则入口或受管目录内存在符号链接、范围越界或初始化锁已存在。当前没有强制覆盖或自动升级选项。

写入过程先在目标项目中的临时目录准备完整文件，再发布规范目录，最后原子替换 AGENTS。可捕获的入口写入失败会撤销本次规范目录并保留原入口；多文件操作无法保证掉电或强制杀进程时整体原子。

遇到异常退出残留时，先确认无运行中的初始化进程，检查 `.ai-dev-standards.lock`、`.ai-dev-standards-stage-*` 及目标目录。保留副本并比较原有 Git 状态；如果结果已完整，确认后清理锁和临时目录再验证；不完整时只撤销可确认由该次初始化产生且未被后续修改的文件，再重跑。不能直接删除用户目录或清单来绕过冲突；无法确认归属时人工合并。

## 升级已接入项目的规范

在要采用的工具包版本下，从工具包根目录预览差异，再应用。已安装的短命令和发行包也支持同一组参数。

```bash
./scripts/ai-dev-standards upgrade-rules --project ../my-project
./scripts/ai-dev-standards upgrade-rules --project ../my-project --apply
```

升级后，项目登记了检查命令时可执行 `./scripts/ai-dev-standards verify --project ../my-project`。默认沿用项目已登记的技术栈、目录范围、检查命令、项目差异和提交策略。要更改采用配置，先把项目的 `.ai-dev-standards/project.json` 复制到仓库外，修改后在预览和应用命令上都加 `--config ../project-config.json`。升级会保留 `AGENTS.md` 区块外内容和清单外的项目文件。若受管文件或区块已手改，先保存并整理差异。需要长期保留的内容可写入自有规则或新配置的 `deviations`，再以旧版受管内容为基线执行升级。

升级完成时会输出备份目录。独立 Git 仓库的备份位于其 Git 元数据目录，无独立 Git 目录时位于项目根目录的 `.ai-dev-standards-upgrade-backups/`。备份属于本机操作记录。遇到中断时，确认记录中的进程已经退出，再使用对应的事务目录预览和恢复：

```bash
./scripts/ai-dev-standards upgrade-rules --project ../my-project --recover "$transaction_dir"
./scripts/ai-dev-standards upgrade-rules --project ../my-project --recover "$transaction_dir" --apply
```

将 `transaction_dir` 设为该项目备份中的 `txn-*` 目录。若日志缺失或恢复发现后续改动，保留现场，按备份核对差异。已完成的升级可结合 Git 改动或备份手工回退。

## 验收

1. 核对选定技术栈、目录范围和保留的差异；检查生成文件的本地引用。
2. 重复执行应返回“无需写入”；运行目标项目实际适用的检查并记录真实结果。检查清单空缺时报告未具备对应验证。
3. 核对 Git diff，确认 `.ai-dev-standards/` 没被项目忽略并纳入本次需要的版本记录；保持用户已有暂存边界。
4. 用户安装后在新会话验证 AGENTS 入口、按修改范围读取规范以及 Skill 发现。脚本成功只证明文件已生成。

Codex 在同目录优先读取 `AGENTS.override.md`，也存在嵌套规则及加载大小限制；因此脚本拒绝被根覆盖文件遮蔽的入口，Skill 还要核对子目录约定。详见[官方 AGENTS 文档](https://learn.chatgpt.com/docs/agent-configuration/agents-md)。Skill 的 frontmatter 与发现方式见[官方 Skill 文档](https://learn.chatgpt.com/docs/build-skills)。生成文件无需全局安装即可被项目入口引用；Skill 的实际发现与加载由 M2 部署后在本机验收。

工具包自身的隔离测试命令：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

本阶段实际验证与未覆盖场景见 [M3 验证记录](verification/m3-project-bootstrap.md)。
