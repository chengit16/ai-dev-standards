# 首版规范完整性核对记录

日期：2026-11-16。被核对版本：`cf70da4`。本记录描述本次提取修订，不是自动检查器或项目代码合规报告。

## 核对依据

- 用户提供的两张截图：Release Harbor 前端、后端规范中的文件头、公开接口、复杂流程和长度要求。
- `release-harbor@051696e909f2aabe22d9cc8f12dce183eaeee1b9`：`docs/governance/frontend-code-standards.md`、`docs/governance/backend-code-standards.md`。
- `KnowSpace@cca5e6696ee8c38e919042df8cd144faaa97e1a8`：`docs/2026-09-23/开发基线/governance/frontend-code-standards.md`、同目录 `backend-code-standards.md`。
- 已确认的前端选型及三项目差异，以各套规范的来源与取舍为准；本次不改变技术栈决策。

## 遗漏与处理

| 范围 | 首版问题 | 本次处理与权威位置 |
| --- | --- | --- |
| 适用条件 | 文件头只提职责改变，遗漏行为改变；公开声明清单不全。 | [前端](../standards/frontend/react-vite.md#中文注释规范)、[NestJS](../standards/backend/nestjs-fastify.md#中文注释规范)、[FastAPI](../standards/backend/fastapi.md#中文注释规范)补齐触发条件、声明范围和例外。 |
| 公开字段 | Props 逐字段、Options、Hook 返回对象、跨模块配置和字段语义缺失。 | 前端补字段与回调说明及示例；NestJS 补默认、省略、单位、时区、所有权；Python 补 Field 与 Protocol 语义。 |
| 声明位置 | 装饰器前 JSDoc、未导出端点和用例、Python future import 顺序缺失。 | 各技术栈中文注释章节明确位置与范围。 |
| 流程与长度 | 将必须编号弱化成可编号，省略四档阈值、有效行数和保留理由。 | [共用注释规则](../standards/common/comments.md#必须说明的流程)统一维护，三套规范强制引用。 |
| 文件职责 | 缺少页面、Hook、Store、Controller、Adapter、Worker 等最低说明表。 | 各技术栈补表，区分数据来源、依赖方向、写入权与副作用。 |
| 注释维护 | TODO/FIXME/HACK、责任和退出条件、生成源处理及语义检查边界不完整。 | [共用注释规则](../standards/common/comments.md)补齐，保留例外和按实际修改渐进执行。 |
| 文件规模 | 只谈职责，没有来源规范的文件规模预警。 | [通用规模预警](../standards/common/engineering.md#文件规模与职责预警)统一维护前后端范围。 |
| React 编写 | 纯渲染、稳定 key、Effect 清理、公共组件兼容、有限 Memo、错误恢复与可访问性不完整。 | [前端组件规则](../standards/frontend/react-vite.md#组件样式与性能)补齐；保持固定选型与缓存按需引入。 |
| 后端一致性 | 时间语义、损坏保护、条件写入、稳定分页、批量上限、追踪与资源上限不完整。 | [通用服务边界](../standards/common/engineering.md#前后端共用的服务边界)补齐；Python 补命名、迁移、ORM 边界及按需扩展要求。 |
| 测试与交付 | 缺少跨端必读、合成夹具、可控依赖及授权拒绝矩阵。 | [通用验证](../standards/common/engineering.md#验证配置与提交)和各技术栈验证章节补齐。 |

## 有意保留为差异的内容

| 来源内容 | 处理理由 |
| --- | --- |
| 不同引号、分号与依赖版本范围，固定 Node/React 版本 | 已确认沿用项目配置，版本兼容在初始化时验证；不以旧参考版本作为跨项目强制版本。 |
| main-platform 内部组件库、微前端桥接、菜单协议和特定错误码 | 属于业务基础设施；已确认直接采用 Ant Design 和统一 Axios 分层，不整份迁移历史 Client。 |
| KnowSpace 默认查询库及编辑器、表格、角色矩阵、文件格式范围 | 已确认 Zustand 管客户端状态，查询缓存按需采用；产品组件、业务角色和解析范围由项目需求决定。 |
| Release Harbor 发布渠道、授权时限、页面名称、断点及专有凭据进程 | 保留权限、可信上下文和副作用边界，具体协议和视觉值不进入通用规则。 |
| 历史文档中的“尚无后端命令”、只允许 local 等阶段描述 | 固定提交中已存在后续实现；不把历史阶段状态转写为工具包通用限制。 |
| 参考项目的检查命令、任务编号、报告目录及自动检查器 | 工具包目前只有规范文档；不复制私有路径、未实现脚本或宣称现有自动门禁覆盖。 |

上述检查按来源章节覆盖可复用主题及截图条款；不表示逐行复制原规范，也未对三个参考项目做全仓代码合规审计。规则条款只在 standards 中维护，本记录用于追溯本次修订。
