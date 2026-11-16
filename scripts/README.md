# 工具脚本

已实现 `project_bootstrap.py`：根据显式采用配置预览或生成项目规则，使用 Python 3.11+ 标准库和 Git。内部模块位于 `bootstrap/`，用法与冲突边界见[项目初始化](../docs/project-bootstrap.md)。

初始化脚本默认只预览，添加 `--apply` 才写入；不运行项目检查、不安装依赖、不暂存或提交。

已实现 `finish_task.py`：预览精确任务范围，执行真实检查并按策略本地提交；推送使用独立子命令核对目标与待推送历史。内部模块位于 `finish/`，用法和恢复边界见[开发收尾](../docs/finish-task.md)。初始化与收尾入口均不修改用户级配置。

已实现 `toolkit.py`：安装、更新、诊断、卸载和显式恢复，内部模块位于 `lifecycle/`。默认预览，--apply 才写入；用法及隔离布局见[安装说明](../docs/installation.md)。只管理清单内文件、链接和区块，备份保留以便核查。
