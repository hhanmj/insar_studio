# 代码规范

这份规范用于保持 InSAR Studio 后续开发可维护。它不是为了追求形式，而是减少状态混乱、发布事故和仓库污染。

## 总体原则

- 小步提交：一次提交只解决一类问题。
- 用户状态优先：任何下载、账号、组件、更新状态都要能被用户看懂。
- 先复用现有结构：除非确实降低复杂度，不新增平行框架。
- 不提交本地数据：缓存、下载成果、私有边界、密钥、测试目录只留在本机。
- 不把未完成能力写成已完成：尤其是静默更新、组件安装、DEM 高程基准转换。

## Python 后端

- 业务入口集中在 `src/insar_prep/desktop/api.py` 暴露给前端。
- 下载任务状态由专门 job 类维护，前端只消费状态，不直接推断核心流程。
- 用户可恢复状态需要持久化；临时进度可以保留在内存。
- 返回给前端的错误必须是用户可理解的中文信息，并带稳定错误码。
- 涉及账号、Token、代理、下载 URL 时必须脱敏，不写入日志和报告。
- 网络请求要考虑代理、超时、重试和用户可理解的失败原因。

## 前端 UI

- 主入口在 `ui/src/pages/Workbench.tsx`，公共 UI 放在 `ui/src/components/`。
- 状态不要用一个布尔值表达多个动作。示例：DEM 下载应区分 `download-only` 和 `download-convert`。
- 离开页面再回来，用户刚才检索、选择、下载、暂停的信息不应无故丢失。
- 按钮禁用时要用 `title` 或附近提示解释为什么不能点。
- 地图和列表联动时，点击列表默认高亮，不应突然跳转视图，除非用户明确要求定位。
- 不使用可见文本解释 UI 本身的设计细节，提示只服务于任务和状态。
- 新手引导只首次自动显示，后续通过入口手动重播。

## 下载与任务

- 下载任务必须显示进度、目录、并发、速度或足够明确的日志。
- 暂停、继续、结束、失败、删除是不同状态，不要混用。
- 暂停任务应留在任务队列；结束、失败、超时进入历史记录。
- 历史记录可恢复，但删除历史记录后不应重启软件又出现。
- 每个任务应绑定开始下载时的输出目录，方便断点续传和重试。

## DEM 与组件

- DEM 下载和 DEM 转换是不同操作，可以组合，但不能强迫用户同时执行。
- 椭球高转换必须明确源高程基准和目标基准。
- 缺少 EGM2008、EGM96 或 PROJ/GDAL 运行数据时，应提示安装或修复组件，不能静默近似。
- SARscape `_dem` 文件输出要同时关注主文件、`.hdr`、`.sml` 等配套文件。
- 组件包属于可选大体积资产，不应塞进主程序。

## 发布脚本

- `.github/workflows/`、`scripts/*.ps1`、`packaging/*.iss` 中禁止中文弯引号。
- Release 正文和发行包说明不得包含本机路径、内部测试路径、账号、Token、缓存目录。
- GitHub Release 正文必须来自 `CHANGELOG.md` 的当前版本条目，按中文 `新增` / `变更` / `优化` / `修复` / `已知问题` 写用户可感知变化。
- 版本号必须同步：
  - `pyproject.toml`
  - `src/insar_prep/__init__.py`
  - `ui/src/lib/bridge.ts`
  - `packaging/*.iss`
  - `packaging/component_manifest.example.json`
  - `CHANGELOG.md`
- tag 触发 Release 前必须确认 `main` 已包含对应提交。

## 文档

- `README.md` 写项目定位、核心能力和快速入口。
- `CHANGELOG.md` 写用户可感知变化。
- `docs/development-log.md` 写阶段决策和开发背景。
- `docs/developer-handoff.md` 写换电脑、打包、发布流程。
- `docs/release.md` 写发布和更新机制。
- 文档可以写通用示例路径，但不要写个人电脑路径。

## 提交前检查

```powershell
uv run python scripts\check_ascii_quotes.py
uv run python -m compileall -q src packaging scripts
npm.cmd run build --prefix ui
uv run insar-prep --version
git diff --check
git status --short
```

如果改动涉及 Release 或安装包，再检查：

```powershell
gh auth status
gh run list --workflow Release --limit 5
```

## 禁止提交

- `dist/`
- `release/`
- `build/`
- `.venv/`
- `.tmp*`
- `__pycache__/`
- `.pytest_cache/`
- 私有边界、下载影像、DEM、轨道文件。
- 个人微信二维码、群聊二维码、账号、Token、Cookie、证书。
