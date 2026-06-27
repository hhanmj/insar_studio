# Sentinel-2/CDSE、GACOS 内嵌与队列化计划

## 目标

把当前“项目 / 研究区”驱动的操作方式逐步收敛为“范围 + 数据源 + 下载任务队列”：

- 顶部和左侧不再强调项目切换。
- 每一次检索、导入、下载、DEM/GACOS/Orbit 都形成可恢复任务。
- 下载中心负责显示排队、并发、暂停、恢复、失败、删除和历史。

## 1. 去项目化

短期保留内部工作目录模型，用于兼容已有 AOI、报告和输出路径；UI 上弱化项目概念：

- 顶部只显示“输出根目录 / 当前范围 / 当前任务数”。
- 新任务开始时再确认输出目录。
- 任务保存到下载中心，不再要求用户先理解项目、研究区。
- AOI 作为全局“当前范围”，各功能默认沿用，允许单独覆盖。

后续重构：

- 新增 `TaskWorkspace` 或 `DownloadTask` 表达一次完整任务。
- `Region` 仅作为可选 AOI/范围，不再作为主导航对象。
- 历史任务可重新打开、复制参数、继续下载。

## 2. Sentinel-2 / CDSE 接入

`sentinel2/哥白尼就批量下载S2/copernicus_batch_download.py` 可作为基础，不建议直接嵌入 UI 调用；应拆成 provider：

- `providers/cdse/client.py`
  - CDSE token 获取、刷新、超时、代理。
  - OData 查询请求。
  - `$value` / `$zip` 下载。
- `providers/cdse/search.py`
  - collection、productType、cloudCover、bbox/GeoJSON、时间范围。
  - 支持 Sentinel-2 L1C/L2A，保留扩展到 Sentinel-3/Landsat/COP-DEM。
- `providers/cdse/downloader.py`
  - `.part` 断点续传。
  - 并发下载。
  - 下载速度、当前文件进度、总进度。
- `desktop/api.py`
  - `search_cdse_products`
  - `start_cdse_download`
  - `pause/resume/stop_cdse_download`
  - `get_cdse_download_status`
- UI
  - Sentinel-2 标签启用。
  - 地图显示产品覆盖范围。
  - 云量、产品级别、瓦片号、轨道号筛选。

参考脚本评估：

- `copernicus_batch_download.py`：可复用核心逻辑，已有 OData、token 刷新、manifest、`.part`。
- `参考2/MSI_batch_download.py` / `OLCI_batch_download.py`：只参考 OData 字段，不直接使用。
- `参考1.txt`：旧 SciHub/sentinelsat 思路，不作为实现基础。

## 3. GACOS 内嵌

可以尝试内嵌，但要按网站限制分两种模式：

- 优先模式：软件内 WebView 打开 GACOS 页面，用户登录/提交，软件保存请求参数和结果下载目录。
- 备用模式：如果 GACOS 禁止 iframe/WebView 或存在验证码，软件打开独立浏览器，同时保留软件内参数生成和结果导入。

后续功能：

- 根据 SLC/GRD 目录、ASF py/metalink/metadata 自动解析日期。
- 自动生成 GACOS 请求列表。
- 导入下载后的 `.ztd` / `.rsc`，按日期匹配 SAR 场景。
- 下载中心显示 GACOS 请求状态和导入状态。

## 4. ASF / 元数据真实进度

当前已把 ASF 检索和导入补全进度从“动画”改为后端状态：

- 检索阶段：准备请求、ASF 请求、解析结果。
- 导入补全阶段：按批次显示 ASF 元数据补全进度。

后续继续增强：

- 为 CMR 备用检索也显示集合级进度。
- 元数据失败时在结果列表里标明原因。
- GRD/SLC 分产品类型显示元数据补全来源。
