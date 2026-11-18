# M5 工程创建与分发验证记录

验证日期：2026-11-18。固定提交：`30374ed9d12a34b35b4a600fb6cd4cc466fd4298`。环境是 macOS 27.0 arm64、Git 2.49.0、Python 3.14.3、Node.js 24.19.0、pnpm 11.20.0。FastAPI 工程使用 Python 3.12.12 和 uv 0.10.7。

## 工具包与生成项目

执行 `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`，71 项测试全部通过。覆盖 M2 至 M4 回归以及 M5 创建预览、三套组合、重复运行、规划仓库与暂存保留、冲突、写入失败回滚和检查失败。Ruff 静态与格式检查、文档本地链接以及 Git 空白检查通过。

从固定提交构建发行包并校验 SHA-256。另一个无源码克隆的临时目录通过发行包完成 M2 安装；从安装副本执行以下命令，三种组合的退出码均为 0：

```bash
ai-dev-standards create projects/react-vite --template react-vite --apply --install --verify
ai-dev-standards create projects/react-fastapi --template react-fastapi --apply --install --verify
ai-dev-standards create projects/react-nestjs --template react-nestjs --apply --install --verify
```

| 组合 | 实际通过的检查 |
| --- | --- |
| React | 5 项，包含格式、Lint、类型、两项 Vitest 交互测试、生产构建 |
| React + FastAPI | 10 项，另含 Ruff 静态及格式检查、mypy、健康接口和 OpenAPI 测试、前后端连通与失联验证 |
| React + NestJS | 11 项，另含后端格式、Lint、类型、Fastify 注入测试、构建及前后端连通与失联验证 |

浏览器访问三种工程。两套全栈显示实际 API 在线状态。关闭 FastAPI 后显示失联，重启后点击重新检查恢复。还验证了独立前端状态、未匹配路由返回首页、展示偏好刷新后保留及 380 像素宽页面无横向溢出。

## 安装与开发收尾

- 发行包的预览、安装、诊断和卸载退出码均为 0。卸载后已生成项目仍在，发行包可以直接创建另一个项目。
- 以 M2 提交为来源部署旧副本，再用本次发行包预览并应用更新。重复更新返回 `unchanged`，新版命令可用。卸载后保留用户追加的全局规则，移除工具包拥有的 Skill 链接。
- 对一次性 React 工程执行 M4，运行生成项目中登记的 5 项检查，只提交 `apps/web/index.html`，提交为 `b12d635f90b0fbc68b120be809c7f8e69c1abec2`。预先暂存的 `README.md` 仍在暂存区。

M5.4 已在同一台 Mac 的不同目录和隔离用户布局完成发行文件与工作流演练。维护者确认本机和第二台电脑均已通过验收。该结果由维护者反馈，本文的命令及计数对应上文记录的验证环境。许可证选择及正式标签和公开发布仍待完成。使用步骤见[创建工程与验证](../project-scaffold.md)，首发范围见[发布确认稿](../release-scope.md)。
