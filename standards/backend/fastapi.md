# FastAPI 后端规范

适用于需要 Python 生态的业务 API，例如文档处理、知识检索或模型相关服务。配合[通用工程规范](../common/engineering.md)使用；仅需要普通业务 API 时也可选用 [NestJS 与 Fastify](nestjs-fastify.md)。

## 技术与模块

- 使用 Python、FastAPI、Pydantic 和 uv。使用 Ruff 完成格式与静态检查、mypy 做严格类型检查、pytest 测试，维护 `uv.lock`。公共函数声明参数和返回类型，外部未知值先校验，类型例外限定在具体边界。
- Router 和请求/响应 Schema 放在业务模块的 `api/`；`application/` 负责编排，`domain/` 维护领域规则，`infrastructure/` 实现存储与外部适配。应用入口装配依赖。模块只在有实际职责时拆分。
- 使用应用工厂集中装配 Router、Middleware、异常映射和生命周期。HTTP 的 `Depends`、Pydantic 请求模型和 ORM 模型均不进入领域规则。Worker 不导入 API 启动模块。

## HTTP 与契约

- Router 声明请求/响应模型、稳定的 OpenAPI `operation_id` 以及已知错误。对安全敏感请求拒绝合同以外的字段。区分 Pydantic 请求/响应、应用输入、领域对象、ORM 和任务事件。
- 以实际路由和 Schema 生成的 OpenAPI 为契约来源，变更后同步调用方类型和接口测试。错误在入口映射为通用规范约定的状态与错误信息。
- 只有确实使用异步 I/O 的调用链才使用异步方式；阻塞模型调用和重计算按实际并发与资源需求放到独立执行边界。

## 持久化与任务

- 需要关系型存储时使用 PostgreSQL、SQLAlchemy 和 Alembic。Session 在请求或任务的有限作用域内管理，写用例明确事务，Repository 不自行决定业务提交。唯一约束和必要的工作区条件落实到存储层。
- 通过版本化 Alembic 迁移变更结构；已进入共享历史的迁移不原地修改。检查空库和有代表性旧数据的升级，可回填时说明批次与失败恢复，应用启动不能代替正式迁移流程。
- 从单个 API 服务起步。需要后台导入、索引等可靠任务时，使用独立 Worker 和 Celery + Redis。载荷用版本与稳定 ID 引用数据，Worker 重新读取当前状态并去重；数据库保存业务任务事实，Redis 不作为唯一记录。
- 当业务数据与待投递任务必须一起持久化时，用同一事务写业务变更和待发送事件；事务提交后再投递，由 Worker 幂等消费。向量字段、对象存储、SSE 和外部模型适配按项目实际需求加入。

## 中文注释与验证

- 手写 Python 模块使用首条语句的中文模块级 docstring；公开顶层类和函数及公开用例说明职责、前置条件和可能结果。端口说明事务、锁、授权或失败语义，生成迁移保留固定格式，手写回填与不可逆步骤补充说明。
- 运行项目配置的 Ruff、mypy 和 pytest。接口测试覆盖状态码、授权和公开字段；数据库测试以可清理的合成数据验证真实约束和迁移；任务测试覆盖重投、乱序、失败状态和恢复。

## 参考与取舍

提取日期：2026-11-16。参考 `KnowSpace@cca5e6696ee8c38e919042df8cd144faaa97e1a8` 的 `docs/2026-09-23/开发基线/governance/backend-code-standards.md`、`pyproject.toml`、`scripts/verify` 和 `alembic/versions/`。

采用该项目明确的类型、职责分层、迁移和后台任务规范。其现有实现并非每个模块都已使用独立存储端口；本文将端口与明确的事务归属作为新功能的设计方向，不要求为简单用例机械封装或批量改造历史代码。
