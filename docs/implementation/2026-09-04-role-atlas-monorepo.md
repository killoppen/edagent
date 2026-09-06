# Role Atlas 同仓接入

本次将参考仓库中的 Role Atlas 同仓迁移到当前 LearnFlow 仓库，并通过独立分支提交 PR；当前分支已有的桌宠与学习路径改动保持不覆盖。

## 来源与目录

- 目标：`apps/role-atlas/`，作为普通源码目录提交，不使用 submodule、不嵌套 .git。
- 源提交：`runzhong123-max/LearnFlow@7eccad15`。导入其 `apps/role-atlas/` 全部 333 个版本化源码、文档、测试和发布样例文件；未导入密钥、数据库、依赖或运行状态。
- 原工作副本保留。后续以同仓目录为维护入口，不自动双向同步。
- 保留 LearnFlow 历史；不把另一仓库分支强推到 main，也不导入 Role Atlas 历史对象。

## Contract impact

仅合并源码管理，不合并数据库、进程、主 Agent 控制权或学习状态权威。LearnFlow 保持唯一学习前端、三类主 Agent 和 EvidenceEvent → reducer → 五核写入链；Role Atlas 独立生产岗位包，LearnFlow 经既有主体/版本校验消费。

随同发布的已有学习路径改动只抽取 `learnflow-learning-path/v1` 共享只读类型及官方图导出，保留旧模块类型重导出；这不等于学习路径 v2 完成。

## 路径调整

- cohost 的 LearnFlow Docker context 改为同仓根目录，仍可由 LEARNFLOW_REPO_PATH 覆盖。
- 官方学习路径同步默认读取同仓，可由 LEARNFLOW_ROOT 覆盖。
- 插件开发态模拟包目录改为同仓，不再搜索维护者机器上的固定目录；生产仍依赖显式配置及 scoped catalog。
- 根 gitignore 只为 Role Atlas public/data 开例外；真实运行数据及秘密仍排除。
- 两产品保留各自 lockfile。Role Atlas 使用 Node.js 22.13+，不改变现有桌面构建环境。

## 验证与发布边界

`make verify-role-atlas` 运行子应用测试、类型检查及构建。联合部署见子应用 deploy/cohost/README.md。

新增 Role Atlas CI 仅执行安装、目录验证、测试、类型检查和构建，权限为 contents:read，不部署服务、不读取生产密钥。

实际验收：

- 逐文件比对源提交：333 个子应用源文件全部导入；根目录工作流、布局校验、README、Makefile、`.gitignore` 与同仓部署路径作适配，并补充 LearnFlow v1/v2 源图导出入口。未导入依赖、密钥、数据库或运行状态。
- 子应用从 lockfile 安装成功，目录检查、测试、类型检查与生产构建按本次验收执行。
- LearnFlow 前端 361 项测试及生产构建通过；后端 407 项通过、1 项跳过（既有私有凭据 CRUD 测试已弃用），保留已有弃用警告。
- Docker Compose 使用测试占位参数解析成功：LearnFlow 前后端 context 指向根目录，Role Atlas context 指向子目录；未启动容器。
- 线上域名、真实模型及 GitHub CI 的运行结果不属于上述本地验收结论。

本次不执行生产迁移、所有者回填、模型调用或容器重启。LearnFlow 现有 main push 工作流会构建内部桌面安装包，不部署网页服务。

回滚源码导入用普通 revert，不改写历史、不删除原工作副本或生产卷。含软删除的线上版本不得回退到不识别 deleted_at 的旧服务，详见第一批升级验收文档。
