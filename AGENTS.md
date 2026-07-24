# AI Code Agent

以下规则适用于本项目，AI 在修改代码前必须严格遵守。

---

## 1. 核心原则

0. **先了解项目再动手**
   - 执行任务或修改代码之前，如果需要了解项目，必须先阅读 `.wiki/` 中的项目概述和文档结构
   - 掌握项目的整体架构和设计原则后再开始工作，避免基于猜测的修改

1. **保持现有功能完整性**
   - 除非用户明确要求，不得修改现有功能行为、配置、接口、环境变量结构、目录结构、脚手架流程
   - 保持项目原有的构建流程和运行方式

2. **最小化修改**
   - 只做必要的修改，避免影响不相关的功能模块
   - 新增逻辑必须最小化修改范围，避免连锁兼容问题

3. **代码风格统一**
   - 遵循项目现有的代码风格和命名规范
   - 文件名统一使用 kebab-case 或遵循项目现有约定
   - 保持文件和目录结构的一致性

---

## 2. 依赖管理

1. **禁止降级依赖版本**，只有用户明确允许或必须降级以修复冲突时才可降版本且经过用户允许
2. **不得移除现有依赖**，除非用户明确要求或明确冗余且经过用户允许
3. **新增依赖必须遵循最新兼容版本策略（semver ^）**，并考虑兼容性
4. **修改依赖配置前必须先确认项目类型与构建体系**

---

## 3. 输出要求

1. 提供清晰的代码实现，优先输出代码与必要的命令步骤
2. 必要时说明修改原因，避免冗余解释性文本
3. 不得擅自生成总结文档、README 或说明文档（除非用户明确要求）

---

## 4. 禁止事项

以下行为全部禁止：

- 自动执行 `git commit`、`git push` 等提交操作（代码修改完成后由用户审查并手动提交）
- 擅自重构项目一级目录结构（如 src、public、dist、apps 等）
- 改变 lint / build 行为导致结果不同
- 将项目改为其他框架或运行环境
- 删除现有功能
- 擅自改变基础配置文件（如 tsconfig / vite / webpack / Cargo.toml / pom.xml）
- 插入当前环境无法使用的 API（例如在浏览器项目引入 fs/path 等 node-only API）
- **Superpowers spec/plan 文件错放**：spec 与 plan 文件只能存放在 `docs/superpowers/specs/` 和 `docs/superpowers/plans/` 下；禁止从 `.gitignore` 中删除 `docs/superpowers` 条目；禁止将 spec/plan 文件放到任何其他目录

---

## 5. 注释规范

**示例（TypeScript）：**

```typescript
/**
 * @description 从 Apifox 平台获取 OpenAPI 数据
 * @param config API 配置对象
 * @returns Promise<ApiData> API 数据
 *
 * @example const data = await fetchApifoxData({ source: '...', token: '...' });
 *
 */
```

**强制要求：**

1. 每个文件必须有 `@description` 文件头注释（中文）
2. 每个函数必须有 `@description` 注释
3. 有参数的函数必须有 `@param` 注释
4. 有返回值的函数必须有 `@returns` 注释
5. 核心函数（命名策略、类型清理、生成器、解析器、转换器等）需要 `@example` 标签

**语言差异说明：**

- TypeScript / JavaScript：使用 JSDoc 风格（如上示例）
- Java：使用 Javadoc 风格（`/** ... */`），遵循 Java 既有规范
- Rust：使用 `///` 文档注释，遵循 rustdoc 规范（`# Arguments` / `# Returns` / `# Examples` 段）
- 各语言按各自规范实现上述 5 条要求的内容，不强制使用完全相同的标签名

---


---

## Python 项目规则

### 包管理与运行时

1. **包管理器遵循项目现状优先级**：`uv` > `poetry` > `pip + requirements.txt`，不得擅自混用或切换
2. **Python 版本必须与 `pyproject.toml` 的 `requires-python` 或 `.python-version` 一致**，不得擅自升级或降级
3. 虚拟环境（`.venv` / `venv`）目录不入库，依赖通过锁文件（`uv.lock` / `poetry.lock`）复现

### 项目结构约定

遵循 Python 标准项目结构，不得擅自调整一级目录：

- `src/<package>/` — 主代码（推荐 src-layout）或 `<package>/`（flat-layout，遵循项目现状）
- `tests/` — 单元测试（镜像包结构）
- `docs/` — 文档（Sphinx / MkDocs 等）
- `scripts/` — 运维 / 辅助脚本
- `pyproject.toml` — 构建 / 依赖 / 工具配置（PEP 621）
- `requirements.txt` / `requirements-dev.txt` — 依赖锁定（若项目使用）
- `.python-version` — Python 版本声明（pyenv）

### 构建与测试命令

- `uv sync` / `poetry install` / `pip install -e .` — 安装依赖（按项目包管理器）
- `uv run python -m <package>` / `python -m <package>` — 运行
- `pytest` — 运行测试
- `pytest tests/<file>` — 运行指定测试
- `ruff check` — 代码检查（如项目使用 ruff）
- `ruff format` — 格式化
- `mypy` / `pyright` — 类型检查（如项目配置）

### 依赖与配置规则

1. **禁止降级依赖版本**，新增依赖优先选择维护活跃、兼容当前 Python 版本的包
2. `pyproject.toml` 修改采取合并策略，不得重写整个文件
3. 依赖分组（dev / docs / test 等）遵循项目现有分组方式，不得擅自重组
4. 类型注解（type hints）遵循项目现状：全量注解项目必须保持注解完整，未注解项目不强制
5. 新增公开函数 / 类必须有 docstring（遵循 Google / NumPy / Sphinx 风格，按项目现状）
6. 配置文件（`.env`、`config.yaml` 等）修改采取合并策略，不破坏现有键值

### 禁止事项

- 不得擅自切换包管理器（`uv` ↔ `poetry` ↔ `pip`）
- 不得擅自升级或降级 `requires-python` 版本
- 不得把虚拟环境目录（`.venv`）或 `__pycache__` 提交入库
- 不得擅自重写 `pyproject.toml` 整个文件
- 不得引入与项目 lint / formatter 冲突的工具（如已有 ruff 再引入 black / flake8）
- 不得在库代码中硬编码绝对路径或环境特定配置
