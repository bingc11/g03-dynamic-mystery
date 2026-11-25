# G03 第二轮状态

## 云端基线

| 项目 | 核对结果 |
| --- | --- |
| 仓库 | `bingc11/g03-dynamic-mystery` |
| 克隆后的默认分支 | `main`，`4574b2d8186cd2f4e868c2902a9427ac5dae4d49` |
| 第一轮远端分支与基线 | `feature/scottishfold-npc-actions`，`548d31a038a6067da852a82a47cdfdaf43e2cead` |
| 第二轮工作分支 | `feature/scottishfold-delegation`，从第一轮远端 HEAD 创建 |
| 祖先核对 | `git merge-base --is-ancestor 548d31a038a6067da852a82a47cdfdaf43e2cead HEAD` 在第二轮分支返回 0 |

第一轮 PR #1 仍为 Draft。第二轮以第一轮分支为评审目标。基线历史中没有 `STATUS.md`、`NEXT_TASK.md` 和 `ACCEPTANCE.md`，本轮在仓库根目录建立三份记录，第一轮原始记录保存在 [docs/PHASE1.md](docs/PHASE1.md)。

## 源码调查与阶段记录

- 第一轮的 `Actor.tsx` 通过 `registryQuestion()` 和特定人物、证物判断把输入送到 `/npc/act`。其他互动走原 `/invoke/stream`。`offline_policy` 根据特定角色目标与秘录常量决策。`npc_api.py` 的会话字典和版本号随进程重启消失。
- 基线 `python -m unittest discover -s tests -v` 通过 7 项。旧离线回放可继续运行，当前原界面的对话委托由第二轮接口负责。
- 第二轮角色引擎从案件数据读取角色目标、初始知识、关系、行动授权和对象记录。SQLite 在受理和执行之间保留任务状态，浏览器通过原对话框结算并显示来源。

- 持久化阶段使用原 SQLite 文件（也支持 `NPC_DB_PATH`），提交会话的角色状态、稳定事件 ID 与幂等凭证。获准任务先落库再执行，单局并发结算由可过期租约保护。
- 委托阶段支持按原话发起、按上下文澄清、拒绝、提示前置材料、联系人物和查阅对象。案件数据控制来源、授权和可对玩家转述的线索。旧 HTTP `/npc/act` 由 `/npc/dialogue`、`/npc/state` 和 `/npc/resume` 取代。
- 模型阶段使用已有提供方接入和候选 ID 结构；每条决策保留 `llm`、`mock` 或 `rules`。程序生成回报并保留原始出处。模型实例最多调用 3 次，每次上限 3 秒，私聊只处理一次收件人反应。
- 交流阶段已配置宫廷案和雾港案。角色只能在收到的事件和已掌握的记录内决策。私聊的转述是角色主张，核查对象的读取得到案件记录。

## 原界面与第二宗案件

- `Actor.tsx` 和 `npcActions.tsx` 通过案件元数据和后端意图处理选择委托通道，普通聊天保留原 `/invoke/stream`。旧助手、笔记和证物面板可继续使用，已受理任务可在原聊天恢复。
- `web/src/data/harborBlackout.ts` 把雾港案放入原剧本库，案件结案题验证作者设定的凶手和动机。第一轮宫廷案继续使用其原流程。
- 原对话输入、证物出示、角色选择与结案路径沿用原 React 组件。生产构建 `npm run build` 通过。

## 回归与交付

- Chromium 回归发现简化数据库的剧本列表省略证物字段。刷新后数据库副本覆盖了雾港案内置证物，导致无法补齐前置条件。合并剧本时现在保留内置证物作为缺省值，并遵从数据库明确提供的列表。
- 云端运行了完整 FastAPI、生产构建、HTTP 重启/并发测试与两案 Chromium 操作。真实模型配置没有授权凭据，模型决策使用 Mock。实际命令、操作和可回查的证据在 [ACCEPTANCE.md](ACCEPTANCE.md)。
- 首次恢复时，`Nnnnobel` 已有用户级写权限，但 ChatGPT Codex Connector 当时未覆盖上游仓库，HTTPS 推送与创建 fork 都返回 403。

## 2026-11-25 恢复核查

- 从现有工作区恢复。验收代码提交为 `3d81b37e15a9267918739e671b9a4d5e4204722b`。执行 `git fetch --prune origin` 后，第一轮远端分支仍在 `548d31a038a6067da852a82a47cdfdaf43e2cead`，`main` 仍在 `4574b2d8186cd2f4e868c2902a9427ac5dae4d49`。
- 第一轮 Draft PR #1 的头部仍为 `548d31a038a6067da852a82a47cdfdaf43e2cead`，核查时没有新提交、审查意见或行内评论。[第一轮 Draft PR](https://github.com/bingc11/g03-dynamic-mystery/pull/1)
- 仓库所有者完成连接器授权后，已推送第二轮分支，并以第一轮分支为目标创建 Draft PR #2。创建时的头部 SHA 为 `0b72db9ba09e12e6dcbcf496be897537b9318f63`。[第二轮 Draft PR](https://github.com/bingc11/g03-dynamic-mystery/pull/2)

## 第二轮审查与 GitHub 启动核查

- 在 `4d4369c5055803c2a3c4288f002d323624e1f9eb` 核对了两条已复现的审查问题。直接询问目击者现在只读取其知道且获准披露的材料，并保留原始来源和主张标记。询问进展按事件先后读取结果，询问联络及其来源仍走各自的披露路径。[目击证词审查](https://github.com/bingc11/g03-dynamic-mystery/pull/2#discussion_r4690879786) · [回报顺序审查](https://github.com/bingc11/g03-dynamic-mystery/pull/2#discussion_r4690879794)
- Issue #3 的 `@codex` 请求收到创建仓库环境的提示，未取得实施任务链接。PR #2 上的代码审查已独立完成。此 Cloud 工作区处于运行状态，施工账号连接的 GitHub 身份为 `Nnnnobel`，未发现绑定本任务的 G03 事件监听或定时任务。[Issue #3 启动回复](https://github.com/bingc11/g03-dynamic-mystery/issues/3#issuecomment-7153993563) · [PR #2 代码审查状态](https://github.com/bingc11/g03-dynamic-mystery/pull/2#issuecomment-7154028368)
