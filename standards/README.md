# 开发规范库

先采用通用规范，再按项目实际职责选择前端和后端规范。前后端可独立组合，不要求项目同时使用两套后端。

| 规范 | 适用范围 |
| --- | --- |
| [通用工程规范](common/engineering.md) | 所有项目：边界、中文注释、验证、配置和提交。 |
| [中文代码注释规范](common/comments.md) | 所有技术栈必读：复杂流程、阶段编号、长函数阈值、TODO 与检查要求。 |
| [React 前端规范](frontend/react-vite.md) | React、TypeScript、Vite，以及选定的组件、样式、路由、状态和 HTTP 方案。 |
| [NestJS 与 Fastify 后端规范](backend/nestjs-fastify.md) | 新建常规业务 API 的默认选项。 |
| [FastAPI 后端规范](backend/fastapi.md) | 依赖 Python 生态的 API，例如文档处理、知识检索和模型服务。 |

例如，新的管理后台采用通用规范、React 前端规范和 NestJS 后端规范；新的知识库可沿用同一套前端并选择 FastAPI。只有前端或只有后端的项目只采用对应规范。

已有项目记录实际技术栈、采用版本和有效差异，不因引入本规范自动改写现有实现。各规范记录来源提交与采用理由，参考项目只用于维护时核对；日常使用可独立阅读本仓库文档。当前可以手动选用，也可通过[项目初始化](../docs/project-bootstrap.md)生成仓库内副本。需要启用用户级规则和工作流时，参见[安装说明](../docs/installation.md)。

文件头、公开接口和字段的具体写法及各类文件最低说明，位于各技术栈的“中文注释规范”章节；必须与共用注释规则一起读取。首版遗漏及处理范围见[完整性核对记录](../docs/standards-completeness-review.md)。
