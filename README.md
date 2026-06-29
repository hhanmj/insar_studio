# InSAR Studio

InSAR Studio 是一个面向 InSAR 与遥感数据准备流程的桌面助手，当前重点服务于 Sentinel-1 / SARscape 使用场景：AOI 区域选择、ASF 元数据检索、SAR 影像下载、精密轨道匹配与下载、DEM 下载与椭球高转换，以及下载任务管理。

本项目不替代 SARscape、ISCE、MintPy、SNAP 或 ASF Vertex。它的定位是“处理前的数据准备助手”，帮助新手把下载、检查、目录组织和辅助数据准备流程做得更清楚。

## 主要功能

- Sentinel-1 ASF 检索与 SLC/GRD 数据准备。
- SAR 影像下载任务队列，支持并发、暂停、继续、失败重试和日志查看。
- AOI 区域管理，支持地图绘制、行政区边界、文件导入和绑定。
- 精密轨道辅助下载，支持从 SAR 影像目录或 ASF 官方文件中解析日期。
- DEM 下载、本地 DEM 转换和 SARscape 适配命名。
- 网络代理、缓存目录、Earthdata/ASF 与 OpenTopography 凭据配置。
- 桌面端 Web UI，方便后续扩展 Sentinel-2、Landsat、HLS 等多源遥感数据下载。

## 下载与使用

请在 GitHub Releases 中下载最新版本的 Windows 便携包或 exe。

首次使用建议先进入“设置”：

1. 配置 Earthdata / ASF 账号或 Token。
2. 配置 OpenTopography API Key。
3. 根据网络环境设置代理。
4. 检查默认缓存目录和下载目录。

软件不会内置任何个人账号、Token、下载历史、缓存或本机测试目录。ASF、OpenTopography、GACOS 等服务均需要用户自行遵守对应网站的账号、访问和数据使用规则。

## 本地开发

开发环境：

- Windows 10/11
- Python 3.11
- Node.js 20+
- uv

安装依赖：

```powershell
uv sync --extra desktop --extra download --extra convert --dev
cd ui
npm ci
npm run build
cd ..
```

构建桌面 exe：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows_desktop_exe.ps1
```

构建安装包需要额外安装 Inno Setup 6：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows_desktop_installer.ps1 -Version 2.0.2
```

## 仓库边界

公开仓库只保留软件源码、构建脚本、打包配置和必要的公开说明。以下内容不应提交：

- 本地测试数据、下载成果、缓存和临时目录。
- 个人账号、Token、密钥、证书和日志。
- 第三方参考项目、临时研究资料、离线边界大文件。
- 仅供本机调试的编辑器配置和代理工具状态。

## 体积说明

当前 Windows 单文件版本体积主要来自 Python 运行环境、PyInstaller 引导器、pywebview/WebView2 桥接依赖，以及 rasterio/GDAL、numpy、shapely 等 DEM 与几何处理依赖。在线地图瓦片、ASF 元数据、SAR 影像、DEM 和 GACOS 数据不会塞进软件本体，应作为用户本地缓存或下载成果保存。

## 后续计划

- 制作正式 Windows 安装包版本。
- 接入 Sentinel-2、Landsat、HLS 等免费遥感数据源。
- 优化多数据源任务队列、缓存机制和更新提醒。
- 继续完善 AOI、下载日志、DEM 转换和新手引导体验。

## 许可证

本项目使用 MIT License，详见 [LICENSE](LICENSE)。
