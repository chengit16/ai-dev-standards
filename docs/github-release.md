# MIT 许可证与 GitHub 发版指南

本指南面向维护者，记录 `ai-dev-standards` 的发版步骤。首发 `v0.1.0` 使用 MIT 许可证，版权署名为 `2026 chen`，对应提交 `f4e2d8ddfafaad29079ddf8afa988c7fba2a3fcf`。可以先打开已发布的版本，对照标签、说明和下载附件。[v0.1.0 发布页](https://github.com/chengit16/ai-dev-standards/releases/tag/v0.1.0)

| 对象 | 作用 |
| --- | --- |
| `LICENSE` | 说明别人可以怎样使用、修改和分发工具包。 |
| Git 标签 | 将版本号固定到一个源码提交。 |
| GitHub Release | 为标签提供面向使用者的发布说明、下载附件和源码归档。 |
| `.pyz` 与 `.sha256` | 可用 Python 执行的工具包，以及验证该文件内容的 SHA-256 校验文件。 |

## 以后发版怎么走

先把要交付的改动测试并提交到 `main`，再按下面六步发布。工作流假定你有目标仓库的写权限，并在同一个终端里运行命令，方便复用版本号、提交号和产物路径。

| 从 `v0.1.0` 开始 | 版本号示例 |
| --- | --- |
| 修复保持兼容的问题 | `v0.1.1` |
| 新增保持兼容的功能 | `v0.2.0` |
| 变更已有命令或项目配置的兼容性 | 在发布说明中标明影响和迁移步骤。`0.x` 是初期开发阶段，可通过递增次版本区分此类变更。 |

版本号参照 [Semantic Versioning](https://semver.org/)。只更新维护文档时，可随下一次代码发版一起交付。每次公开发行使用一个新的标签。

## 1. 确认许可证和公开范围

首次发布时，将完整的 MIT 许可文本存为仓库根目录的 `LICENSE`，填入授权方确认的版权年份与署名，并在 README 链接该文件。本项目已经完成这一步，后续版本沿用仓库中的许可文本。MIT 允许使用、修改、商用和分发，分发副本或实质部分时需保留版权及许可声明。[MIT 许可原文](https://opensource.org/license/mit) · [仓库 LICENSE](../LICENSE)

发布前分别查看将要推送的提交和将要打包的文件。该项目公开通用规则、CLI、Skills、模板和用户文档。参考项目的精确定位、业务数据与本机配置留在本地。公开分支的新提交会让其新增祖先历史也出现在远端。若某项内容曾经随公开提交发布，清理最新快照后仍需按历史的实际可见情况判断。第三方材料按其自身授权与署名要求处理。[已确认的公开范围](release-scope.md)

## 2. 选定要发布的提交

以下命令在工具包源码仓库根目录运行。命令用 `v0.1.1` 演示未来一次发版，请按实际版本替换。目前的首发是已经存在的 `v0.1.0`。

```bash
release_version=v0.1.1
git status --short --branch
git remote get-url origin
git remote get-url --push origin
git fetch origin main --no-tags
git log --oneline origin/main..main
git diff --stat origin/main..main
git ls-remote --tags origin "refs/tags/$release_version"
git tag --list "$release_version"
git merge-base --is-ancestor origin/main main
```

确认当前分支为 `main`，工作区和暂存区干净，`origin` 的推送目标是 `chengit16/ai-dev-standards`。`git log` 列出推送时会新增的提交，`git diff` 用于查看最终文件变化。远端标签查询成功且无输出，再确认本地标签也为空。合并基准命令返回 0 表示本地 `main` 包含远端 `main`。发现历史分叉、查询失败或标签已存在时，先核对状态再继续。

根据变更运行适用的测试。本项目涉及初始化、开发收尾或生命周期工具时，运行以下回归测试。首发的工程模板、分发和双机验收记录可作为核对范围的参考。[M5 验证记录](verification/m5-scaffold.md)

```bash
release_commit="$(git rev-parse main)"
git diff --check origin/main.."$release_commit"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

准备发布说明时，可按上一个已发布标签查看这次变更。后续发版时把 `v0.1.0` 换成实际的上一版标签。

```bash
previous_version=v0.1.0
git log --oneline "$previous_version..$release_commit"
```

## 3. 从固定提交构建并校验发行包

用 Git 提交号固定构建来源，随后复用该提交号打标签。采用独立输出目录，便于选中同一次构建的两个附件：

```bash
release_dir="$PWD/local/releases/$release_version"
release_stem="ai-dev-standards-$(printf '%s' "$release_commit" | cut -c1-12)"
./scripts/ai-dev-standards release --ref "$release_commit" --output "$release_dir" &&
  (cd "$release_dir" && shasum -a 256 -c "$release_stem.sha256") &&
  python3 "$release_dir/$release_stem.pyz" --help
```

构建从提交快照读取文件，工作区的未提交更改不会进入发行包。输出文件名使用提交号的前 12 位。校验通过时，`shasum` 显示 `.pyz: OK`。可用下面的命令确认包中许可证和来源清单：

```bash
unzip -p "$release_dir/$release_stem.pyz" LICENSE
unzip -p "$release_dir/$release_stem.pyz" _toolkit-source.json
```

核对署名、`source.git_commit` 和 `source.working_tree_dirty`。后者应为 `false`。如果安装行为有变化，用临时用户目录演练，三条命令的状态应依次为 `deployed`、`deployed`、`uninstalled`：

```bash
release_home="$(mktemp -d)"
python3 "$release_dir/$release_stem.pyz" install --home "$release_home" --apply
python3 "$release_dir/$release_stem.pyz" doctor --home "$release_home"
python3 "$release_dir/$release_stem.pyz" uninstall --home "$release_home" --apply
```

## 4. 创建并推送标签

继续在同一个终端运行。标签应指向上一步已经打包的提交。下面的命令检查本地 `main` 是否仍指向该提交，再创建附注标签，并把分支和标签一起推送：

```bash
test "$(git rev-parse main)" = "$release_commit" &&
  git tag -a "$release_version" -m "$release_version 发布" "$release_commit" &&
  git push --atomic --no-follow-tags origin "$release_commit:refs/heads/main" \
    "refs/tags/$release_version:refs/tags/$release_version"
```

推送需要仓库写权限。本项目的 `origin` 使用 SSH，GitHub 网页上传则使用浏览器登录。命令以同一次远端事务更新 `main` 和指定标签。推送后核对远端。[Git 推送说明](https://git-scm.com/docs/git-push#Documentation/git-push.txt---atomic)

```bash
git ls-remote origin refs/heads/main "refs/tags/$release_version" "refs/tags/$release_version^{}"
```

刚完成推送时，`main` 和标签末尾带 `^{}` 的两行应显示 `release_commit`。附注标签自身那一行显示的是标签对象编号。推送中断时先查询远端。若本地标签已存在且 `git rev-parse "$release_version^{}"` 与发行提交一致，远端标签仍为空，就重试 `git push` 那一条。若 `main` 受保护，先按仓库要求合并变更，再按远端实际合并提交重新核对、构建和打标签。

## 5. 在 GitHub 网页创建 Release

1. 打开仓库的 [Releases](https://github.com/chengit16/ai-dev-standards/releases)，点 **Draft a new release**。
2. 在 **Choose a tag** 选择刚推送的标签。填写发布标题和说明，写明本次变更、运行环境、安装或升级入口。
3. 在附件区域同时上传本次构建的 `.pyz` 与同名 `.sha256`。页面中的 **Source code (zip)** 和 **Source code (tar.gz)** 是 GitHub 根据标签生成的源码归档。
4. 核对标签、标题、说明和两个附件。还需复核时选 **Save draft**，准备公开时选 **Publish release**。[GitHub 官方操作说明](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository#creating-a-release)

发布说明可按这个格式填写。下载命令中的文件名换成第 3 步构建出的实际文件名。

```markdown
## 本次变更

- 写清使用者能看到的变化和修复。

## 安装与升级

- 下载本页同一版本的 .pyz 和 .sha256，校验后用 Python 执行。
- 首次安装使用 install，已安装旧版使用 update。

## 兼容性与迁移

- 列出已验证环境，以及需要使用者调整的命令或配置。
```

如果分支和标签已经推送，但网页上传中断，先打开相应的 Release 或草稿核对状态。已有草稿时继续编辑该草稿，使用相同提交生成的两个附件完成发布。

## 6. 从公开页面下载并做最后验证

发布后打开对应的 Release，确认版本和提交正确，用公开附件链接下载两个文件。也可以继续在原终端运行下面的命令，把公开附件下载到新的临时目录后验证：

```bash
download_dir="$(mktemp -d)"
asset_base="https://github.com/chengit16/ai-dev-standards/releases/download/$release_version"
curl -fL "$asset_base/$release_stem.pyz" -o "$download_dir/$release_stem.pyz" &&
  curl -fL "$asset_base/$release_stem.sha256" -o "$download_dir/$release_stem.sha256" &&
  (cd "$download_dir" && shasum -a 256 -c "$release_stem.sha256") &&
  cmp "$release_dir/$release_stem.pyz" "$download_dir/$release_stem.pyz" &&
  cmp "$release_dir/$release_stem.sha256" "$download_dir/$release_stem.sha256" &&
  python3 "$download_dir/$release_stem.pyz" --help
```

一般使用者只需下载和校验，不需要本地构建副本。以已发布的 `v0.1.0` 为例，在下载目录运行：

```bash
shasum -a 256 -c ai-dev-standards-f4e2d8ddfafa.sha256 &&
  python3 ai-dev-standards-f4e2d8ddfafa.pyz --help
```

首发时核对了远端 `main` 与 `v0.1.0` 的目标提交，也核对了 GitHub 返回的两项附件 SHA-256，均与本地构建一致。使用者拿到这两个文件即可运行工具包，安装或更新步骤见[发行包使用方式](project-scaffold.md#使用固定版本的发行文件)。

如果发布后发现程序或附件有问题，保留已发布的标签和下载记录，用一个新版本发布修复。如果只是说明写错，可以编辑 Release 的说明。[编辑 Release](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository#editing-a-release)
