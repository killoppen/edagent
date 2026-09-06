# LearnFlow 项目交接文档

> 更新时间：2026-09-06（Asia/Shanghai）
> 仓库：`D:\jbgs\all`
> 远程：`https://github.com/killoppen/edagent.git`
> 当前分支：`codex/migrate-role-atlas`
> 当前 HEAD：`734752d1c81df320f3b19eba65d61f87c72d38d4`
> 当前目标：桌面版 LearnFlow；浏览器开发模式只作为共用前端和调试入口

本文描述生成时实际存在的代码、提交、测试和远程状态。接手前先执行 `git status -sb`。当前工作树中有一项用户已有改动：`desktop/src-tauri/Cargo.toml` 被 Git 标记为修改，不能重置、覆盖、格式化或顺手提交。

## 1. 产品定位

LearnFlow 是一个以 Tutor 对话为中心的计算机学习工作空间，正式产品目标是桌面端：

- 后端：FastAPI、SQLAlchemy async、SQLite；
- 前端：React、Vite、TypeScript；
- 桌面壳：Tauri 2；
- 桌面运行时：Tauri 启动本地 FastAPI sidecar，绑定随机 loopback 端口；
- 浏览器模式：复用同一套前端、API 和学习对象，用于开发、调试和无桌面环境验收。

项目围绕“对话—工具—学习状态—可验证产物”闭环，不把 Role Atlas 或桌宠当成第二套学习状态系统。

## 2. 架构红线

### 2.1 三类主 Agent

| 主 Agent | 责任 |
| --- | --- |
| `tutor_agent` | 用户意图、对话、Action Board、工作台协调和 handoff |
| `learning_design_agent` | 学习路线、内容、问题、评估规格和视觉教学产物 |
| `practice_agent` | 提交、测试、判题、反馈、诊断追问和纠错呈现 |

Role Atlas、Graph Hub、桌宠和学习星图都是工作台、工具或产品能力，不是第四类主 Agent。

### 2.2 五核与证据写回

五核是学习者状态维度：`structure`、`knowledge`、`human`、`value`、`practice`。唯一合法的长期状态写入链为：

```text
用户 / UI / Tool / Agent 行为
  -> EvidenceEvent
  -> five_kernel_reducer
  -> KernelMutation
  -> KernelState
  -> MemoryFact -> MemoryModule -> MemoryClaim
```

Role Atlas 的检索、岗位图谱、冷启动结果、雷达图、学习星图的展示以及视觉模型生成内容，不能直接写 `KernelState`、`EvidenceEvent` 或长期画像。需要改变学习状态时必须走已登记的事件和 reducer。

机器可读权威是 `backend/app/services/architecture_registry.py`（当前版本 `2026-09-06.2`），语义规范见 `docs/ARCHITECTURE_AUTHORITY.md` 与 `docs/AGENT_ARCHITECTURE_GUIDE.md`。

## 3. 功能版图与模块关系

### 3.1 主链路

```text
桌面窗口 / 对话栏
  -> Tutor Runtime
  -> 已登记插件工具或工作台
  -> 结构化 ToolRun / Renderer
  -> 用户确认的 Action 或学习对象变更
  -> EvidenceEvent（如确实改变学习状态）
  -> 五核与 Memory Graph
```

普通检索、图谱推荐、Role Atlas 读取和视觉观察默认是只读或临时上下文；它们不会因为“生成了文本”就自动成为掌握证据。

### 3.2 功能关系表

| 功能板块 | 主要入口 | 依赖 | 输出及边界 |
| --- | --- | --- | --- |
| Tutor 对话 | 主窗口对话栏 | Tutor Runtime、插件目录、Action Board | 回复、工具结果、待确认提案；状态写入受证据链约束 |
| 学习路径 | `frontend/src/LearningPathPage.tsx`、`/learning-path` | 官方节点、个人节点、计划 API、学习星图布局 | 路径状态、节点简介/语义、计划提案；确认后才写正式路径 |
| Graph Hub | 对话工具 `search_graph_hub`、图谱推荐 Renderer | Role Package 目录、主体可见性和匹配器 | 按图谱类型、名称和命中节点筛选推荐；只读，不自动选择图谱 |
| Role Atlas | `apps/role-atlas/`，对话结果中的外部入口 | 静态 Role Package、BuildRun、冷启动/迭代 Skill | 岗位包研究、版本化快照、工作过程和岗位包引用；不维护 LearnFlow 五核 |
| 岗位能力雷达 | Role Atlas 图谱视图 | 节点、边、关联关系 | 选中节点放大、关联高亮、无关内容淡化、节点/过程拖入对话 |
| 视频学习 | `search_learning_videos` → `inspect_learning_video` | 联网候选、字幕/时间点/目标覆盖核验 | 在对话或学习任务中展示候选；搜索/播放不是掌握证据，也不是独立顶层状态 |
| 桌宠 | Tauri `pet` 窗口、托盘和快捷键 | 受限 `lfpet_` capability、正式 Tutor Session | 任务/复习、文本/图片/文档/字幕/选区临时上下文；一次确认只消费一个 Tutor 回合 |
| 项目/任务/复习 | 主窗口工作台 | 正式 Project、LearningTask、SkillRun、Review | 进度、提交、复习和纠错闭环；由正式 Tutor/Practice 链路驱动 |

## 4. Role Atlas 同仓现状

### 4.1 用途和边界

Role Atlas 是岗位研究与岗位包生产工具，不是用户每次学习都必须打开的页面。它把一个静态、版本化的 `Role Package` 作为岗位事实源；岗位图谱、岗位卡片、JD、学习路径投影、对话上下文和报告都从岗位包投影而来。

当前内置岗位包为“大模型应用工程师” `1.2.0`，快照时点 `2026-08-19`。同仓源码在 `apps/role-atlas/`，说明见 `apps/role-atlas/README.md` 和 `docs/implementation/2026-09-04-role-atlas-monorepo.md`。

### 4.2 入口和调用关系

- LearnFlow 侧边栏已有 `Role Atlas` 入口，使用 `frontend/src/role-atlas-entry.ts` 解析配置地址；默认本地地址为 `http://localhost:3000/`。
- 浏览器端使用普通 HTTP(S) 外链；桌面端通过受限 Tauri `open_external_url` 命令交给系统默认浏览器，协议仅允许 HTTP/HTTPS。
- 当岗位包目录没有匹配项时，Graph Hub 结果提供进入 Role Atlas 研究的入口；LearnFlow 不会偷偷使用无关岗位包代替用户选择。
- 用户明确选择岗位包后，必须保留 `packageId`、`packageVersion`、`snapshotId` 和 `rootHash`，后续岗位读取使用精确 selector。

### 4.3 已覆盖的 Role Atlas 能力

- 图谱、岗位卡片、任务/能力/知识技能读取和关系查询；
- 事理森林：工作场景、阶段、条件分支、返工环、交付物和任务桥接；
- 岗位项目新建、冷启动、继续研究、风险修复和版本化快照；
- 项目/会话/消息/BuildRun/BuildEvent 的持久化和恢复；
- Static Role Package 编译、校验、发布、导出、版本 Tag 和恢复；
- 工作区接入、证据归一化和岗位快照实例化；
- 桌面本地项目永久删除并级联清理；浏览器端仍保留软删除/恢复语义；
- 冷启动后台执行、构建事件回放以及断线后前端恢复。

### 4.4 Graph Hub 分类和检索推荐

插件工具 `search_graph_hub` 返回专用 `graph_hub_recommendation` Renderer。当前前端支持：

- 图谱类型筛选；
- 名称和节点文本筛选；
- 展开命中节点；
- 显示当前主体可见范围；
- 从推荐结果跳转 Graph Hub 或 Role Atlas。

推荐结果是候选，不会自动写入学习路径、`EvidenceEvent` 或五核。

## 5. 学习路径与学习星图

### 5.1 数据结构

学习节点已支持：

- `sourceKind`：官方、对话、工具、岗位图谱包、手动等来源；
- `sourceLabel`：面向用户的来源说明；
- `semantics`：官方语义、个人语义和图谱特殊语义；
- 官方节点必须带稳定简介和官方语义；旧节点读取时会自动补默认简介/个人语义；
- 正式 overlay 与 reducer 同时兼容 camelCase 和 snake_case，便于旧数据迁移。

相关实现主要在 `frontend/src/learning-path-graph.ts`、`frontend/src/official-learning-path-content.ts`、`backend/app/services/architecture_registry.py` 和学习路径 API。

### 5.2 当前交互

- 鼠标滚轮上下滚动星图，按住 `Ctrl` 再滚轮控制缩放，缩放中心尽量保持在光标位置；
- 星图任意位置均可按住拖动，包括节点、星团和空白区域；
- 通过 pointer capture 和 4px 移动阈值区分点击与拖动，拖动后不会误触发节点点击；
- 星图区域使用 `preventDefault` 与 `overscroll-behavior: contain`，拖动时不会带动外层学习路径页面上下滚动；
- 节点/星团原有点击、状态变更和选中逻辑仍保留；
- 雷达/星图的缩放和拖动不直接改变学习状态，状态变更仍由明确操作写入。

## 6. 桌面端与桌宠

### 6.1 桌面壳

- Tauri 主窗口 label 为 `main`，桌宠窗口 label 为 `pet`；
- sidecar 使用随机 loopback 端口和独立应用数据目录；
- 支持托盘、单实例唤醒、桌宠显示/隐藏、窗口位置持久化和全局快捷键；
- 主窗口和桌宠复用正式 Tutor Session、Task、Review、File 等对象，不共享第二套数据库权威。

### 6.2 capability 和临时上下文

桌宠使用短效 `lfpet_` capability，不把主窗口 bearer 暴露给 pet。capability 绑定账户、learner、父 AuthSession 和 `auth_epoch`，服务端只保留 token hash，并按 URL→scope 白名单限制访问。

当前支持的临时上下文：`text`、`ocr_text`、`image_observation`、`document_excerpt`、`video_transcript`。默认 TTL 15 分钟、正文上限 12,000 字，需用户确认后最多携带 3 条引用进入一个受限 Tutor 回合；消费或过期后清除正文，仅保留有限 provenance receipt。

选区快捷键默认 `Ctrl+Alt+P`：优先在原前台窗口通过 Unicode 复制读取选区，失败后才回退截图/视觉模型；读取结束会恢复用户原剪贴板。跨 Edge、PDF 阅读器等真实 GUI 场景仍需要手工验收。

## 7. 已完成修复矩阵

| 原问题 | 当前状态 |
| --- | --- |
| 图谱仓库检索异常 | 已补 Graph Hub 检索、分类、推荐 Renderer 和可见范围过滤 |
| 图谱分类/推荐缺失 | 已完成，工具为 `search_graph_hub` |
| 进入 Role Atlas 跳转失败 | 已修复桌面外链命令和 HTTP(S) 校验 |
| Role Atlas 无删除岗位项目选项 | 桌面本地请求改为永久删除并级联清理；浏览器仍可软删除/恢复 |
| Role Atlas 冷启动不可用 | 已加入后台 `waitUntil`、BuildEvent 回放和断线恢复；真实供应商/桌面 GUI 仍需验收 |
| 动画/图片生成卡死且上下文丢失 | 已补图解意图识别、恢复已验证上文主题；视觉规划失败保留正式 Tutor 讲解并展示失败 ToolRun |
| 学习路径节点缺少来源/简介/语义 | 已加入官方/个人来源、简介和多来源语义，保持旧数据兼容 |
| 岗位雷达杂乱、拖入对话困难 | 已支持选中节点放大、关联节点/边高亮、无关内容淡化；对话栏整区可接收拖入 |
| 学习星图只能空白处拖动、页面跟着滚动 | 已支持任意位置拖动、点击兼容和星图区域滚动锁定 |

## 8. 本地运行

### 8.1 浏览器开发模式

```bash
bash start.sh
bash start.sh status
bash start.sh stop
```

默认前端为 `http://localhost:4174`，后端为 `http://127.0.0.1:8010`。脚本会检查 Python 3.10–3.13、后端依赖、`frontend/node_modules` 和 `backend/.env`。

### 8.2 桌面开发和构建

```bash
cd frontend
npm install
npm run build

cd ../desktop
npm install
npm run build:sidecar
npm run dev
# 发布构建
npm run build
```

需要 Rust stable、Tauri 2 平台依赖、Node.js、后端运行依赖和 `desktop/requirements-build.txt` 中的 PyInstaller 依赖。若 rustup 没有默认 toolchain，可使用：

```bash
rustup run stable cargo check --no-default-features
```

Role Atlas 独立开发/验证：

```bash
cd apps/role-atlas
npm install
npm run typecheck
npm test
npm run build
npm run dev
```

Role Atlas 要求 Node.js `>=22.13.0`；真实模型和联网冷启动需要相应的 `.env.local` 配置，密钥不得提交。

## 9. 验证证据

已实际执行或在当前提交前后确认的结果：

| 检查 | 结果 |
| --- | --- |
| 后端定向契约套件：`tests/test_workspace.py`、`tests/test_tutor.py`、`tests/test_local_agent_broker.py`、`tests/test_architecture_registry.py` | `111 passed` |
| 前端全量测试与构建 | 已通过；历史路径测试曾有一个 Role Atlas 导出换行失败，需在继续改动时重新核对 |
| Role Atlas 测试、类型检查、直接 `npx vinext build` | 已通过（迁移后 140+ 测试，具体数量随提交变化） |
| `git diff --check` | 已通过 |
| Rust：`rustup run stable cargo check --no-default-features` | 已通过 |
| PR #8 合并前基线 `1d32573` 的 `verify` | GitHub 已成功 |
| PR #8 当前头 `734752d` 的检查 | 推送后尚未返回新的 check runs，不能提前视为通过 |

未完成或需要真实环境补验：

- Tauri 安装包完整安装、升级、托盘、单实例和桌面外链验收；
- Edge、PDF 阅读器等跨应用选区读取与剪贴板恢复；
- Role Atlas 真实供应商联网冷启动、长任务恢复和桌面 GUI；
- 字幕 `source_ref` 时间窗的完整前后端链路；
- OS 级贴边 dock、自动隐藏和动画；
- Windows/macOS 安装包签名与发布流水线；
- 完整后端套件中曾出现的 Windows 权限、编码和 symlink 环境问题。

## 10. Git、PR 与接手顺序

当前分支在合并提交 `1d32573` 中把当时的 `origin/main`（`0d2e706`）作为第二父提交纳入；文档提交后远程 `main` 已前进到 `2c2ee51`，因此后续合并前必须重新同步 base。PR #8 为：

`https://github.com/killoppen/edagent/pull/8`

截至文档提交后：PR open，GitHub API 报告 `mergeable=false`、`mergeable_state=dirty`，新提交尚未返回完整检查结果。不要自行 merge；也不要把本地 `main` 分支当作最新基线，应先 fetch 并以最新 `origin/main` 为准。

推荐接手顺序：

1. 先读根目录 `AGENTS.md`、`docs/ARCHITECTURE_AUTHORITY.md`、`docs/AGENT_ARCHITECTURE_GUIDE.md`、`docs/GITHUB_COLLABORATION.md` 和本文。
2. 执行 `git status -sb`，保护 `desktop/src-tauri/Cargo.toml` 用户改动。
3. 用 `git log --oneline --decorate -15` 确认当前提交，再检查 PR #8 的实时 CI。
4. 先运行前端构建和后端定向契约测试；需要桌面验收时重新构建 sidecar 和 Tauri Release，避免运行旧的 `target/release/learnflow-desktop.exe`。
5. 手工验证主窗口登录、学习路径星图拖动/缩放、Graph Hub 推荐、Role Atlas 外链、岗位删除/冷启动恢复、桌宠上下文和视频候选核验。
6. 后续修改架构热点时同步更新注册表、实现、测试和文档，并在提交说明中写 `Contract impact`。

## 11. 禁止操作与安全边界

- 不提交 `.env`、API Key、Token、Cookie、真实数据库、`node_modules`、虚拟环境、模型权重、缓存或本地日志；
- 不使用 `git reset --hard`、`git checkout --`、rebase 或 force push 清理工作树；
- 不覆盖、删除或提交任务范围外的用户改动，尤其是 `desktop/src-tauri/Cargo.toml`；
- 不让 Role Atlas、桌宠、插件或 LLM 直接写五核、掌握状态或长期记忆；
- 不把视频搜索/播放、视觉生成、一次答对或带提示成功直接当作掌握证据；
- 不把参考仓库当作持续上游，不自动 merge、cherry-pick 或同步其数据库/状态；
- 删除项目、发布岗位包、确认学习计划和其他高影响操作必须保留明确的用户确认、scope ownership 和幂等边界。
