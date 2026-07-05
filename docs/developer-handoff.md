# 新电脑开发与打包接手指南

这份指南用于把项目迁移到一台新 Windows 电脑继续开发、内部测试或正式发布。所有命令默认在仓库根目录执行。

## 1. 准备工具

建议环境：

- Windows 10/11
- Git
- GitHub CLI
- Python 3.11
- Node.js 20 或更高版本
- uv
- Inno Setup 6（仅构建安装包需要）

推荐安装方式：

```powershell
winget install --id Git.Git --source winget
winget install --id GitHub.cli --source winget
winget install --id OpenJS.NodeJS.LTS --source winget
winget install --id Python.Python.3.11 --source winget
winget install --id JRSoftware.InnoSetup --source winget
```

uv 可按官方方式安装，也可以使用已有 Python 环境安装。安装后确认：

```powershell
git --version
gh --version
node --version
npm --version
uv --version
```

## 2. 登录 GitHub

```powershell
gh auth login
gh auth status
```

需要具备仓库 push、Release 和 Actions 权限。不要把 GitHub token 写入文件或提交到仓库。

## 3. 克隆仓库

```powershell
git clone https://github.com/hhanmj/insar_studio.git
cd insar_studio
git status
```

如果使用私有工作目录，可以把仓库放在任意位置。不要在文档、Release 正文或提交信息里写自己的本机绝对路径。

## 4. 安装依赖

```powershell
uv sync --extra desktop --extra download --extra convert --dev
cd ui
npm ci
npm run build
cd ..
```

如果只开发轻量主程序，后续会逐步减少对 `convert` 额外依赖的本地要求；当前为了构建组件和完整验证，保留完整安装方式。

## 5. 本地运行

开发前端：

```powershell
cd ui
npm run dev
```

桌面端可通过环境变量加载 Vite 页面，也可以先构建前端再启动桌面入口。常规打包验证优先使用构建脚本。

## 6. 常用检查

每次准备提交前至少运行：

```powershell
uv run python scripts\check_ascii_quotes.py
uv run python -m compileall -q src packaging scripts
npm.cmd run build --prefix ui
uv run insar-prep --version
git diff --check
```

说明：

- `check_ascii_quotes.py` 用于阻止工作流、PowerShell 和安装脚本中混入中文弯引号。
- `compileall` 只检查 Python 语法和导入期字节码编译，不等同完整业务测试。
- 前端构建出现 chunk size warning 不代表失败，但后续应通过代码拆分优化体积。

## 7. 构建内部测试版

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows_desktop_exe.ps1 -SkipUi -SkipSelfTest -ExternalDemComponent
```

脚本输出单文件 exe 到 `dist/`。内部测试默认使用外置 DEM/GDAL 组件模式，便于验证组件安装、缺失和修复流程；`dist/` 是本地构建产物，不提交到 Git。

## 8. 构建安装包

先确保 Inno Setup 已安装，然后：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows_desktop_installer.ps1 -Version 2.1.4
```

安装包适合长期使用和后续在线覆盖更新。发行版本应使用完整桌面 exe 构建，不加 `-ExternalDemComponent`；正式分发前仍需考虑代码签名、Windows SmartScreen 信誉和更新器策略。

## 9. 发布版本

发布前：

1. 修改 `pyproject.toml` 和 `src/insar_prep/__init__.py` 中的版本号。
2. 同步 `ui/src/lib/bridge.ts` 的无桥接预览版本号。
3. 同步 `packaging/*.iss` 和 `packaging/component_manifest.example.json`。
4. 更新 `CHANGELOG.md`，并确认当前版本有中文 `新增` / `变更` / `优化` / `修复` 等条目。
5. 运行常用检查。
6. commit 并 push 到 `main`。

创建 Release：

```powershell
git tag -a v2.1.4 -m "Release v2.1.4"
git push origin v2.1.4
gh run list --workflow Release --limit 5
```

Release workflow 成功后，应包含：

- `InSAR-Studio-*.exe`
- `insar-studio-*-setup.exe`
- `insar-studio-*-portable.zip`
- `SHA256SUMS.txt`

GitHub Release 正文会自动从 `CHANGELOG.md` 抽取当前 tag 对应条目。不要在 Release 正文里写本机目录、内部测试路径、账号、Token 或私有数据。

## 10. 凭据与本地状态

软件用户凭据保存在系统凭据管理器，不写入仓库。新电脑第一次运行时需要重新配置：

- Earthdata/ASF Token 或账号密码。
- OpenTopography API Key。
- GACOS 邮箱。
- 网络代理和缓存目录。

本地下载历史、缓存、任务状态、用户边界和下载成果都不随仓库迁移。需要迁移用户数据时，应单独备份用户自己的输出目录，而不是提交到 Git。

## 11. 常见问题

### `gh` 安装后 PowerShell 找不到

关闭当前 PowerShell，重新打开后再执行：

```powershell
gh --version
```

如果仍失败，检查 PATH 或重启电脑。

### Release 工作流失败

优先检查：

- 工作流和 PowerShell 脚本是否混入中文弯引号。
- 版本号是否全部同步。
- GitHub token 权限是否包含 `repo` 和 `workflow`。
- EGM2008 下载源是否可用。
- Inno Setup 是否安装成功。

### 软件内无法提示更新

确认：

- GitHub Release 已创建且不是 draft。
- tag 版本号高于当前软件版本。
- 当前软件能访问 GitHub Release API。
- 旧版本本身是否已经包含更新检查逻辑。
