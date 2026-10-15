# DocumentResearch · 论文日历

将 `daily-paper-search` 生成的 HTML 日报发布到 GitHub Pages，支持手机和 PC 阅读。发布后由 GitHub 托管，本机关闭不影响访问；阅读设备仍需联网。

网站：<https://seven-7-ding.github.io/DocumentResearch/>

## 日常使用

只使用已有的 `bit` conda 环境，无需安装运行依赖。Windows 在当前仓库或任意工作目录执行：

```bat
auto_script\publish.bat
auto_script\publish.bat --date 2026-08-23
auto_script\build.bat
auto_script\test.bat
```

默认发布最新的 `YYYY-MM-DD.html`；指定日期可同步深读或问答修改。`build` 只生成本地站点，打印 `logdir/<run>/site` 路径。`--all` 显式回填全部 HTML 日报，历史 Markdown 不会自动上传。

重要参数集中在 `config.json`：源目录、GitHub 仓库、发布开关、单文件/站点/单次上传容量。相对源目录相对于配置文件定位，执行命令的工作目录不限。`.env` 可配置 `GITHUB_TOKEN`；默认复用 Git Credential Manager，凭据不会进入网页或日志。

## 自动接入 daily-paper-search

本机技能已经接入 `references/cloud-publishing.md`：推荐、深读、后续问答完成 HTML 保存与验证后，只发布修改过的日期；只读查看不发布。`config.json` 的 `publication_enabled` 控制技能自动调用。它控制的是技能流程，不是后台监听服务；不依赖本机常驻进程。手动 `publish` 始终表示显式发布请求。

迁移机器时，将已安装技能中的 `references/cloud-publishing.md` 及其 SKILL.md 对应引用迁移，并修改其中的仓库路径。repo 构建技能的可移植副本位于 `skills/repo-experiment-builder/SKILL.md`，复制到该机器的 Codex skills 目录即可使用。

## 发布设计与边界

- `main` 只存代码；`gh-pages` 只存可发布网页，代码同步不携带日报图片。
- 发布白名单仅含选定 HTML、它引用的本地图片、前端三个静态文件和目录。不会上传完整 `temp/`、PDF、邮箱状态、偏好、私密索引或 `.env`。
- HTML 中的图片转为内容哈希命名；同一日报重复图片只存一份。历史图片一旦发布，不受本地 temp 清理影响。带 arXiv ID 的本地 PDF 链接改为原论文公共 URL。
- 对远端 Git blob SHA 做内容比较，仅上传变化的 blob；不变时 0 上传、0 commit、0 部署。使用 Git Trees 原子提交；并发更新禁止强制覆盖，冲突时保留本地报告并重新运行。
- 每次只读取变动月份的 JSON；浏览器只加载一个月（至多 31 条日报），月份列表很小。不会下载全部历史全文或每篇论文索引。
- 更新某日报时删除其已经不再引用的旧图片；其他日报保持不变。不会根据本地 temp 清理去删除云端历史日报。
- 默认限制单文件 15 MiB、站点当前内容 750 MiB、单次变化 100 MiB，超过则在上传前报错。GitHub Pages 的站点上限为 1 GB，分支发布有每小时 10 次构建软限制；避免连续逐条更新。
- 增量上传不等于无限存储。Git 历史会保留旧版本，GitHub 构建仍会处理部署分支。发布器监测仓库磁盘占用，达到预算会停止。接近预算时按年度新建归档仓库，保留旧站 URL，再将配置指向新仓库；不要自动 force-push 或删除历史。若需要无限规模对象存储，应另行迁移存储层。

当前远端树检查成本随文件数增长，但只传输元数据；站点和仓库预算限制其规模。避免把 PDF、训练产物或原始数据引入这个仓库。

## 缺图与安全

新日报默认遇到缺图即失败，先恢复图片再重试。旧日报可能因先前 temp 清理而丢图，可明确运行：

```bat
auto_script\publish.bat --all --allow-missing-images
```

该选项会在网页显示“历史图片原文件已清理”提示，不会伪造图片。保留原始 HTML 不变。当前首次历史迁移使用此选项；最新日报正常打包全部图片。

发布器面向自己生成且已审阅的可信 HTML，保留脚本、公式、图片缩放与稳定锚点；它不是用于上传任意第三方 HTML 的安全沙箱。本地文件引用必须在源目录内，禁止任意文件和路径越界。CSS 本地依赖与 srcset 暂不支持，会明确报错。公式使用原日报的 CDN，读者网络需可访问对应 CDN。

## 首次部署或迁移

确认公开访问，编辑 `config.json` 的 `repository`，初始化 Git 并提交白名单源码后运行：

```bat
conda run -n bit python -B setup_github.py --public
git push -u origin main
auto_script\publish.bat
conda run -n bit python -B setup_github.py --public --enable-pages
conda run -n bit python -B publisher.py status
```

初始化脚本不改变现有仓库可见性或覆盖不同的 Pages 配置。`gh-pages` 由发布器维护，不需要手动拉取到主工作区。HTTP 成功提交后 Pages 异步构建，最终以公开 URL 可访问为准。

## 验证与产物

`tests/test_publisher.py` 覆盖白名单、路径越界、缺图、重复发布、旧图片清理、月目录、HTTP 和容量限制。`tests/verify_site.py --site logdir/<run>/site` 使用已有 Edge 做真实浏览器渲染、截图和公式检查，所有产物放在新建的运行目录内。诊断详见 `logdir/<run>/result.json`。

`codex-executor.log` 最多保留五条近期记录和一条重要历史记录；`task_checklist.md` 只保留任务勾选。两者、`logdir/`、`.env` 和原始 `codex-prompt.txt` 均不提交。

参考：[GitHub Pages 限制](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)、[Git Trees API](https://docs.github.com/en/rest/git/trees)。
