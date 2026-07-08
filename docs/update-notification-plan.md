# InSAR Studio 更新提醒与组件化升级计划

## 目标

当前 v2.1.x 发布前，最高优先级是保证用户打开软件时能收到新版提醒，能看到更新日志，并能在软件内在线下载更新包。这个能力必须轻量、稳定、失败静默，不影响 Sentinel-1、Orbit、DEM 等核心流程。

这个功能不是继续“全量软件缝补”的目标形态。它只是先建立用户触达通道：用户安装了当前版本以后，后续无论是全量安装包、轻量主程序、DEM/GDAL 组件、GEE 组件、Whitebox 组件，都能通过同一套更新入口被用户及时获知。

Rust 重构的核心目的不是“换语言”，而是把软件拆成更小、更稳定、更容易更新的结构：

- 主程序只保留 UI、任务调度、凭据管理、地图基础能力、更新器、组件管理器和轻量下载规则；
- GDAL/PROJ/rasterio、DEM 高级转换、GEE、Whitebox、光学影像处理、后续算法工具链都作为组件包；
- 用户只下载自己需要的组件，主程序体积不再被所有能力绑死；
- 更新既可以更新主程序，也可以只更新某个组件。

长期 v3/Rust 重构时，不推翻这套规则，而是复用同一套发布清单和版本判断协议，把主程序更新、可选组件更新、后续 GEE/Whitebox/光学影像模块更新统一起来。

## v2.1.x 立即落地：先保证用户不失联

1. 启动后后台检查 GitHub Releases 的 latest release。
2. 如果发现高于当前版本的新版本，弹出更新窗口。
3. 更新窗口展示：
   - 当前版本和最新版本；
   - Release 名称、发布时间；
   - Release body 作为更新日志；
   - 推荐下载资产名称和大小；
   - 在线下载按钮；
   - Release 页面入口。
4. 检查失败、离线、GitHub 限流时不打扰用户，不阻止软件打开。
5. 用户关闭弹窗只影响本次会话；用户点击“不再提示此版本”后，当前版本不再弹，下一个新版本仍会弹。
6. 设置页保留手动“检查更新”和“下载更新包”，作为启动弹窗之外的备用入口。

## 不和 Rust 重构冲突的边界

v2 只负责“发现更新、展示日志、下载发布资产”。它不做自我替换，不做后台静默安装，不把 PyInstaller 打包逻辑和未来 Tauri/Rust 安装器绑死。

从现在开始，新功能不能默认继续塞进主 exe。只有满足“启动必须、无它不可、依赖轻”的能力才进入主程序；重依赖和可选能力必须优先设计为组件。

v3/Rust 需要继承的是协议，而不是当前实现：

```json
{
  "version": "2.1.7",
  "release_name": "InSAR Studio 2.1.7",
  "published_at": "2026-07-08T00:00:00Z",
  "changelog": "Release body or mirrored changelog text",
  "assets": [
    {
      "name": "insar-prep-desktop.exe",
      "download_url": "https://...",
      "size": 84200000,
      "sha256": "..."
    }
  ],
  "components": []
}
```

当前 GitHub Release API 可直接提供大部分字段；后续如果用户无法访问 GitHub，可增加国内镜像 manifest，字段保持一致。

## 组件化目标结构

主程序内置：

- 桌面壳和前端 UI；
- 更新弹窗、组件清单读取、下载校验；
- 任务队列、任务快照、历史记录；
- Earthdata/OpenTopography 等凭据管理；
- Sentinel-1/Orbit 的轻量检索与下载调度规则；
- 基础 AOI/GeoJSON/地图显示能力。

组件外置：

- `dem-gdal`：GDAL/PROJ/rasterio/numpy/geoid 网格和 DEM 高级转换；
- `gee`：Earth Engine 授权、数据目录、GEE 导出任务；
- `whitebox`：WhiteboxTools/Whitebox Workflows 本地地理处理；
- `optical`：Sentinel-2、Landsat、HLS 等光学影像检索和下载；
- `insar-engines`：未来 ISCE/GMTSAR/MintPy/SARscape 适配器。

组件安装目录放在用户本地应用数据目录，不进入主 exe。每个组件必须有版本、大小、sha256、入口、依赖声明、适用平台和更新日志。

## 后续增强顺序

1. 发布包增加 sha256，并在软件下载后校验。
2. Release 附带 `app-update-manifest.json`，作为 GitHub API 的备用或镜像源。
3. 支持国内镜像 URL，优先读镜像，失败再回退 GitHub。
4. 把 `dem-gdal` 做成第一个真正外置组件，不再把 GDAL/PROJ/rasterio 继续塞进主 exe。
5. GEE、Whitebox、光学影像等新增能力默认只进入组件清单，不进入主程序包。
6. v3/Rust/Tauri 阶段由 Rust 负责安全下载、校验、替换和重启；前端继续使用同一套更新弹窗和更新日志展示。
