# AI 开发规范工具包

将个人开发规范、前后端技术栈约定与 AI 开发工作流集中维护，通过 Git 分发到不同电脑，在具体项目中生成可持续维护的工程规则。

## 当前状态

已提供通用、React 前端及两套后端规范，实现 M3 项目初始化和 M4 开发收尾。完整工具包副本可生成项目规范、执行检查并按策略本地提交，推送需要单独授权。M2 已提供安装、更新、诊断、卸载与恢复入口，已完成隔离验证及维护者本机验收。

第一版面向 Codex。其他 AI 开发工具的适配属于后续范围。

M5 已提供三套空白工程模板、创建和验证命令，以及可从固定 Git 提交构建的单文件发行包。业务项目保存在各自独立目录和仓库。

## 目标体验

1. 从完整源码或固定版本发行包启用个人规则与 Skills。
2. 新项目确定技术栈后，从空白模板创建基础工程、接入适用规范并运行实际检查；已有项目可只接入规范。
3. 每完成一个可独立验收的开发任务，执行必要检查并按策略提交。
4. 更新工具包时保留本机配置；更新业务项目规范时查看差异并合并。

已有业务项目的规范升级仍属后续范围。

## 快速开始

以下命令在工具包仓库根目录运行，目标路径按实际项目修改。两个入口都可以直接使用完整工具包。如果需要在本机启用全局规则和两个 Skill，见[安装说明](docs/installation.md)。

### 已有项目只接入规则

先按项目实际技术栈和检查命令准备配置，再预览并应用：

```bash
cp templates/project-bootstrap/config.example.json ../project-config.json
# 编辑 ../project-config.json，填写真实目录和检查命令
./scripts/ai-dev-standards bootstrap --project ../my-project --config ../project-config.json
./scripts/ai-dev-standards bootstrap --project ../my-project --config ../project-config.json --apply
```

这会写入项目的 `AGENTS.md` 和 `.ai-dev-standards/`。配置里有检查命令时，可执行 `./scripts/ai-dev-standards verify --project ../my-project`。配置字段和不同技术栈示例见[接入项目规则](docs/project-bootstrap.md)。

### 从模板新建工程并接入规则

任选一条命令，去掉 `--apply` 可先预览：

```bash
# React
./scripts/ai-dev-standards create ../my-react-app --template react-vite --apply --install --verify
# React + FastAPI
./scripts/ai-dev-standards create ../my-fastapi-app --template react-fastapi --apply --install --verify
# React + NestJS（Fastify）
./scripts/ai-dev-standards create ../my-nestjs-app --template react-nestjs --apply --install --verify
```

模板会自动登记适用规则和检查。只想先生成工程与规则时，保留 `--apply`，省略 `--install --verify`。启动方式见生成项目的 README，运行环境、已有规划目录和发行包用法见[创建工程与验证](docs/project-scaffold.md)。

## 文档入口

- [安装与本机验收](docs/installation.md)：M2 预览、部署、诊断、更新、卸载与中断恢复。

- [开发规范库](standards/README.md)：规范入口、组合方式与适用范围。
- [接入项目规则](docs/project-bootstrap.md)：已有项目的配置、预览、应用和验证。
- [创建工程与验证](docs/project-scaffold.md)：M5 模板创建、检查及免克隆发行包用法。
- [M5 验证记录](docs/verification/m5-scaffold.md)：三种模板、发行包和收尾工作流的实际结果。
- [首发确认稿](docs/release-scope.md)：许可证建议、拟公开范围与待确认事项。
- [开发收尾](docs/finish-task.md)：M4 范围核对、检查、本地提交与独立推送。
- [项目规划](docs/project-plan.md)：方案、范围、工作流、里程碑与验收标准。
- [项目维护约定](AGENTS.md)：维护本仓库时使用的规则。

## 目录职责

| 目录 | 职责 |
| --- | --- |
| `rules/` | 分发到使用者电脑的全局规则 |
| `standards/` | 通用、前端和后端规范及示例 |
| `skills/` | 规范提取、项目初始化和开发收尾工作流 |
| `templates/` | 项目规则、任务配置及空白工程模板 |
| `scripts/` | 项目初始化、开发收尾及安装生命周期工具 |
| `versions/` | 版本策略与兼容说明 |
| `docs/` | 规划与维护文档 |

## 默认策略

- 文档和新增注释使用中文，技术标识符保持原样。
- 开发任务完成并通过必要检查后，默认自动本地提交；推送需要单独启用。
- 全局规则保留既有内容，安装器仅管理带有本工具包标记的区块。
- 业务项目记录规范版本，工具包升级不自动改写已有业务项目。
- 本机绝对路径等配置与可共享规范分离。

## 下一步

维护者已确认本机验收通过。M5 的第二台电脑验收、许可证与公开发布范围仍待确认。规范提取 Skill 和已有业务项目的规范升级仍待实现。详见[项目规划](docs/project-plan.md)。
