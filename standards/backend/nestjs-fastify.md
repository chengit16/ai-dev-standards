# NestJS 与 Fastify 后端规范

适用于 TypeScript 管理后台、业务 API、工作台及第三方接口集成。新建常规业务服务默认选用此套规范，并遵循[通用工程规范](../common/engineering.md)。已有项目保留已验证的接口和部署约定。

## 技术与模块

- 使用 Node.js、TypeScript、NestJS 和 Fastify adapter，由 pnpm 管理依赖。启用 `strict` 和 `noUncheckedIndexedAccess`，使用 `import type` 标注类型导入。公开入口明确输入和返回类型；外部输入从 `unknown` 开始校验。
- 默认从一个 API 服务开始，按业务域组织 Module。Controller 负责 HTTP 参数、响应和错误映射；Service 负责用例编排；领域层负责业务规则和状态转换；存储与外部 SDK 实现明确的端口，由 Module 装配。
- 当多个应用确需共享时，再将领域或公开契约提取到独立包，例如 `packages/domain` 和 `packages/contracts`。领域代码不依赖 NestJS、前端或第三方 SDK；前端不直接使用存储对象、内部 DTO 或 SDK 类型。
- 类、接口与类型使用 `PascalCase`，函数和变量使用 `camelCase`。NestJS 职责文件使用 `*.module.ts`、`*.controller.ts`、`*.service.ts`。保持既有公开字段命名。

## 公开接口

- 在入口校验参数、请求体与第三方响应，按需拒绝安全敏感请求中的未知字段。DTO 只描述传输数据，Controller 负责把数据转换为用例输入。
- TypeScript 工作区可维护共享公开契约和运行时守卫；也可从 OpenAPI 生成客户端契约。以项目选择的一处来源为准。响应只返回公开字段，敏感信息或执行器的本机路径不能穿透到接口。
- 错误在 HTTP 边界映射为公开状态和稳定业务语义。例如资源更新遇到版本冲突时，返回项目约定的冲突状态和错误码，调用方可保留草稿并重新读取当前版本。

## 存储与任务

- 在线业务需要关系型存储时默认 PostgreSQL。Node 侧数据库客户端、ORM 和迁移工具由项目确定；迁移、事务和恢复遵循通用规范。本机工具使用文件存储时，明确单进程限制及并发写入保护。
- 长时间执行或需要独立凭证的操作交给 Worker 或可信执行器。API 负责受理、状态和权限，Worker 从可信输入核对任务与目标，外部 SDK 及重试策略留在适配层；简单项目不预装队列。
- 认证使用项目选择的会话或令牌。本机专用且未认证的 API 仅在回环地址提供；跨设备部署按独立可信边界验证，不沿用本机的信任前提。

## 中文注释与验证

- 新增手写 TS 或 Node 脚本、以及职责有实际变化的文件，在首个 `import` 前提供中文 `@description`，有 shebang 则放在其后；生成文件、第三方文件和纯再导出入口免加文件头。
- 公开用例、Controller 端点、端口与复杂 Adapter 补 JSDoc，说明可信输入、返回事实及事务、并发或副作用边界。端口已说明的通用约束不在每个实现中重复。
- 运行项目可用的类型、测试、构建和格式检查。优先用 Fastify 注入测试验证 HTTP 边界，用合成数据测试授权、存储冲突和历史兼容，用可控替身覆盖外部超时和结果不明；以行为而非私有实现细节断言。

## 参考与取舍

提取日期：2026-11-16。参考 `release-harbor@051696e909f2aabe22d9cc8f12dce183eaeee1b9` 的 `docs/governance/backend-code-standards.md`、`docs/ARCHITECTURE.md`、`apps/api/package.json` 和 `tsconfig.json`。

采用该项目明确的依赖边界、运行时校验和执行器隔离。参考项目同时有本机文件存储和独立在线验证入口；本规范将二者按部署场景选用，不复用业务专有的凭据协议和发布流程。
