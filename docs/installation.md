# 安装、诊断、更新与卸载

M2 提供 `scripts/toolkit.py`。当前完成 macOS 隔离验证，使用 Python 3.11+ 标准库和 Git；显式恢复使用 POSIX 文件锁，Windows 及其他操作系统尚未验收。所有写操作默认预览，只有添加 `--apply` 才应用。本次开发未向真实用户目录安装，也未更改现有全局配置。

## 本机首次验收

在完整工具包仓库根目录运行：

```bash
python3 scripts/toolkit.py install
```

核对输出的目标目录、拟变更资源与文件清单。默认将全局区块写入所选 Codex home 的 `AGENTS.md`，在其中保留一份完整工具包副本，并为两个 Skill 建立链接。

如果检测到旧 `git-commit-message`，安装器会停止。明确保留旧入口时，先预览，再应用：

```bash
python3 scripts/toolkit.py install --legacy-policy keep
python3 scripts/toolkit.py install --legacy-policy keep --apply
python3 scripts/toolkit.py doctor
```

没有旧入口时可直接使用 `python3 scripts/toolkit.py install --apply`。`keep` 不改写或禁用旧 Skill；受管全局规则将默认收尾路由到 `finish-task`，旧入口只在用户明确点名时使用。旧 Skill 的自动匹配不能额外授权推送。以后更新会保留已经记录的选择。

`doctor` 返回 `deployed` 只表示受管文件、链接与清单一致，`host_loading` 始终为 `not_verified`。下一步在目标项目新建会话：

1. 请助手指出本次读取的全局与项目规则来源，并确认中文文档、默认本地提交及推送单独授权。
2. 确认 `project-bootstrap` 和 `finish-task` 可发现，真实路径指向本次安装副本；入口为符号链接时先解析实际目录。
3. 在一次性测试仓库完成[项目初始化](project-bootstrap.md)，核对目录、差异与来源信息，重复执行应无需写入。
4. 修改一个小功能并运行[开发收尾](finish-task.md)，验证真实检查、提交 SHA 与已有改动保留。未明确授权时不推送。

文件部署、工作流实际运行和宿主新会话加载是三个不同层次。用户完成以上步骤后才能记录本机安装验收通过；跨电脑分发及正式版本标签仍属于 M5。

## 路径与资源归属

| 位置 | 用途 |
| --- | --- |
| `CODEX_HOME/AGENTS.md` | 只管理 GLOBAL BEGIN/END 标记之间的工具包区块 |
| `CODEX_HOME/ai-dev-standards/bundle/` | 完整运行副本，包含规范、Skills、脚本、模板与使用文档 |
| `CODEX_HOME/ai-dev-standards/manifest.json` | 记录安装布局、来源、文件指纹及旧 Skill 选择 |
| `HOME/.agents/skills/project-bootstrap` | 指向安装副本中初始化 Skill 的链接 |
| `HOME/.agents/skills/finish-task` | 指向安装副本中收尾 Skill 的链接 |
| `CODEX_HOME/.ai-dev-standards-backups/` | 操作前后快照与恢复日志，卸载后仍保留 |
| `CODEX_HOME/.ai-dev-standards.lock` | 并发与中断保护，记录进程、主机和对应事务 |

未设置 `CODEX_HOME` 时默认使用 `~/.codex`；也可显式指定 `--codex-home`。Skill 用户目录仍基于 HOME，不跟着 CODEX_HOME 移动，因此同一用户不能把同名两个 Skill 同时安装到两个不同 profile。

此布局依据[官方 AGENTS 机制](https://learn.chatgpt.com/docs/agent-configuration/agents-md)及[官方 Skill 发现机制](https://learn.chatgpt.com/docs/build-skills)核对：全局覆盖文件优先，用户 Skill 目录支持符号链接，同名 Skill 不自动合并。安装器只检查所选用户布局；项目级、管理员、插件入口、运行中的宿主状态以及分层配置覆盖，仍需新会话核实。

安装不修改 `config.toml`、旧 Skill、其他全局规则、业务仓库或 Git 全局配置。非空 `AGENTS.override.md`、显式禁用新 Skill、同名目录或声明同名的用户 Skill、无归属记录的旧内容都会停止安装。配置按所选 home 中的 `skills.config` 顺序检查 name/path 与 enabled；不自动修改宿主禁用设置。若全局规则较大，doctor 提醒核对加载预算，不自行调整宿主限制。

仓库根 `AGENTS.md` 在 bundle 中仅作为维护文档保留；安装到全局的正文来自独立的 [rules/global.md](../rules/global.md)。源码目录不是运行依赖，删除原克隆后安装副本仍可执行 M3/M4、诊断及卸载；安装或更新必须使用独立来源，不能从安装副本内部覆盖自身。

## 隔离演练

`--home` 指向已有的临时用户目录，指定后不会继承真实 `CODEX_HOME`，除非同时明确提供 `--codex-home`。以下命令不会安装到真实用户配置目录：

```bash
trial_home=$(mktemp -d)
python3 scripts/toolkit.py install --home "$trial_home"
python3 scripts/toolkit.py install --home "$trial_home" --apply
python3 scripts/toolkit.py doctor --home "$trial_home"
python3 scripts/toolkit.py uninstall --home "$trial_home" --apply
```

隔离模式用于验证文件操作，不会使当前真实 Codex 会话读取该临时用户目录。不要把隔离结果当作当前宿主加载通过。

## 更新

先在独立克隆中选定要采用的提交或版本，核对来源变更，再执行：

```bash
python3 scripts/toolkit.py update
python3 scripts/toolkit.py update --apply
python3 scripts/toolkit.py doctor
```

更新不联网、不自动 pull、不创建标签。预览列出变化资源及文件；实际执行前备份旧版完整资源和全局入口，发布后核对哈希。相同内容重复运行不改写文件或创建新备份；已安装且来源不同时，install 会要求使用 update。

全局区块之外的追加与修改按当前内容保留，不恢复历史整份 AGENTS 覆盖用户后续编辑。受管副本、受管区块或链接被修改、缺失，或目录中新添了文件和空目录时会停止，保留现场供比较。当前不提供强制覆盖或自动合并用户对受管资源的修改。

安装清单记录 Git 提交和来源内容集合 SHA-256；未提交来源标记为工作树快照，不能当作发行版。无 Git 元数据的来源使用内容指纹并保留 Git 字段为空。安装副本中的 `_toolkit-source.json` 使 M3 初始化结果继续记录来源提交和安装指纹；文件被手工改动时不能伪称干净版本。工具包更新不会自动升级已有业务项目规范。

## 卸载

```bash
python3 scripts/toolkit.py uninstall
python3 scripts/toolkit.py uninstall --apply
```

仅移除仍与清单一致的两个链接、安装副本和受管全局区块。用户原有内容及卸载前新增内容保留；原先不存在且卸载后为空的 AGENTS 才删除，原先的空文件保持存在。遇到归属冲突会整体停止，不能通过删清单绕过检查。

备份记录不会自动删除，空的父目录可能保留。备份含旧规则和历史工具包内容，目录默认只允许当前用户访问；确认不再需要恢复后可自行归档，不要在恢复前清理。业务项目中已生成的规范也不会随用户级卸载删除。

## 失败和中断恢复

可捕获的写入错误会先确认目标仍是本次操作的前态或后态，再回滚。无法确认归属或回滚失败时保留锁与事务记录，不继续覆盖。多资源发布不是跨文件系统事务，强制退出或掉电可能留下中间状态。

先确认没有安装、更新、卸载或恢复进程正在运行，然后执行：

```bash
python3 scripts/toolkit.py doctor
python3 scripts/toolkit.py recover --transaction <doctor报告的事务目录>
python3 scripts/toolkit.py recover --transaction <同一事务目录> --apply
python3 scripts/toolkit.py doctor
```

使用隔离布局时，上述命令也要带相同的 `--home`/`--codex-home`。恢复验证事务归属、布局、锁与事务对应关系、进程状态、备份哈希和当前资源；只有本次已触碰且仍可确认的资源才回滚。恢复过程中由系统文件锁避免两个恢复进程同时写入；活动 PID、其他主机、后续用户修改、备份损坏或不匹配事务都会停止。PID 被复用时保守地视为活动进程。

已完成或已回滚的事务若仅剩锁，恢复会核实终态后清理对应残留锁，不把完成安装回退。事务日志还未建立时、锁丢失、临时发布目录残留或现场无法归属时，自动恢复可能不足：先保留副本，比较快照及当前状态，再人工处理，不能直接删锁、删目录或还原整份旧配置。未验证所有断电、磁盘故障与对抗性并发情形。

## 验证与后续

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

本次实际结果见 [M2 验证记录](verification/m2-installation.md)。M2 交付源码与隔离验证；正式版本发布、许可证选择、本机和另一独立环境验收属于后续 M5。规范提取 Skill 仍待实现，不因安装器完成就把它计为已交付。
