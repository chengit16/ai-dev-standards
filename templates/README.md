# 项目模板

[project-bootstrap/AGENTS.block.md](project-bootstrap/AGENTS.block.md) 是生成到项目根目录的受管规则入口模板。[采用配置示例](project-bootstrap/config.example.json) 供 Skill 或用户填写技术栈范围、检查和差异。

规范正文以 `standards/` 为权威来源，生成器只复制所选文档及本地链接依赖，不在此维护副本。PROJECT.md 和 manifest.json 由脚本按配置生成，均采用仓库内相对引用。

使用方式、幂等行为与冲突处理见[项目初始化](../docs/project-bootstrap.md)。

[finish-task/request.example.json](finish-task/request.example.json) 是收尾任务请求结构；填写审核过的精确文件与提交说明，检查及策略优先沿用 M3 采用配置，详见[开发收尾](../docs/finish-task.md)。

## 空白工程模板（规划中）

M5 计划在 `templates/projects/` 维护可组合的前端、FastAPI、NestJS 与公共基础配置，供创建器生成独立业务项目。模板范围、目录草案、规范接入与验证要求统一见[空白工程与创建流程规划](../docs/project-scaffold-plan.md)。该目录及创建命令尚未实现，本次不创建占位模板或空 Skill。

工程模板提供最小可运行代码与真实检查入口；规范正文仍由 `standards/` 单一来源经 M3 接入。生成后的应用代码归业务项目维护，不随工具包升级或卸载被覆盖、删除。
