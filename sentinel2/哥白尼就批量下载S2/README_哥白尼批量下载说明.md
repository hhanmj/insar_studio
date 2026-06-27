# 哥白尼数据批量下载说明

这份脚本把参考代码里的两种写法合并成了一个通用版，统一走 Copernicus Data Space Ecosystem（CDSE）官方接口：

- 检索：`https://catalogue.dataspace.copernicus.eu/odata/v1/Products`
- 鉴权：`https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token`
- 下载：`https://download.dataspace.copernicus.eu/odata/v1/Products(<PRODUCT_ID>)/$value`

和参考脚本相比，主要差别是：

- 不再把数据类型写死成 `Sentinel-2 MSI` 或 `Sentinel-3 OLCI`
- 不依赖 `wget` 和 `pandas`
- 支持任意 `collection`
- 支持 `GeoJSON` / `bbox` / `productType` / 名称关键字 / 原始 OData 条件
- 支持批量下载、已存在跳过、结果清单导出

## 1. 文件说明

- 主脚本：`copernicus_batch_download.py`
- 参考脚本：`参考2/MSI_batch_download.py`、`参考2/OLCI_batch_download.py`
- 参考区域：`参考2/Yangtze.geojson`、`参考2/EastChinaSea_large.geojson`

## 2. 环境准备

建议先安装 Python 3.10+ 和 `requests`：

```powershell
python -m pip install requests
```

也可以把账号密码放到环境变量里，避免直接写在命令历史中：

```powershell
$env:CDSE_USERNAME="你的CDSE账号"
$env:CDSE_PASSWORD="你的CDSE密码"
```

CDSE 账号注册地址：

- [https://dataspace.copernicus.eu/](https://dataspace.copernicus.eu/)

## 3. 通用命令格式

```powershell
python .\copernicus_batch_download.py `
  --start-date 2024-01-01 `
  --end-date 2024-01-31 `
  --output-dir .\downloads `
  --collection SENTINEL-2 `
  --product-type S2MSI2A `
  --geojson .\参考2\Yangtze.geojson
```

如果没有设置环境变量，也可以直接传账号密码：

```powershell
python .\copernicus_batch_download.py `
  --username "你的账号" `
  --password "你的密码" `
  --start-date 2024-01-01 `
  --end-date 2024-01-31 `
  --output-dir .\downloads `
  --collection SENTINEL-2
```

## 4. 常用参数

- `--start-date` / `--end-date`
  采用 `YYYY-MM-DD` 格式，脚本按“起始日包含、结束日包含”处理。

- `--output-dir`
  下载目录。

- `--collection`
  数据集合名，可重复写多次。
  例：`SENTINEL-1`、`SENTINEL-2`、`SENTINEL-3`、`SENTINEL-5P`、`SENTINEL-6`、`CLMS`、`CCM`、`LANDSAT-8`、`LANDSAT-9`、`COP-DEM`、`SMOS`、`ENVISAT`、`TERRA`、`AQUA`、`TERRAAQUA`。

- `--product-type`
  走官方 `productType` 属性筛选，比参考代码里单纯 `contains(Name, ...)` 更稳。

- `--name-contains`
  名称中包含某字符串时才保留，适合继续细筛。

- `--geojson`
  指定多边形范围，支持 `Polygon` 或 `MultiPolygon`，脚本取第一个外环。

- `--bbox min_lon min_lat max_lon max_lat`
  用矩形范围代替 `GeoJSON`。

- `--cloud-cover-max`
  按 `cloudCover <= 指定值` 过滤。只适用于有 `cloudCover` 属性的数据集合。

- `--odata-filter`
  直接追加原始 OData 过滤条件。这个参数是兜底手段，适合下载“任意哥白尼数据”时处理不同集合的专有字段。

- `--manifest`
  把检索结果导出为 `.csv` 或 `.json`。

- `--list-only`
  只检索，不下载。

- `--use-zip-endpoint`
  走 `/$zip` 下载，主要用于官方文档里提到的部分 Sentinel-1 压缩原始产品。

- `--overwrite`
  覆盖已下载文件。默认行为是“存在则跳过”。

## 5. 典型用法

### 5.1 Sentinel-2 L2A

```powershell
python .\copernicus_batch_download.py `
  --start-date 2024-04-01 `
  --end-date 2024-04-10 `
  --output-dir .\downloads\S2_L2A `
  --collection SENTINEL-2 `
  --product-type S2MSI2A `
  --cloud-cover-max 20 `
  --geojson .\参考2\Yangtze.geojson `
  --manifest .\downloads\S2_L2A_manifest.csv
```

### 5.2 Sentinel-3 OLCI EFR

```powershell
python .\copernicus_batch_download.py `
  --start-date 2024-04-01 `
  --end-date 2024-04-10 `
  --output-dir .\downloads\S3_OLCI_EFR `
  --collection SENTINEL-3 `
  --product-type OL_1_EFR___ `
  --geojson .\参考2\EastChinaSea_large.geojson
```

### 5.3 Sentinel-1 GRD

```powershell
python .\copernicus_batch_download.py `
  --start-date 2024-04-01 `
  --end-date 2024-04-10 `
  --output-dir .\downloads\S1_GRD `
  --collection SENTINEL-1 `
  --product-type GRD `
  --bbox 120 30 123 32
```

### 5.4 同时查多个集合

```powershell
python .\copernicus_batch_download.py `
  --start-date 2024-04-01 `
  --end-date 2024-04-10 `
  --output-dir .\downloads\multi `
  --collection SENTINEL-2 `
  --collection SENTINEL-3 `
  --geojson .\参考2\Yangtze.geojson `
  --list-only
```

### 5.5 只看检索结果，不下载

```powershell
python .\copernicus_batch_download.py `
  --start-date 2024-04-01 `
  --end-date 2024-04-10 `
  --output-dir .\downloads\preview `
  --collection CLMS `
  --name-contains NDVI `
  --list-only `
  --manifest .\downloads\clms_ndvi.json
```

### 5.6 使用原始 OData 条件

当某一类数据的筛选字段不适合脚本里现成参数时，直接追加官方 OData 条件：

```powershell
python .\copernicus_batch_download.py `
  --start-date 2024-04-01 `
  --end-date 2024-04-10 `
  --output-dir .\downloads\custom `
  --collection SENTINEL-3 `
  --odata-filter "Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'processingLevel' and att/OData.CSC.StringAttribute/Value eq 'Level-2')" `
  --list-only
```

## 6. 如何找 `productType` 和其他属性名

不同集合允许的属性不同。官方文档给了属性清单入口：

- OData 文档：[https://documentation.dataspace.copernicus.eu/APIs/OData.html](https://documentation.dataspace.copernicus.eu/APIs/OData.html)
- 所有集合属性入口：[https://catalogue.dataspace.copernicus.eu/odata/v1/Attributes](https://catalogue.dataspace.copernicus.eu/odata/v1/Attributes)

常见做法：

1. 先确定 `collection`
2. 再去查该集合支持哪些属性
3. 优先用 `--product-type`
4. 不够时再用 `--odata-filter`

## 7. 注意事项

- 官方文档明确建议不要把账号密码硬编码在脚本里，所以优先用环境变量。
- 不指定 `--collection` 也能查整库，但速度会明显变慢，通常不建议。
- 单次检索分页上限是 `1000`，脚本已经自动翻页。
- 默认下载端点是 `/$value`；部分 Sentinel-1 原始压缩产品才需要 `/$zip`。
- 默认行为是“已存在则跳过”，适合断点后重新执行。
- 当前脚本没有实现复杂的多线程并发下载，优先保证稳定和通用性。

## 8. 参考来源

- CDSE OData 文档：
  [https://documentation.dataspace.copernicus.eu/APIs/OData.html](https://documentation.dataspace.copernicus.eu/APIs/OData.html)
- CDSE Token 文档：
  [https://documentation.dataspace.copernicus.eu/APIs/Token.html](https://documentation.dataspace.copernicus.eu/APIs/Token.html)
- 你提供的参考代码：
  `参考1.txt`
  `参考2/MSI_batch_download.py`
  `参考2/OLCI_batch_download.py`

## 9. 可继续参考的 GitHub 仓库

下面这些仓库值得参考，但用途不完全一样：

- `CDSETool/CDSETool`
  链接：[https://github.com/CDSETool/CDSETool](https://github.com/CDSETool/CDSETool)
  这是面向 CDSE 的现成 Python 工具库，适合参考它的查询字段组织、凭证管理和高层 API 设计。

- `armkhudinyan/copernicus_api`
  链接：[https://github.com/armkhudinyan/copernicus_api](https://github.com/armkhudinyan/copernicus_api)
  这是一个较轻量的 OData Python 封装，适合参考它对 Sentinel 各任务的搜索/下载封装方式。

- `eu-cdse/copernicus-browser`
  链接：[https://github.com/eu-cdse/copernicus-browser](https://github.com/eu-cdse/copernicus-browser)
  这是 CDSE 官方浏览器前端开源仓库，更适合拿来核对当前使用的搜索/下载端点，而不是直接拿来当批量下载脚本。

不建议直接照搬的仓库：

- `sentinelsat/sentinelsat`
  链接：[https://github.com/sentinelsat/sentinelsat](https://github.com/sentinelsat/sentinelsat)
  这个项目历史上很常用，但主要面向旧的 SciHub/Open Access Hub 体系，而且仓库已归档；如果你的目标是当前 CDSE，应该只把它当作思路参考，不要当作现行接口示例。
