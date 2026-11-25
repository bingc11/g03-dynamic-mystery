# G03 第二轮实施记录

| 阶段 | 当前状态 |
| --- | --- |
| 确认云端基线，独立分支 | 完成，从第一轮远端 HEAD 创建 |
| 统一角色状态、事件、任务与持久化 | 完成，完整 FastAPI 重启和并发结算验证通过 |
| 原对话委托与受限模型提议 | 完成，Mock 与规则回退测试通过 |
| 按案件数据执行自主交流 | 完成，两套案件、三种角色行动和两种收件人结果已验收 |
| 生产构建、浏览器、证据 | 完成，命令与复现见 [ACCEPTANCE.md](ACCEPTANCE.md) |

真实 LLM 验收等待本项目授权模型配置。Draft PR 等待 ChatGPT Codex Connector 覆盖上游或已连接的可写 fork。届时将 `feature/scottishfold-delegation` 作为源分支，`feature/scottishfold-npc-actions` 作为目标分支。先按头部分支查找已有 PR；有对应 Draft PR 就更新，否则创建 Draft PR，并保持待审查。

## 恢复和审查

每次启动、恢复或收到 PR 事件时，刷新远端分支、PR 和审查意见，以 [STATUS.md](STATUS.md) 中最近核查的 SHA 为对照。处理本轮范围内的变化，验证后记录新的 SHA、对应 PR 和实际结果。写权限受阻时，保留现有提交并继续可在 Cloud 验证的工作。

下一轮以用户在当前任务中的明确指令或用户指定 Issue 中的指令为准。普通提交、PR 更新和其他人的评论用于同步与本轮审查。

自动唤醒只使用 GitHub 事件。目前这条 Codex Cloud 任务没有可配置的 GitHub 事件入口，连接器的安装范围也未授权本仓库。事件订阅仍待验证。
