# 首次发布范围

首发标签为 `v0.1.0`，发布渠道为现有公开的 [GitHub 仓库](https://github.com/chengit16/ai-dev-standards)。维护者已确认本机和第二台电脑验收通过。[M5 验证记录](verification/m5-scaffold.md)

## 许可证

维护者确认采用 MIT，版权署名为 `2026 chen`。许可适用于有权授权的工具包代码、规则、文档、Skills 和模板。[完整许可文本](../LICENSE)

正式版本在仓库根目录保留 `LICENSE`，如有适用的第三方声明则随附 `NOTICE`。发行包与安装副本携带这些声明。依赖由模板的包管理器按锁文件安装，各依赖沿用自身许可。

## 公开范围

| 公开位置 | 内容 |
| --- | --- |
| GitHub 源码与历史 | CLI、规则、三项 Skill、三套空白工程模板及其依赖声明与锁文件、用户文档、测试和合成样例。 |
| GitHub Release | 固定提交的 `.pyz`、同名 `.sha256`、使用说明与兼容范围。GitHub 另提供标签对应的源码归档。 |
| 本机保存 | 实际业务项目及数据、参考项目源码、本机配置、浏览器记录、安装备份、凭证、依赖目录与测试产物。 |

首发面向已验证的 macOS 环境。项目入口包括[已有工程接入规则](project-bootstrap.md)和[从模板创建并验证](project-scaffold.md)。[GitHub Release 说明](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)

## 参考来源

发布源码和发行包保留通用规则与技术取舍，参考项目的精确定位留在维护者本地。本次发行延续现有 Git 历史，较早的公开提交仍可查阅。任何直接沿用的第三方内容按其自身许可和授权条件处理。

GitHub Release 使用 `v0.1.0` 标签，附带从同一提交构建的 `.pyz` 和 `.sha256`。

维护者可以按[发版指南](github-release.md)构建后续版本并核对公开附件。
