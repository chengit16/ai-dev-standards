# 创建工程与验证

统一命令支持三种模板，生成项目独立保存。需要 Python 3.11+、Git。生成工程运行检查时需要 Node.js 24.19 和 pnpm 11.20.0。FastAPI 组合另外需要 Python 3.12 和 uv。

| 模板 | 目录 | 验证内容 |
| --- | --- | --- |
| `react-vite` | `apps/web` | 前端格式、Lint、类型、交互测试与生产构建 |
| `react-fastapi` | `apps/web`、`apps/api` | 前端检查、Ruff、mypy、pytest，以及前后端连通与失联检查 |
| `react-nestjs` | `apps/web`、`apps/api` | 前后端格式、Lint、类型、构建、Fastify 注入测试及连通与失联检查 |

## 从本地工具包使用

在工具包源码目录执行。将 `../my-app` 换成目标路径，父目录须已存在。

```bash
scripts/ai-dev-standards create ../my-app --template react-fastapi
scripts/ai-dev-standards create ../my-app --template react-fastapi --apply --install --verify
scripts/ai-dev-standards verify --project ../my-app
```

第一条只预览输出文件和计划执行的步骤。第二条生成基础工程、接入 [M3 规范](project-bootstrap.md)，从锁文件安装依赖，并执行采用配置记录的检查。单独使用 `--apply` 可以先生成文件。需要新建 Git 仓库时加 `--git`，任务提交交给 [M4 收尾](finish-task.md)。

`verify` 会执行项目 `.ai-dev-standards/project.json` 登记的命令，只对信任的项目执行。检查失败时打开输出定位失败项，工程仍可继续修改。补装依赖或修复后重新执行 `verify`。模板启动方式见生成的 `README.md`。

目标已经包含 `README.md`、`docs/` 或仅有规划文件的 Git 仓库时，预览与应用都加 `--existing`。原 README 和规划资料继续保留，生成的启动说明位于 `DEVELOPMENT.md`。已有 `.gitignore` 等同名输出会报告冲突。已有功能代码的工程使用 `bootstrap` 接入规范。重复创建会检查原始模板产物与 M3 规则，代码已经改动后使用 `verify`。

创建被强制中断时先核对锁中的 PID、临时目录与原有 Git 状态。留存副本，并比较临时文件、创建记录及原有内容。只在确认进程已结束、归属明确后处理残留；涉及 M3 的中断按其[恢复说明](project-bootstrap.md#重复执行与冲突)处理。

## 使用固定版本的发行文件

维护者从包含 M5 的固定提交构建发行文件。以下使用当前已提交版本，也可将 `HEAD` 换成具体提交或标签。

```bash
scripts/ai-dev-standards release --ref HEAD --output /tmp/ai-dev-release
```

命令输出一个带提交标识的 `.pyz` 文件与对应的 `.sha256` 文件。将两者放在同一目录，并从可信来源核对校验值。下面命令从下载目录定位该组文件：

```bash
release_file="ai-dev-standards-你的提交标识"
shasum -a 256 -c "$release_file.sha256" &&
  python3 "$release_file.pyz" create ../my-app --template react-fastapi
```

直接执行发行包即可使用项目命令。需要安装 Codex 规则和 Skills 时，使用同一发行包按[安装说明](installation.md)依次预览、应用与诊断：

```bash
python3 "$release_file.pyz" install --legacy-policy keep
python3 "$release_file.pyz" install --legacy-policy keep --apply
python3 "$release_file.pyz" doctor
```

常用命令可通过当前 shell 的 `PATH` 调用。默认安装目标如下，使用自定义 `--codex-home` 时替换目录：

```bash
export PATH="${CODEX_HOME:-$HOME/.codex}/ai-dev-standards/bundle/scripts:$PATH"
ai-dev-standards --help
```

安装目录内的短命令随 M2 一起更新及卸载。项目记录模板和规范来源，保存在 `.ai-dev-scaffold/manifest.json` 与 `.ai-dev-standards/manifest.json`。使用新发行包更新时运行 `update`，流程同样先预览。

当前提供本地发行文件构建与实测用法。公共发布地址和正式标签将在许可证与发布范围确定后补充。
