# 工作流 Skills

| 名称 | 状态与职责 |
| --- | --- |
| [project-bootstrap](project-bootstrap/SKILL.md) | 已实现：识别技术栈与差异，通过生成器为项目建立规范入口及采用记录。 |
| [extract-standards](extract-standards/SKILL.md) | 已实现：从参考项目提取可复用规范，区分明文规则、实现惯例和待确认项，记录来源及其公开范围。 |
| [finish-task](finish-task/SKILL.md) | 已实现：核对精确任务范围，运行实际检查并按策略本地提交；推送单独授权与重试。 |
| [git-commit-message](git-commit-message/SKILL.md) | 点名调用后按实际 diff 生成中文提交信息，默认提交并推送。也支持仅预览或仅提交。 |

Skill 随完整工具包分发，安装器为工作流建立用户级入口链接。普通开发任务使用 `finish-task` 收尾。只想预览时，可以在项目会话中发出「`$git-commit-message` 只生成提交信息」。已有个人版的安装选择及新会话加载检查见[安装说明](../docs/installation.md#保留个人版提交-skill)。
