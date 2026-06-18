# InSAR Data Preparation Assistant 开发手册

版本：v0.1-draft  
目标软件：ENVI SARscape  
项目定位：面向 InSAR 初学者的多区域 SARscape 前置数据准备、辅助产品组织与质量检查平台。

---

## 0. 项目一句话定义

本工具不是完整 InSAR 处理软件，而是一个用于 SARscape 处理前的数据准备助手。它帮助用户组织 Sentinel-1 SLC、精密轨道、DEM、大气延迟产品和标准目录结构，并通过一致性检查、日志、报告和错误弹窗降低初学者在数据准备阶段的错误率。

---

## 1. 项目边界

### 1.1 本工具要做什么

本工具主要完成：

1. 解析 ASF Vertex 导出的 cart 文件、Python 下载脚本、CSV、GeoJSON 或 URL 列表；
2. 可选接入 ASF 轻量检索；
3. 下载 Sentinel-1 SLC；
4. 检查 SLC 一致性与 AOI 覆盖；
5. 匹配 Sentinel-1 精密轨道；
6. 下载、裁剪、重投影 DEM；
7. 完成 DEM 正高 / 椭球高转换；
8. 输出符合 SARscape 识别规则的 DEM；
9. 生成 GACOS 请求批次并检查用户导入的 GACOS 产品；
10. 后续可接入 ERA5 / PyAPS / RAiDER；
11. 支持用户导入范围文件、手动输入边界和合规行政区划边界；
12. 支持多区域、多任务、并行或排队下载；
13. 生成 SARscape-ready 目录；
14. 输出 `manifest.csv`、日志和数据准备报告。

### 1.2 本工具暂时不做什么

第一阶段不做：

1. 不替代 SARscape；
2. 不自动驱动 SARscape 执行 SBAS、DInSAR 或解缠；
3. 不做完整 InSAR 时间序列处理；
4. 不做 GACOS 静默自动点击批量提交；
5. 不绕过任何外部服务限制；
6. 不默认分发未经确认合规的中国行政区划边界；
7. 不把账号、密码、token 明文写入配置文件或日志；
8. 不把所有 SAR 卫星和所有 DEM 源一次性纳入第一版。

---

## 2. 总体架构

### 2.1 核心层级

项目从单一 Project 模型升级为：

```text
Workspace
└── Project
    ├── Region
    │   ├── AOI
    │   ├── SLC scenes
    │   ├── Orbits
    │   ├── DEM
    │   ├── Atmosphere
    │   └── Reports
    └── Job Queue
        └── Tasks
```

### 2.2 概念定义

**Workspace**  
一个工作空间，包含多个项目、缓存、全局设置和全局日志。例如：

```text
D:/InSAR_Workspace
```

**Project**  
一个研究主题或一次数据准备任务。例如：

```text
south_china_insar_2026
```

**Region**  
项目中的一个具体处理区域。例如：

```text
guangdong
guangxi
shiliushubao
```

**Job**  
用户发起的一组任务。例如“下载广东 SLC + 轨道 + DEM”。

**Task**  
最小执行单元。例如下载一景 SLC、下载一个 DEM、匹配一个轨道文件。

---

## 3. 推荐技术栈

### 3.1 Python 版本

建议使用 Python 3.11。  
原因：地理空间库、GUI 库、打包工具和科学计算库兼容性较稳。

### 3.2 项目管理

建议使用 `uv` 管理环境和依赖。

项目根目录应包含：

```text
pyproject.toml
uv.lock
.python-version
README.md
DEVELOPMENT_MANUAL.md
CURSOR_OPUS_GUIDE.md
CHANGELOG.md
LICENSE
```

常用命令：

```bash
uv sync
uv run insar-prep --help
uv run pytest
uv run ruff check .
uv run ruff format .
```

### 3.3 GUI 框架

建议正式版使用 PySide6。  
Streamlit 可用于早期原型，但不建议作为长期桌面软件框架。

### 3.4 地理空间处理库

核心依赖建议：

```text
rasterio
pyproj
shapely
geopandas
numpy
pandas
requests
pydantic
rich
keyring
```

可选依赖：

```text
cdsapi
pyaps3
raider
```

### 3.5 测试与规范

建议使用：

```text
pytest
pytest-cov
ruff
mypy 或 pyright
pre-commit
GitHub Actions
```

---

## 4. 仓库目录结构

推荐结构：

```text
insar-data-prep-assistant/
├── pyproject.toml
├── uv.lock
├── .python-version
├── README.md
├── DEVELOPMENT_MANUAL.md
├── CURSOR_OPUS_GUIDE.md
├── CHANGELOG.md
├── LICENSE
├── .gitignore
├── .env.example
├── configs/
│   ├── default_settings.yaml
│   ├── logging.yaml
│   └── providers.yaml
├── src/
│   └── insar_prep/
│       ├── __init__.py
│       ├── cli/
│       │   └── main.py
│       ├── gui/
│       │   ├── app.py
│       │   ├── main_window.py
│       │   ├── views/
│       │   └── widgets/
│       ├── core/
│       │   ├── config.py
│       │   ├── logging.py
│       │   ├── security.py
│       │   ├── exceptions.py
│       │   ├── models.py
│       │   ├── naming.py
│       │   ├── paths.py
│       │   └── state.py
│       ├── providers/
│       │   ├── asf/
│       │   ├── orbit/
│       │   ├── dem/
│       │   ├── atmosphere/
│       │   ├── gacos/
│       │   └── admin_boundary/
│       ├── processing/
│       │   ├── validators.py
│       │   ├── download.py
│       │   ├── dem_vertical.py
│       │   ├── dem_clip.py
│       │   ├── orbit_match.py
│       │   ├── gacos_batch.py
│       │   └── report.py
│       ├── sar_apps/
│       │   ├── sarscape.py
│       │   ├── isce.py
│       │   └── mintpy.py
│       └── utils/
│           ├── time.py
│           ├── hashing.py
│           ├── file_check.py
│           └── network.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── e2e/
├── docs/
│   ├── user_manual.md
│   ├── developer_manual.md
│   ├── installation.md
│   ├── quick_start.md
│   ├── asf_workflow.md
│   ├── orbit_workflow.md
│   ├── dem_vertical_datum.md
│   ├── gacos_workflow.md
│   ├── atmospheric_products.md
│   ├── admin_boundary_compliance.md
│   ├── sarscape_ready_directory.md
│   └── troubleshooting.md
├── scripts/
│   ├── build_windows.ps1
│   ├── build_linux.sh
│   └── make_test_project.py
└── .github/
    ├── workflows/
    │   ├── ci.yml
    │   └── release.yml
    └── ISSUE_TEMPLATE/
        ├── bug_report.md
        ├── feature_request.md
        └── data_source_error.md
```

---

## 5. SARscape 适配硬约束

### 5.1 命名红线

SARscape 输出目录和文件名必须使用 snake_case。禁止使用：

```text
-
空格
中文标点
特殊符号
过长路径
```

建议只允许：

```text
小写英文字母
数字
下划线
```

示例：

```text
错误：SARscape-ready
正确：06_sarscape_ready

错误：Guangxi-stack-2024
正确：guangxi_stack_2024

错误：COP30-WGS84-ellipsoid
正确：cop30_wgs84_ellipsoid
```

### 5.2 SARscape 安全命名函数

必须建立统一函数：

```python
def sarscape_safe_name(value: str) -> str:
    """Return a SARscape-safe snake_case name."""
```

规则：

1. 转小写；
2. 空格、连字符、中文标点、特殊符号替换为 `_`；
3. 多个 `_` 合并为一个；
4. 去除首尾 `_`；
5. 不允许空字符串；
6. 过长名称自动截断并保留唯一后缀；
7. 所有 SARscape-ready 输出都必须调用该函数。

### 5.3 DEM 文件名红线

SARscape 转换椭球高后的 DEM 只识别以 `_dem` 结尾的文件。因此最终输出必须为：

```text
<region_safe_name>_dem.tif
```

示例：

```text
guangdong_dem.tif
guangxi_dem.tif
shiliushubao_dem.tif
```

通用 DEM 模块可以输出：

```text
shiliushubao_ellipsoid.tif
```

但 SARscape adapter 必须生成：

```text
06_sarscape_ready/DEM/shiliushubao_dem.tif
```

### 5.4 SARscape-ready 目录

推荐结构：

```text
06_sarscape_ready/
├── SLC/
├── ORBITS/
├── DEM/
│   └── shiliushubao_dem.tif
└── ATMOSPHERE/
```

---

## 6. 标准 Workspace / Project / Region 目录

推荐结构：

```text
Workspace/
├── projects/
│   └── south_china_insar_2026/
│       ├── project.yaml
│       ├── regions/
│       │   ├── guangdong/
│       │   │   ├── 00_config/
│       │   │   ├── 01_asf_cart/
│       │   │   ├── 02_slc/
│       │   │   ├── 03_orbits/
│       │   │   ├── 04_dem/
│       │   │   ├── 05_atmosphere/
│       │   │   ├── 06_sarscape_ready/
│       │   │   ├── 07_reports/
│       │   │   └── logs/
│       │   └── guangxi/
│       │       ├── 00_config/
│       │       ├── 01_asf_cart/
│       │       ├── 02_slc/
│       │       ├── 03_orbits/
│       │       ├── 04_dem/
│       │       ├── 05_atmosphere/
│       │       ├── 06_sarscape_ready/
│       │       ├── 07_reports/
│       │       └── logs/
│       └── project_reports/
├── cache/
│   ├── slc/
│   ├── orbits/
│   ├── dem/
│   ├── atmosphere/
│   └── admin_boundaries/
└── global_logs/
```

---

## 7. 数据模型

### 7.1 Workspace

```text
workspace_id
workspace_root
created_at
updated_at
cache_root
global_settings
```

### 7.2 Project

```text
project_id
workspace_id
project_name
project_root
created_at
updated_at
target_software
regions
jobs
notes
```

### 7.3 Region

```text
region_id
project_id
region_name
region_safe_name
region_root
aoi_source
aoi_geometry_path
aoi_bbox
aoi_crs
aoi_buffer_settings
created_at
updated_at
```

### 7.4 Scene

```text
scene_id
platform
sensor
product_type
beam_mode
polarization
acquisition_datetime
orbit_direction
relative_orbit
absolute_orbit
frame
path
url
local_path
file_size_remote
file_size_local
checksum
download_status
zip_valid
processing_aoi_id
processing_aoi_name
asf_footprint_coverage
safe_metadata_coverage
coverage_warning
```

### 7.5 DownloadTask

```text
task_id
job_id
region_id
provider
task_type
input
output
status
progress
retry_count
created_at
started_at
finished_at
error_code
error_message
```

### 7.6 DEM Product

```text
dem_id
region_id
source
dataset
resolution
original_vertical_datum
target_vertical_datum
geoid_model
is_dsm
is_ellipsoidal
input_path
ellipsoid_output_path
sarscape_ready_path
aoi_bbox
crs
nodata
min_elevation
max_elevation
mean_elevation
processing_log
```

### 7.7 AtmosphericProduct

```text
atmo_id
region_id
provider
method
date
input_path
output_path
coverage_status
matched_scene_ids
status
notes
```

---

## 8. AOI / 范围输入

### 8.1 基本原则

SLC 影像范围不完全一致，精确 footprint 往往需要下载 SAFE 后才能提取。因此 DEM、GACOS、ERA5、RAiDER 等辅助产品不应直接依赖单景 SLC 范围，而应优先使用用户指定的处理范围。

必须区分：

```text
SLC footprint: 影像自身覆盖范围，用于覆盖检查。
Processing AOI: 用户指定处理范围，用于 DEM / GACOS / ERA5 / 输出目录。
Download AOI: Processing AOI + buffer，用于辅助产品下载。
```

### 8.2 支持的 AOI 输入方式

必须支持：

```text
1. 手动输入 W/E/S/N
2. 导入矢量范围文件
3. 从行政区划边界选择
4. 从地图界面绘制矩形或多边形
5. 从已有项目复制 AOI
```

### 8.3 手动输入 W/E/S/N

字段：

```text
West / min longitude
East / max longitude
South / min latitude
North / max latitude
CRS: EPSG:4326
```

检查项：

```text
West < East
South < North
经度范围在 -180 到 180
纬度范围在 -90 到 90
AOI 面积是否过大
是否跨越 180° 经线
```

### 8.4 矢量范围文件

支持：

```text
Shapefile
GeoJSON
GeoPackage
KML
KMZ
WKT 文本
```

### 8.5 多要素 AOI 处理模式

多要素输入应提供三种模式：

#### 8.5.1 Merge_to_one_region

将所有要素合并为一个处理区。适用于多个斑块共同构成同一研究区。

输出：

```text
多个要素 → 1 个 Region → 1 套 DEM/GACOS/报告
```

#### 8.5.2 Select_one_feature

用户从属性表中选择一个要素作为处理区。适用于矢量文件包含很多行政区或很多滑坡，但本次只处理其中一个。

输出：

```text
多个要素 → 选择 1 个要素 → 1 个 Region
```

#### 8.5.3 Split_to_regions

每个要素生成一个独立处理区。适用于一个文件中包含多个彼此独立的研究区。

输出：

```text
多个要素 → N 个 Region → N 套 DEM/GACOS/报告
```

### 8.6 AOI buffer

默认设置：

```text
DEM buffer: 0.02°
GACOS buffer: 0.05°
ERA5 buffer: 0.25°
```

报告中必须写明：

```text
Processing AOI: 用户指定研究区
Download AOI: Processing AOI + buffer
```

---

## 9. 中国行政区划边界合规要求

### 9.1 硬约束

中国行政区划边界必须使用合规边界，不得默认使用未经确认的全球开源边界库作为中国行政区划边界。

允许方式：

```text
1. 用户提供的有审图号边界；
2. 天地图或其他合规来源提供的有审图号边界；
3. 用户自定义边界，但公开使用成果时需自行处理地图合规问题。
```

### 9.2 禁止行为

第一版禁止：

```text
默认内置未经确认合规的中国行政区划 shp；
默认用 GADM / geoBoundaries / Natural Earth 作为中国行政区划边界；
在报告中暗示非审定边界可直接用于公开地图成果；
删除边界来源、审图号、获取日期等元数据。
```

### 9.3 元数据记录

中国行政区划边界必须记录：

```text
boundary_source
provider
review_number
download_or_import_date
license_or_terms
admin_level
name_field
crs
file_path
notes
```

### 9.4 界面提示

选择中国行政区划边界时，界面提示：

```text
中国行政区划边界涉及地图合规要求。请使用带审图号的边界数据，例如用户自备审定边界或天地图等合规来源。工具将记录边界来源、审图号、获取时间和使用范围。
```

---

## 10. SLC footprint 与 AOI 覆盖检查

### 10.1 两级检查

```text
Pre-download check:
使用 ASF 元数据 footprint 进行初步覆盖检查。

Post-download check:
下载 SAFE 后读取 manifest / annotation 元数据进行严格检查。
```

### 10.2 覆盖状态

```text
COVERED
PARTIALLY_COVERED
NOT_COVERED
UNKNOWN
```

### 10.3 报告示例

```text
警告：3 景 SLC 仅部分覆盖用户指定 AOI。继续处理可能导致 SARscape 裁剪范围不完整。建议检查 ASF 影像选择范围，或缩小处理 AOI。
```

---

## 11. ASF 模块

### 11.1 开发阶段

```text
v1.0: ASF cart 导入模式
v1.5: ASF guided search 模式
v2.0: InSAR stack builder 模式
```

### 11.2 v1.0 支持输入

```text
ASF Vertex 导出的 Python 下载脚本
CSV
GeoJSON
URL 文本
用户手动粘贴 URL 列表
```

### 11.3 质检项

导入后检查：

```text
是否均为 SLC
是否均为 Sentinel-1
是否均为 IW 模式
是否极化一致
是否轨道方向一致
是否相对轨道一致
是否时间范围异常
是否存在重复日期
是否存在重复 scene
是否 URL 缺失
是否文件名符合 Sentinel-1 命名规则
是否覆盖用户指定 AOI
```

### 11.4 v1.5 轻量检索字段

```text
AOI
开始日期
结束日期
平台：S1A / S1B / S1C
产品级别：SLC
轨道方向：Ascending / Descending
相对轨道
Beam mode：IW
极化：VV / VH / VV+VH
```

---

## 12. 下载管理器

### 12.1 目标

所有下载任务统一进入任务队列。必须支持：

```text
断点续传
失败重试
文件大小检查
zip 完整性检查
下载状态保存
软件重启后继续
重复文件跳过
```

### 12.2 并发限制

默认并发：

```text
ASF SLC 下载：2–3 个并发
轨道文件下载：3–5 个并发
DEM 下载：1–2 个并发
ERA5：1 个并发
GACOS：第一版不自动提交
```

### 12.3 Task 状态

```text
PENDING
RUNNING
PAUSED
COMPLETED
FAILED
CANCELLED
SKIPPED
WAITING_FOR_USER
```

### 12.4 Job 状态

```text
NOT_STARTED
RUNNING
COMPLETED
COMPLETED_WITH_WARNINGS
FAILED
PARTIALLY_FAILED
CANCELLED
```

---

## 13. 轨道模块

### 13.1 支持轨道类型

```text
AUX_POEORB
AUX_RESORB
AUX_MOEORB
```

### 13.2 匹配逻辑

根据 Sentinel-1 SAFE 文件名解析：

```text
platform
acquisition_start
acquisition_stop
```

轨道文件必须满足：

```text
同一卫星平台
轨道有效时间覆盖影像采集时间
优先级：POEORB > MOEORB > RESORB
```

### 13.3 输出文件

```text
03_orbits/orbit_match_table.csv
```

字段：

```text
scene_id
acquisition_datetime
platform
matched_orbit_type
matched_orbit_file
coverage_status
notes
```

---

## 14. DEM 模块

### 14.1 DEM 来源

第一版支持：

```text
OpenTopography COP30
OpenTopography COP90
OpenTopography SRTM GL1
OpenTopography SRTM GL1 Ellipsoidal
OpenTopography NASADEM
OpenTopography ALOS World 3D
OpenTopography ALOS World 3D Ellipsoidal
用户本地 DEM
```

### 14.2 默认推荐

```text
COP30
目标垂直基准：WGS84 ellipsoid height
输出格式：GeoTIFF
SARscape-ready 文件名：<region_safe_name>_dem.tif
```

### 14.3 垂直基准转换

核心关系：

```text
h = H + N
```

其中：

```text
h: ellipsoidal height
H: orthometric height
N: geoid undulation
```

必须记录：

```text
输入 DEM 垂直基准
目标垂直基准
使用的 geoid model
是否已经是 ellipsoidal DEM
是否执行了转换
```

### 14.4 防止二次转换

如果 DEM 已是 ellipsoidal，则禁止再次执行正高转椭球高。

界面警告：

```text
该 DEM 已标记为 ellipsoidal height。继续转换可能造成整体高程偏移。默认跳过垂直基准转换。
```

### 14.5 DEM 日志

`dem_processing_log.txt` 必须记录：

```text
DEM source
dataset name
download URL or provider
input file
output file
SARscape-ready output file
input CRS
output CRS
input vertical datum
target vertical datum
geoid model
clip bbox
buffer
resolution
resampling method
nodata value
min/max/mean before conversion
min/max/mean after conversion
processing time
```

---

## 15. GACOS 模块

### 15.1 模块名称

推荐名称：

```text
GACOS Request Assistant
```

不建议：

```text
GACOS Auto Downloader
```

### 15.2 原则

由于 GACOS 没有官方公开 API，第一版不做静默自动提交，不做绕过网页限制的脚本，不做批量自动点击。

### 15.3 功能

```text
从 SLC 提取日期
根据用户 AOI 生成 bbox
按日期数量自动分批
生成每批日期列表
生成 gacos_request_batches.csv
打开 GACOS 网页
用户手动提交
导入用户下载后的 GACOS 产品
检查日期完整性
检查空间范围
整理到 SARscape-ready 目录
```

### 15.4 请求批次

```text
05_atmosphere/gacos/request_batches/batch_001_dates.txt
05_atmosphere/gacos/request_batches/batch_002_dates.txt
05_atmosphere/gacos/gacos_request_batches.csv
```

CSV 字段：

```text
batch_id
date_count
dates
west
east
south
north
format
status
notes
```

### 15.5 产品导入检查

```text
是否包含所有 SLC 日期
是否有多余日期
日期格式是否为 YYYYMMDD
空间范围是否覆盖 AOI
文件格式是否一致
是否存在损坏文件
```

---

## 16. ERA5 / PyAPS / RAiDER 模块

### 16.1 开发顺序

```text
第一阶段：GACOS Request Assistant
第二阶段：ERA5 / PyAPS
第三阶段：RAiDER
第四阶段：GNSS ZTD 导入
```

### 16.2 不过度承诺

报告中必须说明：

```text
不同大气产品代表不同模型和分辨率。工具只负责数据准备和格式组织，不保证一定提高 InSAR 结果精度。
```

---

## 17. 日志系统

### 17.1 日志文件

每个 Region 必须生成：

```text
app.log        人类可读日志
task.log       任务日志
events.jsonl   机器可读事件日志
errors.log     错误日志
```

全局日志放在：

```text
Workspace/global_logs/
```

### 17.2 日志等级

```text
DEBUG
INFO
WARNING
ERROR
CRITICAL
```

### 17.3 JSONL 事件格式

```json
{
  "timestamp": "2026-06-18T00:00:00+08:00",
  "event_id": "EVT-000001",
  "workspace_id": "ws_20260618_001",
  "project_id": "proj_20260618_001",
  "region_id": "region_guangdong",
  "module": "asf",
  "event_type": "ASF_CART_IMPORTED",
  "level": "INFO",
  "message": "Imported 32 Sentinel-1 SLC scenes from ASF cart file.",
  "payload": {
    "scene_count": 32,
    "orbit_directions": ["ASCENDING"],
    "product_type": "SLC"
  }
}
```

### 17.4 事件类型

```text
APP_STARTED
WORKSPACE_CREATED
PROJECT_CREATED
REGION_CREATED
PROJECT_OPENED
AOI_IMPORTED
AOI_VALIDATED
ASF_CART_IMPORTED
ASF_SEARCH_STARTED
ASF_SEARCH_FINISHED
SCENE_VALIDATION_STARTED
SCENE_VALIDATION_FINISHED
DOWNLOAD_STARTED
DOWNLOAD_PROGRESS
DOWNLOAD_FINISHED
DOWNLOAD_FAILED
FILE_CHECK_STARTED
FILE_CHECK_FINISHED
ORBIT_MATCH_STARTED
ORBIT_MATCH_FINISHED
DEM_DOWNLOAD_STARTED
DEM_DOWNLOAD_FINISHED
DEM_VERTICAL_CONVERSION_STARTED
DEM_VERTICAL_CONVERSION_FINISHED
SARSCAPE_DEM_RENAMED
GACOS_BATCH_CREATED
GACOS_PRODUCTS_IMPORTED
REPORT_GENERATED
APP_ERROR
```

### 17.5 日志脱敏

禁止输出完整 token、密码、cookie。

允许：

```text
OpenTopography API key loaded: ****8f2a
```

禁止：

```text
OpenTopography API key loaded: abcdefg123456
```

---

## 18. 错误处理与弹窗

### 18.1 自定义异常

在 `core/exceptions.py` 中定义：

```python
class InsarPrepError(Exception):
    """Base exception for all application-specific errors."""

class ConfigError(InsarPrepError):
    """Invalid or missing configuration."""

class CredentialError(InsarPrepError):
    """Credential is missing, invalid, or cannot be accessed."""

class ProviderError(InsarPrepError):
    """External provider returned an error."""

class DownloadError(InsarPrepError):
    """Download failed or file is incomplete."""

class ValidationError(InsarPrepError):
    """Input data failed validation."""

class DemProcessingError(InsarPrepError):
    """DEM clipping, reprojection, or vertical conversion failed."""

class OrbitMatchingError(InsarPrepError):
    """No suitable orbit file can be matched."""

class AtmosphereProductError(InsarPrepError):
    """Atmospheric product is missing, invalid, or unmatched."""
```

### 18.2 错误码

```text
CFG001  项目配置文件缺失
CFG002  项目配置字段无效
AUTH001 账号凭据缺失
AUTH002 账号认证失败
ASF001  ASF cart 文件无法解析
ASF002  ASF 检索失败
ASF003  ASF 下载链接无效
AOI001  AOI 输入无效
AOI002  AOI 多要素处理失败
AOI003  中国行政区划边界缺少审图号
DL001   下载中断
DL002   文件大小不一致
DL003   zip 完整性检查失败
ORB001  未找到对应轨道文件
DEM001  DEM 下载失败
DEM002  DEM 垂直基准未知
DEM003  DEM 转椭球高失败
DEM004  SARscape DEM 命名不合规
GAC001  GACOS 日期清单生成失败
GAC002  GACOS 产品日期不完整
REP001  报告生成失败
```

### 18.3 弹窗类型

```text
Info       普通提示
Warning    可继续，但建议处理
Error      当前任务失败，但软件可继续
Critical   项目无法继续，必须修复
```

### 18.4 弹窗结构

```text
标题
一句话原因
建议操作
按钮：查看日志
按钮：忽略/稍后处理
按钮：关闭
```

示例：

```text
标题：DEM 文件命名不符合 SARscape 规则

原因：SARscape-ready DEM 文件名未以 _dem 结尾，可能无法被 SARscape 正确识别。

建议：工具将自动重命名为 shiliushubao_dem.tif，并保留原始文件。

按钮：
[自动修正] [查看日志] [关闭]
```

---

## 19. 凭据与安全

### 19.1 凭据类型

```text
NASA Earthdata / ASF username-password
Earthdata token
OpenTopography API key
Copernicus / CDS API key
GACOS email
```

### 19.2 保存原则

默认使用系统 Keyring。配置文件只保存凭据别名，不保存凭据值。

示例：

```yaml
credentials:
  asf:
    method: keyring
    service_name: insar_prep_asf
    username_alias: default
  opentopography:
    method: keyring
    service_name: insar_prep_opentopography
```

禁止：

```yaml
password: "123456"
token: "abcd..."
```

### 19.3 `.gitignore`

必须包含：

```text
.env
*.env
.netrc
credentials.yaml
secrets.yaml
*.key
*.token
```

---

## 20. manifest.csv

每个 Region 必须生成：

```text
07_reports/manifest.csv
```

字段：

```text
region_id
region_name
scene_id
platform
product_type
beam_mode
polarization
acquisition_datetime
orbit_direction
relative_orbit
absolute_orbit
url
slc_local_path
slc_download_status
slc_file_size
slc_zip_valid
processing_aoi_id
asf_footprint_coverage
safe_metadata_coverage
orbit_type
orbit_local_path
orbit_status
dem_used
dem_sarscape_ready_path
gacos_status
era5_status
warnings
```

---

## 21. 报告系统

### 21.1 Region 报告

每个 Region 生成：

```text
07_reports/data_preparation_report.md
07_reports/data_preparation_report.html
07_reports/warnings.csv
```

内容：

```text
区域基本信息
AOI 来源
AOI 合规信息
影像数量
轨道方向
相对轨道
极化
下载成功数量
下载失败数量
轨道匹配结果
DEM 来源与垂直基准
SARscape DEM 文件名
GACOS 批次与日期完整性
ERA5 / RAiDER 状态
SARscape-ready 目录
警告和建议
```

### 21.2 Project 总报告

项目级报告：

```text
project_reports/project_summary_report.md
project_reports/project_summary_report.html
```

内容：

```text
区域数量
每个区域 AOI
每个区域 SLC 数量
每个区域下载状态
每个区域轨道匹配状态
每个区域 DEM 状态
每个区域大气产品状态
全局警告
```

---

## 22. GUI 设计

### 22.1 主界面布局

推荐：

```text
左侧：Workspace / Project / Region 树
中间：当前 Region 工作流步骤
右侧：任务队列与日志摘要
底部：警告与错误提示栏
```

### 22.2 Region 工作流

```text
1. 设置 AOI
2. 导入或检索 SLC
3. 检查 SLC 覆盖和一致性
4. 下载 SLC
5. 匹配轨道
6. 下载和转换 DEM
7. 生成 GACOS 请求批次
8. 生成 SARscape-ready 目录
9. 输出报告
```

### 22.3 队列面板

字段：

```text
区域
任务类型
文件名/产品名
状态
进度
速度
剩余大小
错误数
操作
```

操作：

```text
暂停
继续
取消
重试
查看日志
打开文件夹
```

---

## 23. 命令行接口

GUI 之外必须提供 CLI。

建议命令：

```bash
insar-prep init-workspace
insar-prep create-project
insar-prep add-region
insar-prep import-aoi
insar-prep import-asf-cart
insar-prep validate-scenes
insar-prep download-slc
insar-prep match-orbits
insar-prep download-dem
insar-prep convert-dem-height
insar-prep make-gacos-batches
insar-prep import-gacos
insar-prep build-sarscape-ready
insar-prep report
```

示例：

```bash
insar-prep init-workspace --root D:/InSAR_Workspace

insar-prep create-project   --workspace D:/InSAR_Workspace   --name south_china_insar_2026

insar-prep add-region   --project D:/InSAR_Workspace/projects/south_china_insar_2026   --name guangdong   --bbox 109.5 117.5 20.0 25.5

insar-prep import-asf-cart   --region D:/InSAR_Workspace/projects/south_china_insar_2026/regions/guangdong   --file D:/Downloads/asf_cart.py
```

---

## 24. 配置文件

### 24.1 project.yaml

```yaml
project:
  name: south_china_insar_2026
  safe_name: south_china_insar_2026
  root: D:/InSAR_Workspace/projects/south_china_insar_2026
  created_at: 2026-06-18T00:00:00+08:00
  target_software: SARscape

regions:
  - name: guangdong
    safe_name: guangdong
    root: regions/guangdong
  - name: guangxi
    safe_name: guangxi
    root: regions/guangxi

sar:
  provider: ASF
  platform: SENTINEL-1
  product_type: SLC
  beam_mode: IW
  polarization: VV

dem:
  provider: OpenTopography
  dataset: COP30
  target_vertical_datum: WGS84_ELLIPSOID
  geoid_model: EGM2008
  sarscape_dem_suffix: _dem

atmosphere:
  gacos:
    enabled: true
    mode: request_assistant
  era5:
    enabled: false

logging:
  level: INFO
```

### 24.2 region.yaml

```yaml
region:
  name: guangdong
  safe_name: guangdong
  target_software: SARscape

aoi:
  source: manual_bbox
  bbox:
    west: 109.5
    east: 117.5
    south: 20.0
    north: 25.5
  crs: EPSG:4326
  buffer:
    dem: 0.02
    gacos: 0.05
    era5: 0.25

boundary_compliance:
  country: China
  requires_review_number: true
  provider: user_imported
  review_number: null
  notes: "If used for public map products, the user must provide compliant boundary metadata."
```

---

## 25. 测试规范

### 25.1 测试类型

```text
unit          单元测试
integration   模块集成测试
provider      外部服务 mock 测试
e2e           端到端小项目测试
```

### 25.2 必须测试

ASF：

```text
解析 ASF Python 下载脚本
解析 URL 列表
解析 CSV
识别重复 scene
识别非 SLC 产品
识别轨道方向混杂
识别相对轨道混杂
```

AOI：

```text
手动 bbox 校验
多要素矢量导入
Merge_to_one_region
Select_one_feature
Split_to_regions
中国行政区边界缺少审图号时提示
```

命名：

```text
SARscape-safe snake_case
连字符替换为下划线
最终 DEM 以 _dem.tif 结尾
过长名称处理
```

下载：

```text
断点续传
文件大小检查
失败重试
下载状态保存
重复文件跳过
```

轨道：

```text
从 SAFE 文件名解析时间
POEORB 匹配
MOEORB fallback
RESORB fallback
轨道时间不覆盖时报错
```

DEM：

```text
识别 DEM 垂直基准
正高转椭球高
ellipsoidal DEM 防止二次转换
裁剪 AOI
NoData 保持
```

GACOS：

```text
提取 SLC 日期
日期去重
按批次切分
生成请求文件
导入 GACOS 文件
识别缺失日期
```

报告：

```text
manifest.csv 生成
warnings.csv 生成
markdown 报告生成
HTML 报告生成
```

---

## 26. Git 开发流程

### 26.1 分支

```text
main       稳定版本
dev        日常开发
feature/*  单个功能
fix/*      bug 修复
docs/*     文档修改
```

### 26.2 commit 规范

```text
feat: add ASF cart parser
fix: handle incomplete SLC download
docs: update DEM vertical datum guide
test: add orbit matching tests
refactor: simplify downloader state machine
chore: update dependencies
```

### 26.3 PR 检查清单

```text
代码能运行
测试通过
Ruff 检查通过
无明文 token 或密码
新增功能有日志
新增功能有测试
用户可见错误有错误码
文档已更新
没有破坏 SARscape 命名规则
```

---

## 27. GitHub Actions

建议 CI：

```yaml
name: CI

on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [main, dev]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5

      - name: Set up Python
        run: uv python install 3.11

      - name: Install dependencies
        run: uv sync --all-extras --dev

      - name: Ruff check
        run: uv run ruff check .

      - name: Ruff format check
        run: uv run ruff format --check .

      - name: Run tests
        run: uv run pytest
```

---

## 28. 版本路线

```text
0.1.0  项目骨架 + CLI
0.2.0  Workspace / Project / Region 数据模型
0.3.0  日志系统 + 错误码
0.4.0  AOI 输入 + 多要素处理
0.5.0  ASF cart 解析 + Scene 质检
0.6.0  下载管理器 + 任务队列
0.7.0  轨道匹配
0.8.0  OpenTopography DEM 下载
0.9.0  DEM 垂直基准转换 + SARscape DEM 命名
0.10.0 GACOS Request Assistant
0.11.0 报告系统
0.12.0 GUI beta
1.0.0  第一个稳定版本
```

---

## 29. 第一阶段任务拆分

### Task 001：建立项目骨架

目标：

```text
创建 pyproject.toml
创建 src/insar_prep
创建 CLI 入口
创建 tests
配置 ruff
配置 pytest
配置 GitHub Actions
```

验收标准：

```text
uv sync 成功
uv run insar-prep --help 成功
uv run pytest 成功
uv run ruff check . 成功
```

### Task 002：核心数据模型

目标：

```text
实现 Workspace
实现 Project
实现 Region
实现 Scene
实现 DownloadTask
实现 DemProduct
实现 AtmosphericProduct
```

验收标准：

```text
所有模型可序列化为 dict/json
非法字段能报错
测试覆盖基本字段
```

### Task 003：SARscape 命名工具

目标：

```text
实现 sarscape_safe_name()
实现 SARscape DEM 输出命名
禁止连字符
禁止空格
最终 DEM 以 _dem.tif 结尾
```

验收标准：

```text
所有 SARscape-ready 输出路径通过命名检查
测试覆盖中文、空格、连字符、特殊符号、过长路径
```

### Task 004：日志系统

目标：

```text
实现统一 logger
输出 app.log
输出 task.log
输出 events.jsonl
输出 errors.log
支持项目级和区域级日志目录
```

验收标准：

```text
创建 Region 后 logs/ 自动生成
事件日志为合法 JSONL
错误日志不显示密码和 token
```

### Task 005：AOI 输入模块

目标：

```text
支持 W/E/S/N 手动输入
支持 GeoJSON / Shapefile / GeoPackage / KML
支持多要素识别
支持 Merge_to_one_region / Select_one_feature / Split_to_regions
```

验收标准：

```text
能正确读取多要素文件
能显示属性表摘要
能生成 Region AOI
能输出 AOI bbox
```

### Task 006：ASF cart 解析器

目标：

```text
解析 ASF Python 下载脚本
解析 URL txt
解析 CSV
输出 Scene 列表
```

验收标准：

```text
能解析测试文件
能识别重复影像
能识别非 Sentinel-1 SLC
生成 parsed_scenes.csv
```

### Task 007：影像一致性检查

目标：

```text
检查 product type
检查 beam mode
检查 polarization
检查 orbit direction
检查 relative orbit
检查重复日期
检查 AOI 覆盖
```

验收标准：

```text
输出 warnings.csv
报告中给出可读建议
```

### Task 008：下载管理器和任务队列

目标：

```text
实现下载任务状态
支持断点续传
支持失败重试
支持文件大小检查
支持多区域并行或排队
```

验收标准：

```text
可 mock 下载
中断后可恢复
失败任务不影响其他任务
广东和广西任务可同时存在
```

### Task 009：轨道匹配

目标：

```text
解析 Sentinel-1 文件名
解析 orbit 文件名
匹配 POEORB / MOEORB / RESORB
生成 orbit_match_table.csv
```

验收标准：

```text
同平台、时间覆盖正确匹配
POEORB 优先
缺 POEORB 时 fallback 到 MOEORB 或 RESORB
```

### Task 010：OpenTopography DEM 下载

目标：

```text
接入 OpenTopography Global Datasets API
支持 COP30
支持 bbox 下载
保存原始 DEM
```

验收标准：

```text
mock API 测试通过
失败时有错误码
项目中生成 DEM 记录
```

### Task 011：DEM 垂直基准转换

目标：

```text
实现正高转椭球高
支持 EGM96 / EGM2008
防止二次转换
输出 dem_processing_log.txt
输出 <region_safe_name>_dem.tif
```

验收标准：

```text
小 DEM 测试通过
转换前后统计记录正确
ellipsoidal DEM 不重复转换
SARscape-ready DEM 命名合规
```

### Task 012：GACOS Request Assistant

目标：

```text
提取 SLC 日期
按批次生成请求文件
生成 gacos_request_batches.csv
导入用户下载产品
检查日期完整性
```

验收标准：

```text
日期去重正确
缺失日期能识别
报告中有 GACOS 状态
```

### Task 013：报告系统

目标：

```text
生成 manifest.csv
生成 markdown 报告
生成 HTML 报告
生成 warnings.csv
```

验收标准：

```text
报告能解释项目是否适合继续 SARscape 处理
```

### Task 014：GUI Beta

目标：

```text
实现 Workspace / Project / Region 树
实现项目创建
实现 AOI 输入
实现 ASF 导入
实现检查结果显示
实现任务队列
实现日志窗口
实现错误弹窗
```

验收标准：

```text
GUI 可完成最小流程：创建 Workspace → 创建 Project → 添加 Region → 输入 AOI → 导入 ASF cart → 检查 → 生成报告
```

---

## 30. 质量红线

以下问题一律不能合并：

```text
明文保存密码或 token
日志输出完整 token
SARscape-ready 路径中出现连字符
SARscape DEM 文件未以 _dem.tif 结尾
中国行政区划边界缺少来源与审图号元数据
下载失败导致整个程序崩溃
没有测试的新核心功能
硬编码用户本地路径
把大体积 SLC 测试数据提交到仓库
无错误码的用户可见错误
GUI 直接实现核心逻辑
绕过外部服务限制
```

---

## 31. 参考信息与实现依据

本项目设计中涉及的主要外部事实应在实现时以官方文档为准。建议开发时优先查阅：

```text
ASF Search / asf_search 官方文档
OpenTopography Global Datasets API 文档
GACOS 官方网页
Python logging 官方文档
keyring 官方文档
uv 官方文档
Ruff 官方文档
pytest 官方文档
Cursor Rules 官方文档
地图审核管理规定、地图管理条例及相关自然资源主管部门说明
```

---

## 32. 结论

本工具的核心价值不是“下载更多数据”，而是让初学者以标准化、可追溯、符合 SARscape 识别规则和数据合规要求的方式准备 InSAR 前置数据。

长期维护时必须优先保证：

```text
稳定性
可追溯性
日志完整性
错误可解释性
SARscape 兼容性
凭据安全
边界数据合规
多区域任务可恢复
```
