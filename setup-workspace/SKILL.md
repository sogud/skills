---
name: setup-workspace
description: 新机器或新克隆的 AgentSpace 初始化。用户要求配置工作区、恢复缺失仓库或建立全局配置链接时使用；先检查清单，Git、EV、QMD 各用原工具，不自动修改平台配置。
---

# Setup Workspace

## 流程

1. 确认 cwd 与根 `manifest.json`，读取根 AGENTS；不猜测机器路径。
2. 按当前任务从 manifest 的 repos 检查需要的仓库目录；只报告缺失的名称、remote 和目的地。用户确认后直接 `git clone <remote> <path>`，不批量克隆无关仓库。
3. EV 可用时运行 `ev workspace context`；从目标目录或指定名称验证规则和技能路径。EV 未安装时直接读 manifest/project.json 与 AGENTS，不把安装作为普通任务前提。
4. 只检查当前目标所需的 Node/pnpm、Python、Git、QMD 等工具；缺失报告，不自动安装或登录。
5. 知识库直接用现有 QMD 入口；Obsidian 打开 manifest 配置的知识库，而不是仓库根。
6. 对实际改动做最小验证：路由检查路径、代码运行所属项目测试、索引更新后检索验证。不要为初始化运行所有仓库测试。

## 全局配置仅在明确要求时处理

EV 不替换用户的 Skills、MCP、认证或会话配置。用户明确要求恢复 AgentSpace 现有全局链接时，
先读取 `system/infra/workspace.py` 的 link-globals 实现并展示源/目标；确认后可直接运行
`python3 system/infra/workspace.py link-globals`。这是旧维护工具的特定用途，不是日常启动步骤。
工具为 `~/.agents/skills` 等四个入口逐个建仓内技能软链；入口里用户自放的真实目录和外部软链只透传不动，同名真实文件或软链会跳过并告警，不覆盖。
首次摊平整目录软链或清理悬空链需要显式确认后才能加 `--force`，工具默认不自动加；不改登录凭据。

## 失败处理

缺少仓库不影响无关任务；克隆失败保留已有目录，核对状态再决定后续动作。
已有仓更新先检查工作树和分支，再按授权 `git pull --ff-only`，不自动 stash/reset/强推。
任何无法验证的入口或工具如实报告，不拿配置存在当成功。
