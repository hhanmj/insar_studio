# 更新日志

本项目遵循语义化版本号思路：修复问题使用补丁版本，兼容性功能使用小版本，破坏性变更使用大版本。

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
