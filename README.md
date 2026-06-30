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

请在 GitHub Releases 中下载最新版本的 Windows 便携包或安装包。

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
powershell -ExecutionPolicy Bypass -File scripts\build_windows_desktop_installer.ps1 -Version 2.1
```

安装包构建流程已接入；正式代码签名证书、发布信誉和静默覆盖更新策略仍需在后续版本继续完善。

## v2.1 更新要点

- 修复软件关闭后后台进程偶发残留的问题。
- 强化下载任务持久化，暂停、失败、结束和已删除记录在重启后保持正确状态。
- 优化 Sentinel-1 / ASF 检索、下载队列、断点续传、失败重试和详细日志。
- 增加 SAR 下载工作台，支持搜索、勾选、全选当前列表、高亮影像和单景操作。
- 精密轨道默认承接 Sentinel-1 检索结果，也支持单独导入 SAR 文件或目录生成轨道候选。
- 移除精密轨道中的本地轨道库入口，简化为下载所选影像对应的 POEORB/EOF。
- 优化 AOI 与行政区边界，多要素边界可预览、筛选、选择和绑定。
- 调整 DEM 下载/转换入口，支持 DEM/GDAL 高级转换组件外置。
- 改进 iOS 风格界面、顶部资源区、下载中心角标、新手引导和地图交互。


## 体积说明

发行版默认采用“轻量主程序 + 按需组件”的策略：主程序保留界面、ASF 检索下载、轨道下载、AOI 与任务队列；rasterio/GDAL/numpy 等 DEM 高级转换运行库会作为可选组件从 Release 下载，不默认塞进主程序。在线地图瓦片、行政区缓存、ASF 元数据、SAR 影像、DEM 和 GACOS 数据不会进入软件本体，应作为用户本地缓存或下载成果保存。

## 后续计划

- 完善正式 Windows 安装包与软件内覆盖更新。
- 接入 Sentinel-2、Landsat、HLS 等免费遥感数据源。
- 优化多数据源任务队列、缓存机制和更新提醒。
- 继续完善 AOI、下载日志、DEM 转换和新手引导体验。

## 许可证

本项目使用 MIT License，详见 [LICENSE](LICENSE)。
