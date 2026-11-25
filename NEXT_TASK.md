# G03 后续记录

## Issue #5 审查入口

新分支 `feature/g03-agent-investigation` 基于 PR #2 的 `0119ed0c49a7b9d936374126401dc5f1a93c5964`。先复查严格真实双案轨迹及历史权限反例，再看生产截图中的草稿确认和角色筛选。继续积累课堂真实表达后可扩充固定语料，尤其关注容易进入澄清的省略指代。[本轮验收](ACCEPTANCE.md#issue-5-云端验收) · [Issue #5](https://github.com/bingc11/g03-dynamic-mystery/issues/5)

## Issue #4 交付后

本次实施与验证继续使用 PR #2 的 `feature/scottishfold-delegation`。`deepseek-flash` 已在本项目的云端运行验证。审查可从雾港委托与双席公开路径开始，评测包含真实请求、回退和三角色对照。[验收](ACCEPTANCE.md) · [课堂脚本](docs/CLASSROOM.md) · [评测](docs/EVALUATION.md) · [主任务](https://github.com/bingc11/g03-dynamic-mystery/issues/4) · [Draft PR #2](https://github.com/bingc11/g03-dynamic-mystery/pull/2)

- 课堂试玩时记录玩家在哪些自然表达上需要澄清，以及哪条独立线索能支持最后推理。继续比较新增情境在 Mock、Rules 与真实模型下的轨迹。
- 请课程教师查看课程映射与展示脚本，确认具体评分权重及呈现形式要求。[课程目标映射](docs/CLASSROOM.md#课程目标映射与待确认项)
- 恢复开发时先核对 GitHub 的 Draft PR、分支头部和审查记录。下一阶段以用户明确指定的任务为准。

## 第二轮历史记录

| 阶段 | 当前状态 |
| --- | --- |
| 确认云端基线，独立分支 | 完成，从第一轮远端 HEAD 创建 |
| 统一角色状态、事件、任务与持久化 | 完成，完整 FastAPI 重启和并发结算验证通过 |
| 原对话委托与受限模型提议 | 完成，Mock 与规则回退测试通过 |
| 按案件数据执行自主交流 | 完成，两套案件、三种角色行动和两种收件人结果已验收 |
| 生产构建、浏览器、证据 | 完成，命令与复现见 [ACCEPTANCE.md](ACCEPTANCE.md) |

真实 LLM 验收等待本项目授权模型配置。第二轮已推送 `feature/scottishfold-delegation`，目标为 `feature/scottishfold-npc-actions`，Draft PR 保持待审查。[第二轮 Draft PR](https://github.com/bingc11/g03-dynamic-mystery/pull/2)

### 恢复和审查

每次启动、恢复或收到 PR 事件时，刷新远端分支、PR 和审查意见，以 [STATUS.md](STATUS.md) 中最近核查的 SHA 为对照。处理本轮范围内的变化，验证后记录新的 SHA、对应 PR 和实际结果。写权限受阻时，保留现有提交并继续可在 Cloud 验证的工作。

下一轮以用户在当前任务中的明确指令或用户指定 Issue 中的指令为准。普通提交、PR 更新和其他人的评论用于同步与本轮审查。

此前要求的自动唤醒范围是 GitHub 的 PR 提交更新事件。当时未能把事件订阅绑定到本 Cloud 任务，也未启用定时轮询。

GitHub `@codex` 实现入口的独立复验仍需配置本仓库可用的 Codex Cloud Legacy 环境，应以实际任务链接和运行记录核对启动结果。继续这条任务的现有工作区时，使用原 Codex 对话。[环境设置](https://chatgpt.com/codex/cloud/settings/environments)
