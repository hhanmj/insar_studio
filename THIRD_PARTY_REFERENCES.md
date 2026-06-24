# Third-Party References

本文件登记项目调研过的第三方仓库 / 工具 / API。**每看一个就登记一次。**

## 使用纪律（硬规则）

1. **不直接复制第三方源代码**；只总结功能边界、API 调用方式、配置方式、测试思路与许可证风险。
2. 可作为依赖的，**优先封装成适配器**（`providers/*`），不重写其核心功能。
3. 许可证与 MIT 不兼容或有 **GPL 传染风险** 的，只能作为「可选外部工具」或「架构 / 接口参考」，**不得**作为 MIT 主项目的强依赖。
4. **许可证不明 = 视为 All Rights Reserved**：只可学习概念，不得复制代码、不得随项目分发。
5. 第三方项目自带的 `.env`、凭据、整套 venv、二进制，一律 **不进 git**（已在 `.gitignore` 忽略 `参考项目/`、`.env`、`*.exe`）。

## 字段说明

`name / url / license / last_checked_date / purpose / use_as_dependency / copy_code_allowed / integration_plan / risk / notes`

## 许可证兼容性速查

| 许可证 | 与 MIT 主项目 | 处理方式 |
|---|---|---|
| MIT / BSD-2 / BSD-3 | 兼容 | 可作 pip 依赖；封装适配器，不复制源码 |
| Apache-2.0 | 兼容 | 可作依赖；保留 NOTICE / 专利条款 |
| GPL-3.0 / AGPL | **不兼容（传染）** | 仅作可选外部工具 / 接口参考，禁止 import 进主代码 |
| 未声明 / 私有 | **视为保留所有权利** | 仅学习概念，禁止复制与再分发 |

---

## 登记条目

### 1. asf_search

- **name**: asf_search (asfadmin/Discovery-asf_search)
- **url**: https://github.com/asfadmin/Discovery-asf_search
- **license**: BSD-3-Clause
- **last_checked_date**: 2026-06-23
- **purpose**: ASF 目录检索、baseline / stack、SLC 下载（Earthdata 认证）。
- **use_as_dependency**: 否（本项目选用直连 `requests`，见下）。当前真实下载用 `requests` 自研，未引入 asf_search。
- **copy_code_allowed**: 否（许可证允许，但本项目政策为封装不复制）。
- **integration_plan**: Task 049 真实 SLC 下载选择直连 `requests`（可选 `download` extra），以便完全掌控 `.part`/原子改名/体积校验/重试/脱敏；仅**概念借鉴** `ASFSession.rebuild_auth`——重定向时把 `Authorization` 头限制在 Earthdata/ASF 主机、签名 S3 跳转前丢弃（落到 `providers/asf/downloader.py` 的 `_EarthdataSession`，自写实现，未复制源码）。
- **risk**: 低。需 Earthdata 凭据（env token / `~/.netrc`，仓库外）；网络在单测中以 fake session 注入，从不真连。
- **notes**: 可借鉴点=`ASFSession` 跨域保留/丢弃认证头的思路、平台/极化/beam 常量、结果→下载流。不应实现/复制=任何 asf_search 源码。已落地=Task 049（真实下载，concept-only borrow）。

### 2. sentineleof

- **name**: sentineleof (scottstanie/sentineleof)
- **url**: https://github.com/scottstanie/sentineleof
- **license**: MIT
- **last_checked_date**: 2026-06-18
- **purpose**: Sentinel-1 精密 / 重启轨道（POEORB / RESORB）下载与按日期匹配。
- **use_as_dependency**: 是（推荐，作为轨道 Provider 依赖）。
- **copy_code_allowed**: 否（封装不复制）。
- **integration_plan**: 在 `providers/orbit/` 封装；复用其「按采集时间选轨 + 优先级」思路，输出 `orbit_match_table.csv`。
- **risk**: 低。轨道源端点可能变化；单测 mock。
- **notes**: 可借鉴点=POEORB>RESORB 选择逻辑、时间覆盖判断、CLI `eof`。不应实现=自己硬刚 Copernicus/ASF 轨道端点协议。后续 Task=Task 009。

### 3. OpenTopography Global DEM API

- **name**: OpenTopography Global Datasets API
- **url**: https://portal.opentopography.org/apidocs/
- **license**: 非开源代码，受 API 使用条款 + 各 DEM 数据集许可（COP/SRTM/NASADEM/ALOS）约束。
- **last_checked_date**: 2026-06-23
- **purpose**: 按 bbox 下载 COP30/COP90/SRTMGL1/NASADEM/ALOS 等 DEM。
- **use_as_dependency**: N/A（直接 HTTP 调官方 API，不依赖个人封装库）。
- **copy_code_allowed**: N/A（以官方 API 文档为准）。
- **integration_plan**: **已落地（Task 052）**。在 `providers/dem/downloader.py` 用 `requests`（可选 `download` extra）直连 `GET /API/globaldem`（demtype + south/north/west/east + outputFormat=GTiff + API_Key），保存原始 DEM；`.part` 临时文件 + 原子改名 + GeoTIFF 魔数/体积校验 + 重试。API key 由**用户自备**（keyring / 环境变量），代码不内置、不分发。
- **risk**: 中。需 API key（keyring）；有速率限制（学术 200/24h、非学术 50/24h，绑定账号、禁分享、商用需 Enterprise）；**数据需按各数据集要求标注引用**。
- **notes**: 可借鉴点=数据集枚举（→`opentopo_demtype` 映射）、bbox 参数、`API_Key` 查询串、GeoTIFF 输出。不应实现=绕过限速 / 隐藏数据来源 / 内置共享 key。已落地=Task 052（仅按官方 API 文档实现，未复制任何第三方源码）。

### 4. pyroSAR

- **name**: pyroSAR (johntruckenbrodt/pyroSAR)
- **url**: https://github.com/johntruckenbrodt/pyroSAR
- **license**: MIT
- **last_checked_date**: 2026-06-18
- **purpose**: 大规模 SAR 数据组织、元数据解析、SNAP/GAMMA workflow 封装。
- **use_as_dependency**: 否 / 谨慎（仅架构参考；它会拉入 SNAP/GAMMA 等重型外部处理器，超出本项目「前置准备」边界）。
- **copy_code_allowed**: 否。
- **integration_plan**: 仅借鉴其「场景元数据抽象 + 目录组织 + 日志/脚本留痕」设计思路，落到我们自己的 `core/models.py`。
- **risk**: 中。重依赖 + 处理逻辑会越界到「驱动处理」，违反项目边界。
- **notes**: 可借鉴点=按文件名识别元数据、workflow adapter 模式、dem_autocreate 概念。不应实现=引入 SNAP/GAMMA 处理。后续 Task=Task 002（数据模型）、Task 011（概念）。

### 5. RAiDER

- **name**: RAiDER (dbekaert/RAiDER)
- **url**: https://github.com/dbekaert/RAiDER
- **license**: Apache-2.0
- **last_checked_date**: 2026-06-18
- **purpose**: 基于气象模型（ERA5/HRES/GMAO 等）的对流层延迟计算。
- **use_as_dependency**: 可选（v2.0+ 大气阶段研究）。
- **copy_code_allowed**: 否（Apache-2.0，若将来引入需保留 NOTICE）。
- **integration_plan**: 后期在 `providers/atmosphere/` 以可选模块封装；第一阶段不引入。
- **risk**: 中。依赖较重；与 MIT 兼容但需保留 Apache NOTICE/专利条款。
- **notes**: 可借鉴点=气象模型→延迟的接口抽象。不应实现=第一阶段强行集成。后续 Task=Task 012 之后（大气第三阶段）。

### 6. PyAPS / pyaps3

- **name**: PyAPS (insarlab/PyAPS, pyaps3)
- **url**: https://github.com/insarlab/PyAPS
- **license**: GPL-3.0
- **last_checked_date**: 2026-06-18
- **purpose**: 基于 ERA5 的大气相位延迟改正。
- **use_as_dependency**: **否（GPL-3.0 传染）**。只能作为用户自行安装的可选外部工具。
- **copy_code_allowed**: **否（硬性，GPL）**。
- **integration_plan**: 仅定义接口/数据交换格式；由用户在独立环境安装，本项目不 import、不分发其代码。
- **risk**: 高（许可证传染）。一旦 import 进 MIT 主代码会污染整个项目许可证。
- **notes**: 可借鉴点=ERA5 改正的概念与配置流程（CDS）。不应实现/复制=任何 PyAPS 源代码进主仓库。后续 Task=Task 012 之后（ERA5 第二阶段，可选外部工具）。

### 7. geo-downloader

- **name**: geo-downloader (gaopengbin/geo-downloader)
- **url**: https://github.com/gaopengbin/geo-downloader
- **license**: MIT
- **last_checked_date**: 2026-06-18
- **purpose**: 跨平台桌面地理数据下载器（GeoTIFF 瓦片 / Google 3D Tiles / Esri Wayback）。
- **use_as_dependency**: 否（**Rust + Tauri / JS 桌面应用，非 Python 库**，无法作为 Python 依赖）。
- **copy_code_allowed**: 否（且语言栈不同）。
- **integration_plan**: 仅作为「下载管理器 UX + 任务队列/续传 + 桌面打包」的产品/交互参考；我们用 PySide6 自研。
- **risk**: 低（仅参考）。
- **notes**: 可借鉴点=下载队列、断点续传、并发控制、TIFF 压缩选项、跨平台打包。不应实现=照搬 Tauri 架构。后续 Task=Task 008（下载管理器）、Task 014（GUI）。

### 8. DEMdownloader（本地 参考项目）

- **name**: DEMdownloader（本地：`参考项目/DEMdownloader/`）
- **url**: 本地，无公开仓库出处
- **license**: **不明（未见 LICENSE）→ 视为 All Rights Reserved**
- **last_checked_date**: 2026-06-18
- **purpose**: Python 版 DEM 下载器：`api/{catalog,client,globaldem}`、`utils/{administrative_boundary,geospatial,validator,file_handler}`、`interactive` CLI、`gui_app`。
- **use_as_dependency**: 否（许可证不明 + 自带二进制/venv）。
- **copy_code_allowed**: **否（硬性，许可证不明）**。
- **integration_plan**: 仅作概念参考——OpenTopography 客户端分层、行政边界处理、校验器思路，落到我们自研的 `providers/dem`、`processing/validators`。
- **risk**: **高**。① 许可证不明；② 目录内含 `.env`（疑似凭据）和整套 `Lib/site-packages`（GDAL 等）共约 5500 文件；必须隔离、严禁入库。
- **notes**: 可借鉴点=DEM API 分层、administrative_boundary（与中国边界合规交叉印证）、validator。不应复制=任何源码与 `.env`。已落地=Task 052（**仅概念参考** OpenTopography 客户端分层；DEM 下载实现按官方 API 文档自研于 `providers/dem/`，未复制其任何源码）。后续 Task=Task 005（行政边界）。

### 9. Sentinel1_OrbitDownloader.exe（本地 参考项目）

- **name**: Sentinel1_OrbitDownloader.exe（本地）
- **url**: 本地二进制，无源码
- **license**: 不明（二进制）
- **last_checked_date**: 2026-06-18
- **purpose**: Sentinel-1 轨道下载（成品 exe）。
- **use_as_dependency**: 否。
- **copy_code_allowed**: N/A（无源码）。
- **integration_plan**: 仅作行为参考（下载哪些轨道、命名），实现走 sentineleof 适配器。
- **risk**: 中。无法审计来源 / 不可再分发。
- **notes**: 后续 Task=Task 009（行为参考）。

### 10. EZ-InSAR (MIESAR)

- **name**: EZ-InSAR（alexisInSAR/EZ-InSAR，前身 MIESAR；UCD）
- **url**: https://github.com/alexisInSAR/EZ-InSAR
- **license**: **GPL-3.0**（另有 2025 Python 分支）
- **last_checked_date**: 2026-06-23
- **purpose**: MATLAB GUI 工具箱，封装 ISCE+StaMPS/MintPy。三模块：数据准备 / ISCE 处理 / 时间序列。多传感器：S1 IW+Stripmap、TSX/PAZ、CSK、ALOS-2，各有 SLC 目录约定。
- **use_as_dependency**: **否（GPL-3.0 传染 + MATLAB，非 Python 库）**。
- **copy_code_allowed**: **否（硬性，GPL-3.0）**。
- **integration_plan**: 仅作架构 / UX 参考。借鉴其「数据准备模块」工作流（AOI→下载 SLC/orbit/DEM→按 `slc/` 目录约定组织→配准设置）与多传感器抽象，落到我们自研的 GUI/CLI 与 `core/models`；**不 import、不复制、不分发**其代码。
- **risk**: **高（GPL 传染）**。一旦复制 / import 会污染 MIT 主项目许可证；MATLAB 依赖也超出本项目 Python 栈。
- **notes**: 可借鉴点=数据准备流程 / 三模块布局 / 多传感器 SLC 目录约定（与涪城 FC-1 stripmap 路径相关）。不应实现=照搬其 ISCE/StaMPS 处理链（越过「只做数据准备」边界）。后续 Task=GUI / 多传感器准备（仅概念参考）。

### 11. awesome-sar（精选清单）

- **name**: awesome-sar（RadarCODE/awesome-sar）
- **url**: https://github.com/RadarCODE/awesome-sar
- **license**: 清单仓库本身（以仓库为准）；**所链接各工具各自许可证不同，选用前须逐一核对**。
- **last_checked_date**: 2026-06-23
- **purpose**: SAR 软件 / 库 / 资源精选清单（InSAR 处理、时序、对流层改正、数据下载、地理工具等）。
- **use_as_dependency**: 否（它是清单，不是库）。
- **copy_code_allowed**: N/A（清单本身；具体工具按各自许可证）。
- **integration_plan**: 作「候选第三方工具」目录使用；**选用任一条目前，按本文件规则单独登记该工具的许可证 / 边界**。
- **risk**: 低（清单本身）；但下游工具许可证差异大（如 PyAPS / MintPy = GPL；RAiDER = Apache；asf_search / sentineleof = BSD/MIT）。
- **notes**: 对本项目有用的条目分类：下游处理器（ISCE2 / GMTSAR / SNAP-S1TBX / Doris）、时序（MintPy / StaMPS / GIAnT / PyRate）、对流层（PyAPS / TRAIN / kite / RAiDER）、数据下载（EODAG / CDSETool / SSARA / asf_search）、地理（GDAL / QGIS）、地形 geocoding（sarsen / pyroSAR）。

### 12. GeographicLib geoid data (egm96-15)

- **name**: GeographicLib geoid grids（egm96-15.pgm）
- **url**: https://geographiclib.sourceforge.io/ （geoids-distrib/egm96-15.tar.bz2）
- **license**: GeographicLib 本体 MIT；geoid 网格派生自 **NGA EGM96（public domain）**。
- **last_checked_date**: 2026-06-24
- **purpose**: 提供 EGM96 大地水准面起伏 N（15′ 全球网格），用于把正高（EGM96/EGM2008）DEM 转为 WGS84 椭球高（h = H + N）。
- **use_as_dependency**: 否（只内置**数据文件**，不依赖 GeographicLib 代码）。
- **copy_code_allowed**: N/A（仅数据；public domain 模型）。
- **integration_plan**: **已落地（Task 053）**。用 `scripts/build_geoid_npz.py` 把官方 `egm96-15.pgm` 解析为精简 `src/insar_prep/data/egm96_15.npz`（undulation + 地理参数），运行时由 `providers/dem/geoid.py` 仅用 numpy 双线性插值；**未复制任何 GeographicLib 源代码**。
- **risk**: 低。仅 EGM96；EGM2008 源 DEM 用 EGM96 近似时在报告/日志显式 WARNING，并支持 `--geoid-grid` 传入自备 EGM2008 网格。
- **notes**: 可借鉴点=PGM Offset/Scale 头 + 北→南/0→360 网格约定。校验=全球极值（印度洋 -107 m / 巴新 +85 m）位置吻合。

### 13. rasterio

- **name**: rasterio (rasterio/rasterio)
- **url**: https://github.com/rasterio/rasterio
- **license**: BSD-3-Clause（wheel 内置 GDAL，MIT/X 风格）。
- **last_checked_date**: 2026-06-24
- **purpose**: 读写 GeoTIFF DEM（含 CRS/transform/nodata），供垂直基准转换分块读写。
- **use_as_dependency**: 是（**可选 `convert` extra**；离线核心从不需要）。
- **copy_code_allowed**: 否（封装不复制）。
- **integration_plan**: **已落地（Task 053）**。`providers/dem/converter.py` 懒加载 rasterio，分块读原始 DEM、加 geoid 起伏、写椭球 DEM（`.part`+原子改名），GUI exe 打包 `--collect-all rasterio`；精简 CLI exe 不含。
- **risk**: 中（GDAL 二进制较重，仅在 convert extra / GUI exe 内）。
- **notes**: 可借鉴点=`Window`/`profile`/`transform` API。不应实现=自写 GeoTIFF 解析。

### 14. GACOS（Newcastle University）

- **name**: GACOS (Generic Atmospheric Correction Online Service for InSAR)
- **url**: http://www.gacos.net/
- **license**: 产物受 GACOS 使用条款约束，**须按官方要求引用文献**；**无公开下载 API**。
- **last_checked_date**: 2026-06-24
- **purpose**: 天顶对流层延迟图（`YYYYMMDD.ztd` 小端 4 字节 float + `.ztd.rsc` 头，或 GeoTIFF）。
- **use_as_dependency**: N/A（**无 API**：网页表单提交 + 邮件链接下载；官方 ReadMe 称"will soon release an API"但至今未出）。
- **copy_code_allowed**: N/A。
- **integration_plan**: **已落地（Task 012/013/053）**。`planner` 规划提交日期+bbox（用户手动提交）；`importer`（`gacos-import`）把用户**手动下载**的产物解压/按日期归位/完整性校验（`.ztd` 字节数须 = 4×WIDTH×FILE_LENGTH）；`import_checker` 只读核对。**绝不** submit/scrape/automate 其网页表单、不驱动浏览器、不存凭据。
- **risk**: 中。完全手动；须标注引用；`.ztd`/`.rsc` 格式以官方 ReadMe 为准。
- **notes**: 可借鉴点=`.ztd`/`.rsc` 文件约定、5×5°/10 天（现 10×10°/20 期）提交上限。不应实现=任何网页自动化下载。

---

## 分析汇总表

| # | 名称 | 许可证 | 作依赖? | 可复制源码? | 集成方式 | 后续 Task |
|---|---|---|---|---|---|---|
| 1 | asf_search | BSD-3-Clause | 否(改用 requests) | 否(仅概念) | 概念借鉴 ASFSession.rebuild_auth | 049(已落地) |
| 2 | sentineleof | MIT | 是 | 否（封装） | `providers/orbit` 适配器 | 009 |
| 3 | OpenTopography API | 条款/数据许可 | N/A | N/A | `providers/dem` 直连 API | 010 / 052(已落地) |
| 4 | pyroSAR | MIT | 否/谨慎 | 否 | 仅架构参考 | 002 / 011 |
| 5 | RAiDER | Apache-2.0 | 可选(v2+) | 否（留NOTICE） | `providers/atmosphere` 可选 | 012+ |
| 6 | PyAPS | **GPL-3.0** | **否(传染)** | **否** | 仅外部工具/接口 | 012+ |
| 7 | geo-downloader | MIT | 否(非Py) | 否 | 下载器/GUI 交互参考 | 008 / 014 |
| 8 | DEMdownloader(本地) | **不明** | 否 | **否** | 仅概念参考(含.env,隔离) | 005 / 052(已落地,仅概念) |
| 9 | OrbitDownloader.exe(本地) | 不明 | 否 | N/A | 仅行为参考 | 009 |
| 10 | EZ-InSAR (MIESAR) | **GPL-3.0** | **否(传染/MATLAB)** | **否** | 仅架构/UX 参考(数据准备模块/多传感器) | GUI/多传感器 |
| 11 | awesome-sar | 清单(各工具不同) | 否(清单) | N/A | 候选工具目录;选用前逐一登记 | — |
| 12 | GeographicLib geoid(egm96-15) | MIT/public-domain | 否(仅数据) | N/A | 内置 npz, `providers/dem/geoid` | 053(已落地) |
| 13 | rasterio | BSD-3-Clause | 是(convert extra) | 否(封装) | `providers/dem/converter` 懒加载 | 053(已落地) |
| 14 | GACOS | 条款/无API | N/A | N/A | `gacos-import` 仅整理手动下载产物 | 012/013/053(已落地) |
