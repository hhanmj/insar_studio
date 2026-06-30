# 贡献指南

感谢你愿意帮助 InSAR Studio 变得更好。本项目仍在快速迭代，欢迎提交问题、建议、文档改进和代码修复。

## 反馈问题

提交 issue 前请尽量提供：

- 软件版本。
- Windows 版本。
- 你正在使用的功能模块。
- 能复现问题的步骤。
- 错误截图或日志片段。
- 是否开启代理、使用何种数据源账号。

请不要上传账号、Token、Cookie、下载链接中的签名参数、私有边界数据或未公开项目数据。

## 开发环境

```powershell
uv sync --extra desktop --extra download --extra convert --dev
cd ui
npm ci
npm run build
cd ..
```

常用检查：

```powershell
npm.cmd run build --prefix ui
uv run python -m compileall -q src packaging
git diff --check
```

## 分支与提交

- 功能开发建议从 `main` 新建短分支。
- 提交信息尽量说明用户可感知的变化，例如 `Fix persisted download history state`。
- 一个 PR 尽量只解决一类问题，避免把 UI、下载逻辑和打包脚本混在一起。

## 代码边界

公开仓库不接收：

- 个人账号、Token、密钥、证书和日志。
- 本地下载成果、缓存、临时测试目录。
- 第三方参考项目完整拷贝。
- 大体积离线边界、影像、DEM 或轨道文件。

## UI 方向

桌面端 UI 以“新手清晰、任务可追踪、地图与列表联动”为核心。新增功能时请优先考虑：

- 用户是否能理解当前状态。
- 是否能暂停、恢复、重试和查看日志。
- 离开页面后状态是否保留。
- 是否避免把下载目录、缓存、账号等设置提前变成阻碍。
