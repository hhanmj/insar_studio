# 更新日志

本项目遵循语义化版本号思路：修复问题使用补丁版本，兼容性功能使用小版本，破坏性变更使用大版本。

## [2.1.9] - 2026-07-12

### 更新摘要

- 完成 Sentinel-1 多批次检索、并行下载、任务快照、暂停继续和重启恢复的状态隔离，避免不同任务、AOI 和工作台结果互相污染。
- 完善 ASF 检索数量、缓存、Path/Frame 元数据回查和工作台展示，减少重复查询并提高大批量检索稳定性。
- 完善行政区与本地边界导入，支持全国真实复杂边界、台湾省县市、多要素选择和单个 Shapefile 拖拽识别。
- 完善 DEM 下载、暂停、进度和输出命名，避免同目录重复任务覆盖结果文件。
- 新增 GitHub + Gitee 双渠道发布与国内更新镜像；软件每次启动检查一次新版，并可按版本关闭重复提醒。
- 更新 InSAR Studio 品牌图标、社区入口和 GitHub Stars 链接；完整 Python 全量版继续包含 DEM/GDAL 功能，Rust 重构不进入本次发布。

### 新增

- 新增任务级稳定 `task_id`、冻结候选影像列表、实际下载影像 ID、AOI、目录和勾选状态持久化。
- 新增同一软件会话内多个 Sentinel-1 下载任务并发运行，每批检索可独立选择目录并创建独立任务快照。
- 新增 Path 与 Frame 区间筛选，经纬度范围支持十进制和度分秒输入。
- 新增全国、省、市、县真实行政边界选择；台湾行政区支持在线查询并回退本地真实边界。
- 新增全软件边界文件拖拽识别，支持 `.shp`、`.kml`、`.kmz`、`.geojson` 和 `.json`；多要素文件可选择要素后合并为 AOI。
- 新增完整 AOI 复制为 KML，保留多边形坐标；无完整几何时回退外包矩形。
- 新增 DEM 下载实时字节进度、暂停继续、ASCII 指纹文件名和独立结果日志。
- 新增 GitHub Release 自动同步 Gitee Release、国内镜像标记和镜像优先下载。
- 新增 InSAR Studio 专属 SVG 品牌标识、多分辨率 Windows 图标、交流群二维码和 GitHub Stars 社区入口。

### 优化

- ASF 检索相同 AOI 与筛选条件时复用缓存；上调目标数量时优先只补充缺少的结果。
- 检索工作台与下载任务快照完全分离：新检索只覆盖当前工作台，不再继承旧任务下载状态。
- 下载中心任务快照保存检索时全部候选影像，允许后续从原任务目录追加未下载影像。
- 任务队列卡片控制整任务；任务快照顶部只控制当前勾选影像；影像行只控制单景。
- 下载状态使用互斥的下载中、已暂停和排队集合，暂停请求发出后立即刷新计数且不会突破设定并发。
- 下载目录默认按用户选择位置直接保存；可选创建 `SLC` 和 `Sentinel_Orbit/AUX_POEORB` 子目录。
- 已有完整文件自动跳过，`.part` 文件继续断点续传；缺失条目会核对、重试并写入中文日志。
- Earthdata Token、用户名和密码保存后回填输入框，并明确显示 Token、账户或本地 `.netrc` 登录方式。
- 行政区切换时立即清空旧的市县选项，后台加载并缓存新选项，避免快速操作显示上一省数据。
- 社区二维码统一裁切、尺寸和对齐；地图 Leaflet 标识缩小；工作台列表补充序号、Path 和 Frame。
- 完整版 EXE 内置 DEM、GDAL、PROJ、Shapefile 与 EGM2008 高程基准网格，体积约 103 MiB。

### 修复

- 修复同目录或不同检索批次的任务快照互相覆盖、AOI 被最新边界污染的问题。
- 修复暂停任务重启后任务快照无法打开、继续任务错误使用当前检索结果的问题。
- 修复任务卡片、快照顶部和影像行暂停/继续状态不一致，以及单景继续导致并发数增加的问题。
- 修复下载进度只在暂停时刷新、任务结束持续转圈、运行任务误入历史记录和结束任务重复占用队列的问题。
- 修复历史任务删除后重新出现、同一任务产生多条中断记录、任务名称及日志遮挡的问题。
- 修复 ASF 指定数量时结果不足、大批量分页受限、回退元数据缺少 Path/Frame 和轨道方向显示错误的问题。
- 修复精密轨道工作台被旧检索或下载状态污染、轨道日志不完整和目录层级错误的问题。
- 修复工作台未下载影像出现暂停按钮、已在任务中的排队影像可重复追加的问题。
- 修复 Shapefile 投影识别失败、旧版 WGS84 `.prj` 不兼容、GeoJSON 多要素加载卡顿和 500 要素限制。
- 修复全国 AOI 名称、台湾市县列表与真实边界加载、行政区“全国/全部”重复和下级选项残留问题。
- 修复 Earthdata 正确凭据在其他电脑保存时触发 `AttributeError` / `DL004` 的问题。
- 修复 DEM 同一目录多次下载覆盖结果日志、中文文件名兼容性和下载进度延迟问题。
- 修复更新弹窗内容截断、更新下载仅依赖 GitHub 导致国内网络失败和软件内版本仍显示 `v2.1.8` 的问题。

## [2.1.8] - 2026-07-10

### 更新摘要

- 新增启动更新提醒和在线下载更新包入口。
- 新增任务快照机制，下载任务不再被后续检索或最新 AOI 污染。
- 优化 Sentinel-1 与精密轨道检索、下载、日志和历史记录逻辑。
- 修复工作台、任务快照、边界导入、暂停任务和下载进度相关问题。
- 更新弹窗支持完整日志滚动显示；旧版弹窗优先展示本摘要。

### 新增

- 新增启动时更新提醒：检测到新版后弹出更新窗口，并显示版本号、发布时间和更新日志。
- 新增在线下载更新入口，用户可在更新弹窗或“设置 - 更新与组件”中下载新版安装包。
- 新增“任务快照”机制：下载任务会固定保存进入下载时的影像列表、AOI、目录和勾选状态，避免被后续检索污染。
- 新增 AOI 复制为 KML：地图上仍显示简洁范围信息，复制时优先复制完整 AOI 几何；无完整几何时复制外包矩形。
- 新增工作台与任务快照影像序号显示，并补充 path、frame 等关键轨道信息。
- 新增经纬度范围输入对十进制和度分秒格式的支持。

### 优化

- 优化 Sentinel-1 检索缓存逻辑：相同区域和筛选条件下优先复用已有结果，调整目标数量时减少重复查询。
- 优化 ASF 检索数量逻辑，目标影像数量与候选影像总数显示更清晰。
- 优化 Sentinel-1 与精密轨道下载任务结构，统一下载队列、任务快照、日志和历史记录逻辑，为后续光学影像下载扩展打基础。
- 优化下载目录逻辑：用户选择到哪里就下载到哪里，不再额外强制创建目录；可选创建 SLC、Sentinel_Orbit 等分类目录。
- 优化已下载数据识别，目录中已有完整文件时自动跳过，减少重复下载。
- 优化本地边界文件导入流程，支持拖拽识别边界文件，并改进 Shapefile 侧车文件处理。
- 优化行政区选择与 AOI 绑定逻辑，选择行政区或导入边界后自动作为当前 AOI。
- 优化下载日志中文表述，减少冗余技术信息，补充任务耗时和未完成条目提示。
- 优化软件图标与界面标识，替换旧水印和模糊图标。
- 优化打包体积，在保持 DEM、GIS、下载等功能完整的前提下减少不必要依赖。

### 修复

- 修复删除历史任务后有时重新出现的问题。
- 修复同一任务产生大量中断记录的问题。
- 修复运行中任务错误进入历史记录的问题。
- 修复已结束任务同时出现在任务队列和历史任务中的问题。
- 修复重新打开软件后暂停任务丢失的问题。
- 修复暂停后继续任务时任务快照打不开的问题。
- 修复第二次检索后工作台被旧下载任务污染的问题。
- 修复下载中心任务快照被最新 AOI 或最新边界污染的问题。
- 修复 Sentinel-1 和精密轨道工作台之间已选数量、任务状态互相污染的问题。
- 修复下载进度、速度不实时刷新，以及任务结束后一直转圈的问题。
- 修复精密轨道下载日志不完整、失败或缺失条目提示不足的问题。
- 修复工作台和任务快照中影像名称、按钮、下载信息遮挡的问题。
- 修复历史任务名称和日志布局不规整、内容遮挡的问题。
- 修复 path、frame 区间输入提示被遮挡的问题。
- 修复日期输入框占用高度过多的问题。
- 修复本地 GeoJSON 要素较多时弹窗卡顿的问题。
- 修复 Shapefile 导入失败或范围识别错误的问题。
- 修复全国 AOI 在任务快照中标注错误的问题。
- 修复 ASF 回查元数据后部分影像仍缺少 path、frame 或轨道方向信息的问题。
- 修复行政区市、县选项缺失的问题。
- 修复地图拖拽识别边界时出现遮挡地图、影响缩放的问题。

## [2.1.7] - 2026-07-08

### Added

- Added startup update notification dialog with release notes, release date, asset details, and in-app update package download.
- Added update metadata caching for release name, changelog, publication time, and downloadable assets so known updates can still be shown when the network is temporarily unavailable.
- Added the update and componentisation plan for the transition from the current full desktop package to a smaller host app plus optional components.
- Added frozen task snapshots for Sentinel-1 and Orbit download flows so later searches do not mutate existing download tasks.

### Improved

- Improved Sentinel-1 search cache rules for AOI, date, path, frame, orbit direction, beam mode, and polarisation filters.
- Improved download task isolation: each Sentinel-1 or Orbit batch keeps its own scene snapshot and output directory.
- Improved ASF/Sentinel-1 downloads to skip already completed files and resume partial files where possible.
- Improved Orbit downloads to skip existing EOF files and to reuse the same snapshot-oriented download rules.
- Improved local AOI import behaviour for administrative boundaries and uploaded vector boundaries.
- Improved task history persistence so paused tasks survive restart and deleted history entries do not reappear.
- Clarified that future heavy runtimes such as DEM/GDAL, GEE, Whitebox, optical imagery, and processing engines should move to optional components rather than the main exe.

### Fixed

- Fixed repeated interrupted history records for the same task.
- Fixed stale download workbench state after repeated Sentinel-1 or Orbit searches.
- Fixed SHP/CGCS2000 boundary import handling and unsupported drag-and-drop messaging.
- Fixed several download progress and terminal-state refresh issues.

## [2.1.6] - 2026-07-05

### 新增

- 增加 Sentinel-1 大数量检索缓存，同一区域和同类条件下再次扩大数量时复用已有结果，减少重复联网检索。
- 增加 Sentinel-1 检索过程停止能力，避免大范围检索时只能等待完成。
- 增加下载中心中 DEM、轨道和 Sentinel-1 任务的统一目录打开入口。

### 优化

- 优化 ASF 大数量检索策略，优先分批使用 ASF 查询并保留升降轨、Path、Frame 等元数据；CMR 仅作为备用结果来源。
- 优化 Sentinel-1、精密轨道和 DEM 的资源入口，将在线检索和本地文件检索整理为同一张卡片内的切换界面。
- 优化 Sentinel-1 与精密轨道工作台在地图中的显示逻辑，点击哪个工作台就显示哪个，并保留上次滚动位置。
- 优化工作台列表虚拟滚动和行高，减少几千景数据时的卡顿和等待。
- 优化地图右上角经纬度与范围显示，支持点击复制并避免换行撑高。
- 优化下载队列显示，运行中任务不再进入历史记录，暂停、恢复、取消和结束状态更统一。
- 优化精密轨道下载状态展示，补充成功、跳过、未发布、失败、速度和用时统计。
- 优化 DEM 下载流程，任务进入下载中心并支持取消，日志集中显示在下载中心。
- 优化设置页账号状态检测，启动时刷新 ASF/Earthdata 状态，并减少重复凭据验证。
- 发布资产调整为全量单文件 exe，不再发布 setup 安装包。

### 修复

- 修复 ASF 日期控件回退为手填或显示异常格式的问题，保留日历选择并统一显示为 `yyyy/mm/dd`。
- 修复影像数量较多时 ASF 检索失败后元数据回填慢、结果数量异常的问题。
- 修复历史记录删除后在部分电脑上重启又重新出现的问题。
- 修复软件最大化或全屏后遮挡 Windows 任务栏的问题。
- 修复 DEM 下载只生成原始 DEM 但日志误报椭球高和 SARscape 输出完成的问题。
- 修复已暂停任务重启后错误进入历史记录，以及恢复时可能重复校验 ASF 账号的问题。
- 修复 Sentinel-1 结束下载有时不能立即反馈的问题，终止过程中显示处理中状态。
- 修复本地或下载 DEM 已是椭球高时仍提示继续转换的问题。

## [2.1.4] - 2026-07-01

### 优化

- 优化 Earthdata/ASF 设置状态展示，明确区分本机已保存凭据、正在检测、检测通过和检测失败，避免绿色成功与黄色警告同时出现。
- 优化 Sentinel-1 影像下载工作台，补充已暂停数量，并让暂停所选、继续所选的可用条件和提示更清楚。
- 优化新手教程触发逻辑：首次打开软件自动显示一次，后续可通过顶部引导入口手动重播。
- 优化 DEM 下载按钮状态，仅下载DEM和下载并转换椭球高分别显示各自的执行状态。
- 调整更新与组件说明，明确主程序在线更新优先，DEM/GDAL 高程基准组件作为第二阶段按需安装。

### 修复

- 修复启动或手动刷新账号状态时复用旧成功缓存导致状态不准确的问题。
- 修复单文件桌面版因 WebView 本地缓存来源变化而反复弹出新手教程的问题。
- 修复 DEM 仅下载时转换按钮也一起转圈的界面问题。
- 增加工作流和打包脚本的中文弯引号检查，防止发布脚本再次因非 ASCII 引号解析失败。

## [2.1.3] - 2026-06-30

### 修复

- 修复 GitHub Release 工作流中发行包说明遇到中文弯引号时触发 PowerShell 解析错误的问题。

## [2.1.2] - 2026-06-30

### 优化

- 优化软件内更新体验，更新包下载后显示保存位置并提供打开更新目录入口。
- 将 DEM/GDAL 组件文案统一为“DEM/GDAL 高程基准组件”，明确覆盖 EGM96、EGM2008 与 WGS84 椭球高输出流程。

### 修复

- 修复 GitHub Release 工作流下载 EGM2008 格网时可能拿到网页而非压缩包的问题。
- 修复自动生成的发行包说明文字编码问题。

## [2.1.1] - 2026-06-30

### 优化

- 优化 Earthdata/ASF、OpenTopography、天地图等凭据保存前校验逻辑，避免无效账号或密钥被静默保存。
- 优化 DEM/GDAL 组件状态识别，区分运行库、EGM2008 网格缺失和组件损坏状态。
- 优化设置页中的组件入口和密码/Token 可见性切换。
- 优化新手指引，首次进入新版自动展开，并统一软件名称为 InSAR Studio。

### 修复

- 修复全屏后地图底部经纬度、缩放等级和加载提示被遮挡的问题。
- 修复 DEM/GDAL 组件缺失时提示不准确、错误信息过粗的问题。
- 修复软件版本显示在部分场景下仍停留在旧值的问题。

## [2.1] - 2026-06-30

### 新增

- 增加 SAR 下载工作台，支持搜索、勾选、全选当前列表、高亮影像和单景操作。
- 增加下载中心角标，提示正在进行的任务数量。
- 增加 DEM/GDAL 高级转换组件的按需下载和组件清单机制。
- 增加 GitHub Release 自动打包安装版、便携版和 DEM/GDAL 组件资产的流程。

### 优化

- 优化 Sentinel-1 / ASF 检索、下载队列、断点续传、失败重试和详细日志。
- 优化暂停、失败、结束和已删除下载记录的持久化逻辑，重启后保持正确状态。
- 优化 AOI 与行政区边界，多要素边界可预览、筛选、选择和绑定。
- 优化精密轨道逻辑：默认承接 Sentinel-1 检索结果，也支持单独导入 SAR 文件或目录生成轨道候选。
- 优化 iOS 风格界面、顶部资源区、新手引导和地图交互。

### 修复

- 修复软件关闭后后台进程偶发残留的问题。
- 修复结束或删除的任务重启后错误回到任务队列的问题。
- 修复工作台中已选影像高亮、元数据提示和列表操作不一致的问题。

### 移除

- 移除精密轨道中的本地轨道库入口，简化为下载所选影像对应的 POEORB/EOF。

## [2.0.2] - 2026-06-29

### 修复

- 修复发布工作流中的打包引号问题。
- 改进 Release 资产生成流程。

## [2.0.1] - 2026-06

### 新增

- 发布 InSAR Studio 2.x 桌面 UI 的早期测试版本。
