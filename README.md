# DocumentResearch · 论文书房

公开门户：[GitHub Pages](https://seven-7-ding.github.io/DocumentResearch/) · [Hugging Face Space](https://huggingface.co/spaces/seven-7-ding/DocumentResearch) · [Space 独立页面](https://seven-7-ding-documentresearch.static.hf.space/)

上方按卡片展示每日论文汇报、论文总数、精读数与主题；下方收录 EveryDayPaper 历史精读记录，包括早期 Markdown 中的精读文献。论文卡片直接打开原文 PDF，支持标题、作者、第一作者、尾作、机构、发表日期、入库日期、会议期刊、类型及用户标签组合筛选。

## 日常发布

只使用已有 conda bit 环境和标准库，无需安装包。

```bat
auto_script\publish.bat
auto_script\publish.bat --date 2026-10-15
auto_script\build.bat --all --allow-missing-images
auto_script\test.bat
```

默认发布最新 HTML，指定日期可更新精读及问答。发布会刷新精读元数据（同一天已成功核查的记录跳过）、增量更新 GitHub gh-pages，然后同步 HF 门户。daily-paper-search 已有的发布命令继续适用。仅 HF 更新失败时：

```bat
auto_script\publish_space.bat
```

元数据也可单独刷新：`auto_script\refresh_library.bat`。本地构建不会联网刷新。源目录、GitHub 发布容量与自动刷新开关在 config.json，固定 HF 目标在 publish_space.py。默认复用 Git Credential Manager；.env 可放 GITHUB_TOKEN，不会出现在部署文件中。

## 私人笔记与同步

点击“登录同步”，通过 Hugging Face OAuth / PKCE 授权。两个门户使用相同的公开 OAuth Client Metadata Document，均能登录同一账号。无需手动创建数据库或付费存储，首次登录自动创建账号下的 **私有 Dataset `document-research-notes`**。不要预先创建同名仓库；OAuth 的 `contribute-repos` 权限仅能访问本应用创建的仓库，不授权读取其他个人仓库。

- 标签、笔记和评分只进入私有 Dataset；公开 Space、GitHub 代码、日报目录不包含它们。
- OAuth 令牌只保存在当前标签页的 sessionStorage，关闭后重新登录；不会在代码中嵌入本机 API Token。公共阅读不需要登录。
- 笔记按稳定哈希分成至多 16 个文件，每次只提交变化分片与小清单；重复保存相同内容不创建提交。读取固定到同一提交，写入用 parentCommit 防止覆盖并发更新。
- 保存后立即同步，回到页面、恢复网络及前台每分钟自动刷新。不同字段可以合并；同字段冲突保留当前设备草稿，提示手动合并。离线或请求失败的待同步草稿按用户隔离存放在本机。
- “笔记管理”可以导出当前笔记和待同步草稿。当前笔记上限 2 MB，每篇笔记 10000 字，最多 20 个标签。累计上传历史的保守预算为 100 MB，达到时停止增加历史；先导出备份，再在“笔记管理”选择“整理历史”，确认后保留当前笔记并压缩旧版本。
- 若使用 HF 外层 iframe，登录会在独立页面打开，以避免第三方浏览器存储隔离。个人账号的首次授权由用户在 HF 页面完成。

原始记录的个人 tags、notes、评分不会意外公开或自动导入云端；这些字段从空白开始由用户填写。

## 元数据来源与边界

portal.py 从本地私有索引与日报正文提取已精读文献，并只导出严格白名单字段。HTML 中未填写的“精读”占位块不计入精读数；去重采用稳定论文 ID。公开的论文书目是为门户派生的数据，不上传原始 paper_index.json。

arXiv 采用 API 的最新 updated 日期、版本、作者与期刊信息；机构缺失时核查论文首页。元数据缓存 library_metadata.json 位于 EveryDayPaper，包含核查来源，保持本地，不直接发布。部分 OpenReview 页面会触发人机验证，此时保留原记录，不推测新日期或会议信息；发表日期的提示文字区分已核验与未核验。作者 PDF 未标明版本日期时同样保留原记录。预印本不会自动归类为不完整草稿。

入库日期采用已有精读日期，未记录精读日期时采用最早收录日期。HTML 日报卡片只列已发布日报；早期 Markdown 的精读条目仍包含在图书馆内。

## 精简发布与容量

- GitHub main 存源码，gh-pages 存部署内容；HF main 是独立的门户部署仓库。
- 白名单只有选定日报 HTML、被引用的本地图片、前端、公开目录及派生书目；不上传 PDF、邮箱数据、偏好、原始私有索引、.env、日志或完整 temp 目录。
- HF 只部署小型门户与目录，日报全文和图片链接到 GitHub Pages，不重复上传大文件。用户本机关机不影响访问。
- 公共书目稳定分为 16 个内容哈希分片，保留上一代供部署期间旧客户端读取，再清理过期分片。浏览器最多并发加载 4 个分片，每页仅渲染 12 篇；日报默认最近 6 份，按月最多 31 份。书目达到 5 MiB 时拒绝发布，需分档后继续。
- Git blob 内容比对避免重复提交；图片内容哈希去重。已发布图片的映射让后续更新可以在本地 temp 清理后继续复用旧云端图片。默认不允许新日报缺图；明确历史回填才可使用 --allow-missing-images。
- GitHub 当前站点 750 MiB、单文件 15 MiB、单次上传 100 MiB、仓库历史 850 MiB 为默认预算；超限在上传前停止。规模增长时按年度另建归档，不自动 force-push 删除公共历史。
- 静态门户不启动常驻容器，因此不依赖 Space 计算实例的临时磁盘或休眠状态。

## 验证

`auto_script\test.bat` 验证发布安全、幂等、图片保留、容量、公开元数据白名单、历史精读与稳定分片。

```bat
conda run -n bit python -B tests\verify_portal.py --site logdir\<run>\site
conda run -n bit python -B tests\verify_cloud.py
```

浏览器测试使用已有 Edge，检查手机/桌面、真实 132 篇数据、筛选、分页、PDF 链接及冲突合并。云端测试显式创建一个随机命名的私有测试 Dataset，验证两台客户端读写、持久化与匿名访问拒绝，随后删除测试 Dataset；不触及生产笔记。实际 OAuth 首次登录仍需账号持有者授权。

所有构建、浏览器 profile、截图和诊断只进入 logdir/<run>/。任务结束按本仓库要求删除整个 logdir，不留空占位；后续命令按需临时重建。task_checklist.md 只含任务勾选；codex-executor.log 最多五条近期记录加一条重要历史记录。两者、codex-prompt.txt、.env 和日志均不提交。

参考：[HF OAuth 与 CIMD](https://huggingface.co/docs/hub/oauth)、[Space 静态登录](https://huggingface.co/docs/hub/spaces-oauth)、[GitHub Pages 限制](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)。
