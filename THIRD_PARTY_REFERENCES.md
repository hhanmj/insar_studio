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
- **last_checked_date**: 2026-06-18
- **purpose**: ASF 目录检索、baseline / stack、SLC 下载（Earthdata 认证）。
- **use_as_dependency**: 是（推荐，作为 ASF Provider 核心依赖）。
- **copy_code_allowed**: 否（许可证允许，但本项目政策为封装不复制）。
- **integration_plan**: 在 `providers/asf/` 封装适配器，调用 `geo_search/granule_search/product_search/search/stack`；`ASFSession` 认证用 keyring 注入，不落明文。
- **risk**: 低。需 Earthdata 凭据（走 keyring）；网络在单测中必须 mock。
- **notes**: 可借鉴点=检索函数 API 形态、结果→下载流、平台/极化/beam 常量。不应实现=自己重写一套 ASF 检索协议。后续 Task=Task 006（cart/URL 解析交叉校验）、Task 005（v1.5 检索）。

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
- **last_checked_date**: 2026-06-18
- **purpose**: 按 bbox 下载 COP30/COP90/SRTMGL1/NASADEM/ALOS 等 DEM。
- **use_as_dependency**: N/A（直接 HTTP 调官方 API，不依赖个人封装库）。
- **copy_code_allowed**: N/A（以官方 API 文档为准）。
- **integration_plan**: 在 `providers/dem/` 直接用 `requests` 调 `globaldem`（demtype + south/north/west/east + API_Key），保存原始 DEM。
- **risk**: 中。需 API key（keyring）；有速率限制；**数据需按各数据集要求标注引用**。
- **notes**: 可借鉴点=数据集枚举、bbox 参数、输出格式。不应实现=绕过限速 / 隐藏数据来源。后续 Task=Task 010。

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
- **notes**: 可借鉴点=DEM API 分层、administrative_boundary（与中国边界合规交叉印证）、validator。不应复制=任何源码与 `.env`。后续 Task=Task 005（行政边界）、Task 010/011（DEM）。

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

---

## 分析汇总表

| # | 名称 | 许可证 | 作依赖? | 可复制源码? | 集成方式 | 后续 Task |
|---|---|---|---|---|---|---|
| 1 | asf_search | BSD-3-Clause | 是 | 否（封装） | `providers/asf` 适配器 | 006 / 005 |
| 2 | sentineleof | MIT | 是 | 否（封装） | `providers/orbit` 适配器 | 009 |
| 3 | OpenTopography API | 条款/数据许可 | N/A | N/A | `providers/dem` 直连 API | 010 |
| 4 | pyroSAR | MIT | 否/谨慎 | 否 | 仅架构参考 | 002 / 011 |
| 5 | RAiDER | Apache-2.0 | 可选(v2+) | 否（留NOTICE） | `providers/atmosphere` 可选 | 012+ |
| 6 | PyAPS | **GPL-3.0** | **否(传染)** | **否** | 仅外部工具/接口 | 012+ |
| 7 | geo-downloader | MIT | 否(非Py) | 否 | 下载器/GUI 交互参考 | 008 / 014 |
| 8 | DEMdownloader(本地) | **不明** | 否 | **否** | 仅概念参考(含.env,隔离) | 005 / 010 / 011 |
| 9 | OrbitDownloader.exe(本地) | 不明 | 否 | N/A | 仅行为参考 | 009 |
