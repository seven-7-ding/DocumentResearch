# DocumentResearch · 论文书房

[门户入口](https://seven-7-ding.github.io/DocumentResearch/) → [私有 Hugging Face Space](https://huggingface.co/spaces/seven-7-ding/DocumentResearch)。只有有权访问 Space 的 HF 账号能进入；进入后直接编辑，不再进行应用内 OAuth 登录。既有公开日报 URL 保持不变。

上方展示每日汇报、论文数、精读数和主题。作者、首尾作者、机构、会议、标签和类型支持带搜索的多选：同一字段按“或”匹配，不同字段按“且”匹配。卡片高亮匹配文本与字段；标签按名称稳定分配八种颜色。界面及报告优先使用 Times New Roman，中文和缺少该字体的设备使用系统衬线字体回退。下方图书馆支持标题、作者、首尾作者、机构、时间段、会议期刊、标签和 **1–5 分范围**组合筛选，也可单独筛选未评分论文。卡片包含 PDF 和已有精读报告链接；没有报告的条目明确标示，不生成占位精读。

## 发布

本机仅使用已有 conda `bit`；无需新建环境。历史报告转换使用 bit 中已有的 Python Markdown，后端仅依赖标准库。

```bat
auto_script\publish.bat
auto_script\publish.bat --date 2026-10-15
auto_script\publish_space.bat
auto_script\test.bat
```

源目录和容量参数在 `config.json`。GitHub `main` 保存源码，`gh-pages` 保存公开日报和入口；HF `main` 保存私有部署。`private_portal` 必须为 true。日常发布刷新元数据、增量发布公开日报，再同步私有门户。只重试 HF 时使用 `publish_space.bat`。

HF 使用 Docker / CPU Basic。当前 HF 规则要求运行计算型 Space 的个人账号有 PRO；CPU Basic 无小时费用，但账号计划有独立订阅费用。若 HF 返回 `Quota exceeded ... cpu-basic ... limit=0`，在 HF 账号中处理订阅后，从 Space Settings 重启即可。发布脚本不会购买计划或升级付费硬件。

## 笔记存储

发布脚本创建 **私有 Dataset `seven-7-ding/document-research-notes`**，无需另购持久化磁盘。标签、笔记、评分由 Space 后端写入 Dataset，容器重启或休眠不会丢失。所有获准进入该私人 Space 的协作者共享这一份图书馆笔记。

- HF 平台负责入口认证。后端还检查 Space 保持私有，并限制修改请求来源。
- `NOTES_HF_TOKEN` 仅保存在 Docker Space 的 Secret 中，浏览器不接触令牌。不可将此 Space 改回 Static SDK；Static Space 的变量和 Secret 可能暴露给前端。
- 笔记最多16个稳定分片，每次只上传变化分片及清单，相同内容不提交。读取固定到同一版本，写入用 `parentCommit` 防止覆盖并发更新。
- 不同字段的修改自动合并；同字段冲突保留本机草稿。网络失败时不显示“已同步”，恢复网络和回到页面时重试。
- 保存和切回页面时立即同步；可见页面每五分钟检查其他设备的更新，隐藏时停止周期检查。并发资源请求共用一次私有状态核验，减少重复请求。
- 每篇最多10000字、20个标签，总笔记2 MB，历史上传预算100 MB。“笔记管理”支持导出；手动确认“整理历史”后保留当前笔记并压缩旧版本。

原索引中的私人标签、笔记、评分不自动导入，也不出现在部署文件中。

## 论文与精读报告

`portal.py` 读取 EveryDayPaper 的本地索引、日报和 `library_additions.json`（用户指定补入的书目），按稳定 ID 去重。`library_metadata.json` 保存核验来源。三个源数据文件均不直接上传或提交到源码仓库。

arXiv 使用最新版本的作者、updated 日期和 PDF；机构按论文首页核验。会议统一缩写，主会与 Workshop 分开。机构占位文字不作为可选项，无法查证的机构留空；不能从邮箱域名推测机构。来源只给出年份或月份时保留原精度，不伪造具体日期。部分 OpenReview 页面会要求人机验证，尚未核实的最新日期不会标记为已核验。

已有 HTML 精读跳转到对应公开日报锚点；早期 Markdown 提取论文专属章节，通过 `reading_reports.py` 转成独立的私有网页，保留数学公式。目录不会把简短推荐或空占位块当作精读。补入论文若无本地精读记录，只增加书目，不声称完成精读。

## 容量与隐私

- GitHub 只公开选定日报、其引用图片、紧凑日报目录及跳转入口；HF 部署前端、派生书目、精读网页和最小后端。
- 不上传论文 PDF、邮箱、偏好、原始索引、`.env`、本地路径、日志或整个临时目录。公开旧日报及其历史不会因门户改为私有而被撤回。
- 书目稳定分16个内容哈希分片，浏览器并发最多4个、每页渲染12篇；日报默认最近6份，按月加载。书目达到5 MiB时停止发布，要求先分档。
- 日报图片按内容哈希去重，旧图片映射支持本地图片清理后继续更新日报。GitHub 单文件15 MiB、站点750 MiB、单次上传100 MiB、历史850 MiB为默认预算；超限停止，不自动重写公共 Git 历史。
- 本机关机不影响云端存储；Space 休眠后首次进入可能需要等待唤醒。

## 验证

`auto_script\test.bat` 检查发布隔离、稳定分片、历史精读、机构缩写和后端安全边界。

```bat
conda run -n bit python -B tests\verify_private.py
conda run -n bit python -B tests\verify_filters.py
```

`verify_private.py` 使用已有 Edge、真实图书馆和一个随机命名的私有测试 Dataset，覆盖云端持久化、并发合并、冲突、重复保存、匿名拒绝、手机桌面、评分筛选、直接编辑、断网草稿恢复和精读公式。测试后删除测试 Dataset，不改动生产笔记。`verify_filters.py` 使用本地测试笔记验证多选、高亮、配色、字体和手机布局，不写云端数据。两者均在本地运行；HF 实例的实际启动状态须另外核查。

本仓库不创建 `logdir/`、不保存测试日志或截图；验证结果直接输出到终端。必要的构建检出、测试输入和浏览器配置使用系统临时目录，进程退出时自动清理；`task_checklist.md` 仅任务勾选，`codex-executor.log` 最多五条近期记录加一条重要历史记录，均不提交。`codex-prompt.txt` 不修改。

参考：[HF Space 可见性和计算计划](https://huggingface.co/docs/hub/spaces-overview)、[Docker Spaces](https://huggingface.co/docs/hub/spaces-sdks-docker)、[GitHub Pages 限制](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)。
