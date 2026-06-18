# Cursor + Opus 协作开发指南

适用项目：InSAR Data Preparation Assistant  
目标：使用 Cursor 中的 Opus 模型长期、稳定、可控地开发项目。  
原则：不要让模型一次性开发整个软件；必须按任务拆分、测试驱动、验收后再进入下一步。

---

## 1. 基本策略

### 1.1 不要这样提问

不要给 Cursor/Opus 这种任务：

```text
请帮我开发完整的 InSAR 数据准备软件。
```

这种提示会导致：

1. 代码跨度太大；
2. 文件被大范围改动；
3. 质量难以检查；
4. 模型容易跳过测试和日志；
5. 后期难以维护。

### 1.2 正确方式

每次只给一个小任务：

```text
请实现 Task 003：SARscape 命名工具。

要求：
1. 只修改 src/insar_prep/core/naming.py 和 tests/unit/test_naming.py；
2. 实现 sarscape_safe_name()；
3. 禁止连字符、空格和特殊符号；
4. 最终 SARscape DEM 必须以 _dem.tif 结尾；
5. 写 pytest 测试；
6. 运行 uv run ruff check . 和 uv run pytest。
```

---

## 2. Cursor Project Rules 设置

建议在项目中加入 Cursor 规则文件。规则文件应长期存在，不要每次临时口头提醒模型。

推荐路径：

```text
.cursor/rules/insar_prep_project_rules.mdc
```

规则内容见本压缩包内的 `insar_prep_project_rules.mdc`。

### 2.1 规则文件应包含什么

必须包含：

```text
项目定位
SARscape 命名规则
凭据安全规则
日志规则
错误码规则
测试规则
禁止行为
任务拆分原则
```

### 2.2 每次开始任务前

在 Cursor 中先让模型阅读：

```text
请先阅读 DEVELOPMENT_MANUAL.md、CURSOR_OPUS_GUIDE.md 和 .cursor/rules/insar_prep_project_rules.mdc。之后只按我指定的 Task 开发，不要自行扩展功能。
```

---

## 3. 推荐开发流程

每个任务使用固定流程：

```text
Step 1：让模型复述任务目标
Step 2：让模型列出计划修改的文件
Step 3：让模型实现最小代码
Step 4：让模型写测试
Step 5：让模型运行检查命令
Step 6：让模型解释实现结果
Step 7：你人工检查
Step 8：提交 Git commit
```

---

## 4. 每个任务的标准提示词模板

```text
你是本项目的 Python 开发助手。请严格遵守 DEVELOPMENT_MANUAL.md、CURSOR_OPUS_GUIDE.md 和 .cursor/rules/insar_prep_project_rules.mdc。

当前任务：
[填写 Task 编号和名称]

任务目标：
[填写要实现的功能]

允许修改的文件：
[列出文件路径]

禁止修改的文件：
[列出不允许修改的文件，或写“除上述文件外均禁止修改”]

具体要求：
1. 不要修改无关文件；
2. 不要引入未声明依赖；
3. 不要硬编码我的本地路径；
4. 不要保存或输出账号、密码、token；
5. 用户可见错误必须使用错误码；
6. 必须写日志；
7. 必须写 pytest 测试；
8. 网络请求必须可 mock；
9. SARscape-ready 路径和文件名必须使用下划线，不能有连字符；
10. SARscape-ready DEM 必须以 _dem.tif 结尾；
11. 中国行政区划边界必须保留来源和审图号元数据；
12. 代码必须通过 ruff 和 pytest。

请先输出：
1. 你理解的任务；
2. 你计划修改的文件；
3. 你不会修改的范围；
4. 可能风险。

等我确认后再写代码。
```

---

## 5. 代码实现阶段提示词

确认计划后，再发：

```text
按刚才确认的方案实现代码。

要求：
1. 一次只完成当前 Task；
2. 保持函数短小；
3. 所有核心逻辑写在 src/insar_prep/，不要写在 GUI；
4. GUI 只能调用核心逻辑；
5. 所有错误使用 core.exceptions；
6. 所有用户可读错误包含错误码；
7. 所有日志使用项目 logger；
8. 测试文件放在 tests/unit 或 tests/integration；
9. 不要真实访问网络，网络请求必须 mock；
10. 完成后给出运行命令和结果摘要。
```

---

## 6. 代码审查提示词

每个任务完成后，让模型自查：

```text
请审查你刚才的修改，重点检查：

1. 是否违反 DEVELOPMENT_MANUAL.md；
2. 是否有明文凭据；
3. 是否有硬编码本地路径；
4. SARscape-ready 文件名是否可能出现连字符；
5. DEM 输出是否以 _dem.tif 结尾；
6. 中国行政区划边界是否保留审图号元数据；
7. 是否有用户可见错误但没有错误码；
8. 是否有 print() 代替 logger；
9. 是否有未测试的核心逻辑；
10. 是否有不必要的大范围重构。

请列出风险和需要我人工确认的地方。
```

---

## 7. Debug 提示词

如果测试失败，不要让模型乱改。使用：

```text
测试失败。请只分析失败原因，不要立即改代码。

失败命令：
[粘贴命令]

错误输出：
[粘贴错误]

要求：
1. 判断是代码错误、测试错误还是环境错误；
2. 指出最小修改范围；
3. 不要重构无关模块；
4. 不要修改已经通过的测试；
5. 给出修复计划，等我确认后再改。
```

确认后再发：

```text
按最小修改方案修复。只修改你刚才列出的文件。修复后重新运行相关测试。
```

---

## 8. 不同开发阶段的模型使用方式

### 8.1 架构设计阶段

适合使用 Opus。

任务：

```text
拆分模块
设计数据模型
识别技术风险
写测试计划
审查命名规范
审查安全规范
```

提示词重点：

```text
请先评估设计风险，不要急着写代码。
```

### 8.2 代码实现阶段

也可使用 Opus，但要严格限制文件范围。

提示词重点：

```text
只实现当前 Task，不要主动扩展功能。
```

### 8.3 调试阶段

要求模型先分析，再修改。

提示词重点：

```text
不要直接改代码，先定位根因。
```

### 8.4 重构阶段

重构必须单独开任务，不能混在功能开发里。

提示词重点：

```text
当前任务只允许重构，不允许新增功能。
```

---

## 9. 强制开发顺序

建议按以下顺序推进，不要跳到 GUI：

```text
Task 001：项目骨架
Task 002：核心数据模型
Task 003：SARscape 命名工具
Task 004：日志系统
Task 005：AOI 输入模块
Task 006：ASF cart 解析器
Task 007：影像一致性检查
Task 008：下载管理器和任务队列
Task 009：轨道匹配
Task 010：OpenTopography DEM 下载
Task 011：DEM 垂直基准转换
Task 012：GACOS Request Assistant
Task 013：报告系统
Task 014：GUI Beta
```

原因：

1. GUI 依赖核心逻辑；
2. 日志和错误码越早建立越好；
3. SARscape 命名规则必须先固定；
4. 多区域模型必须先进入底层数据结构；
5. 下载器、DEM、GACOS 都依赖 AOI 和 Region 模型。

---

## 10. 每次提交前必须运行

```bash
uv run ruff check .
uv run ruff format .
uv run pytest
uv run insar-prep --help
```

如果某个命令失败，不要提交。

---

## 11. Git commit 模板

```text
feat: add sarscape-safe naming utilities
fix: prevent duplicate DEM ellipsoid conversion
docs: update AOI compliance guide
test: add ASF cart parser fixtures
refactor: split downloader state machine
chore: update ruff config
```

---

## 12. 人工检查清单

每次模型完成任务后，你人工检查：

```text
是否只改了允许修改的文件
是否新增了测试
测试是否能跑
是否新增了无关依赖
是否有硬编码路径
是否有 token / 密码泄露
SARscape-ready 路径是否全是下划线
DEM 是否以 _dem.tif 结尾
中国行政区边界是否记录审图号
错误是否有错误码
日志是否可读
```

---

## 13. Opus 常见问题与约束方式

### 13.1 容易主动扩展功能

约束方式：

```text
不要实现任何当前 Task 之外的功能。即使你认为它有帮助，也只在最后列为建议。
```

### 13.2 容易大范围重构

约束方式：

```text
除我指定的文件外，不要修改其他文件。需要修改时先说明理由并等待确认。
```

### 13.3 容易省略测试

约束方式：

```text
没有测试则任务视为未完成。
```

### 13.4 容易把 GUI 和核心逻辑混在一起

约束方式：

```text
核心逻辑必须在 src/insar_prep/core、providers 或 processing 中实现。GUI 只能调用核心接口。
```

### 13.5 容易忽略 SARscape 命名

约束方式：

```text
任何写入 06_sarscape_ready 的路径都必须调用 sarscape_safe_name()。
```

---

## 14. 首次开发建议

第一次打开 Cursor 后，按这个顺序做：

### 14.1 创建规则文件

把 `insar_prep_project_rules.mdc` 放到：

```text
.cursor/rules/insar_prep_project_rules.mdc
```

### 14.2 把手册放入根目录

```text
DEVELOPMENT_MANUAL.md
CURSOR_OPUS_GUIDE.md
```

### 14.3 第一个提示词

```text
请阅读 DEVELOPMENT_MANUAL.md、CURSOR_OPUS_GUIDE.md 和 .cursor/rules/insar_prep_project_rules.mdc。

现在不要写代码。请只做三件事：
1. 总结这个项目的目标和硬约束；
2. 检查 Task 001 是否足够清晰；
3. 给出 Task 001 的文件创建计划。

不要实现代码，等我确认。
```

### 14.4 第二个提示词

```text
确认执行 Task 001：建立项目骨架。

允许创建：
pyproject.toml
.python-version
README.md
CHANGELOG.md
LICENSE
src/insar_prep/__init__.py
src/insar_prep/cli/main.py
tests/test_import.py
.github/workflows/ci.yml

要求：
1. 使用 Python 3.11；
2. 使用 uv；
3. 使用 ruff；
4. 使用 pytest；
5. CLI 命令为 insar-prep；
6. 不实现任何业务功能；
7. 只保证项目能安装、导入、运行帮助命令和测试。

完成后运行：
uv sync
uv run insar-prep --help
uv run pytest
uv run ruff check .
```

---

## 15. 任务完成判定

一个 Task 完成必须同时满足：

```text
功能实现
测试通过
日志合规
错误码合规
SARscape 命名合规
无凭据泄露
无硬编码本地路径
文档更新
Git commit 完成
```

不满足任何一条，都不进入下一个 Task。

---

## 16. 最重要的协作原则

每次只推进一个小任务。  
每次都要求模型先计划、后实现。  
每次都运行测试。  
每次都检查 SARscape 命名和凭据安全。  
不要让 GUI 先行。  
不要让模型自由发挥整体架构。
