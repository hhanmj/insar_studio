# InSAR Studio V2.0

InSAR Studio 是一个面向 InSAR 与遥感数据准备流程的桌面工具，当前重点服务于
Sentinel-1 / SARscape 使用场景：区域 AOI 选择、ASF 元数据检索、SAR 影像下载、
精密轨道匹配与下载、DEM 下载与椭球高转换、GACOS 辅助数据准备，以及下载任务管理。

本项目不替代 SARscape、ISCE、MintPy、SNAP 或 ASF Vertex。
它的定位是“处理前的数据准备助手”，帮助新手把下载、检查、目录组织和辅助数据准备流程做得更清楚。

## V2.0 主要特性

- 现代化桌面工作台：左侧参数区，右侧地图区，顶部数据源功能区。
- GeoDownloader 风格交互：数据源入口支持横向滚动，后续可继续扩展 Sentinel-2、Landsat 等模块。
- Sentinel-1 下载：支持 ASF 检索、SLC/GRD 元数据展示、影像范围地图高亮、任务队列与历史记录。
- 下载任务管理：支持并发、暂停、继续、失败重试、日志查看、断点续传提示。
- AOI 区域管理：支持行政区边界、手动框选、多边形绘制、文件导入与地图显示。
- 多图层地图：默认使用 Google 卫星底图，并保留多种可切换图源。
- 精密轨道：支持按 SAR 影像目录或 ASF 官方脚本解析并下载 Sentinel-1 轨道文件。
- DEM：支持 OpenTopography DEM 下载、原始 DEM 保存、椭球高转换和 SARscape 适配命名。
- GACOS：支持根据 SAR 影像日期准备请求与下载辅助流程。
- 设置中心：支持 Earthdata/ASF 凭据、OpenTopography Key、GACOS 邮箱、网络代理、缓存目录等配置。
- 无边框桌面窗口：应用图标、窗口控制按钮和主功能区合并为统一顶部体验。

## 下载与使用

当前内部测试版建议直接使用便携包：

1. 下载 `insar-studio-V2.0-portable.zip` 或最新 release 中的便携包。
2. 解压后运行 `insar-prep-desktop.exe`。
3. 首次使用请先在“设置”中填写 Earthdata/ASF 凭据和 OpenTopography Key。

说明：

- 软件不会内置任何个人账号、Token、密钥或下载缓存。
- 用户数据、任务记录、缓存和下载成果保存在用户电脑本地。
- ASF、OpenTopography、GACOS 等服务均需要用户自行遵守对应网站的账号、访问和数据使用规则。

## 本地构建

开发环境：

- Windows 10/11
- Python 3.11
- Node.js / npm
- uv

安装依赖：

```powershell
uv sync --extra desktop --extra download --extra convert
cd ui
npm install
npm run build
cd ..
```

构建桌面 exe：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows_desktop_exe.ps1
```

构建正式安装包需要额外安装 Inno Setup 6：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows_desktop_installer.ps1 -Version 2.0.0
```

## 体积说明

当前 Windows 单文件版约 65 MB。体积主要来自：

- Python 运行环境与 PyInstaller 引导器；
- WebView/pywebview 与 pythonnet 相关运行库；
- rasterio/GDAL、shapely、numpy 等 DEM 与几何处理依赖；
- 离线行政边界与小型地理辅助数据。

地图瓦片、ASF 元数据、SAR 影像、DEM、GACOS 等在线数据不会塞进软件本体，
应作为用户本地缓存或下载成果保存。后续如果拆分“基础版 / DEM 转换增强版”，可以进一步降低基础包体积。

## 下一版本计划

V2.x 后续重点：

- 制作正式 Windows 安装包版本，包含开始菜单、桌面快捷方式、卸载入口和更新提示。
- 接入 Sentinel-2 下载与筛选流程。
- 接入 Landsat 下载与筛选流程。
- 将下载中心进一步统一为多数据源任务队列。
- 优化缓存机制，支持地图瓦片、元数据和下载任务记录的可配置缓存目录。
- 完善多源数据检索结果在地图中的统一展示、选择、删除和导出。

## 反馈

当前项目仍处于内部测试和快速迭代阶段。欢迎通过 Issue 或测试群反馈：

- 下载失败日志；
- ASF 检索条件与返回结果；
- AOI 行政区边界问题；
- DEM/GACOS 转换流程问题；
- UI 与新手引导建议。

## 许可证

本项目使用 MIT License。详见 [LICENSE](LICENSE)。
