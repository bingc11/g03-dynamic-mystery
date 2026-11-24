# 阶段 0–1 交付记录

本分支基于 ScottishFold007/ai-murder-mystery 的 3afe5bccb989ec1b8964c0ff851e99c5484c80fe。原作允许保留版权的非商业教学改作；完整许可在根目录。本次公开导出仅包含实现所需的源码、运行资源与署名。开发基线在独立环境测试。

## 一宗案件的最短对照

进入内置《深宫血色：玉玺谜云》。先问御史大夫“有人查过秘录登记吗？”，他尚未收到询问。在太平公主的原对话框用证物夹出示“遗失的宫闱秘录”，再问御史同一句话。他此时能确认有人问过；追问“谁来问过秘录登记？”可取得他本人的具名陈述。直接给张昌宗看同一材料，御史的回答不会发生上述变化。公主看到的是玩家出示的材料；御史只听到她查登记的请求。二人交换的消息不能直接作为证明取走秘录的物证。

本轮的角色选择使用离线策略。每次出示最多触发一次候选决策。前端收到的是可交给玩家的回应。固定的合成复演会在命令行打印事件、来源和收件人。案情真相与原有指认均不在新增动作的写入范围。

## 实际源码地图

|玩家操作|原作实际实现|本次改动|
|---|---|---|
|选案和切换人物|ScriptLibrary、scriptContext 合并本地示例与数据库剧本；PlayScript 选中剧本，构建角色后挂载 Home|PlayScript 在原界面外提供当前案件的行动会话；换人物共享，新开案件独立|
|询问和助手|Actor.tsx 的 sendChatStream 经 api/invoke.ts 到 FastAPI /invoke/stream，llm_service 区分模型后端|对该示例的两类“登记”追问走规则；普通聊天与原助手仍使用原通道|
|出示和组合|EvidenceSelectorPanel 选中材料；Actor.handleEvidenceSend 原先只将内容送入聊天。evidenceManager 与 EvidenceLibraryPanel 管理浏览器端证物和组合；服务端另有 evidence_api|限定本案已开放的样例材料，出示时进入可信规则；原有其他材料走原流程。修复空数据库证物表的登记|
|笔记、结案|EnhancedNotesPanel、noteManager，Home 的 MultipleChoiceGame 和 EndModal|保留原数据与交互；NPC 的口头主张不能触发正确指认|
|角色行动|旧源码的消息与故事提示随对话传递|npc_actions 定义角色可见观察、合法选项、受限结算及来源事件；npc_api 检查会话、版本、字段和材料。私聊只给参与者，未设全知查询入口|

## 基线与证据

- 在未增加行动的原 FastAPI 副本，以临时数据库及本机 Ollama 兼容假服务测试。/health 成功；证人、助手均收到一个固定文本片段与流结束事件。证明传输链可用，未调用任何实际模型。
- 同一环境的 /evidence/create 与证物列表初次均报 HTTP 500。原 evidence_models 单独建立 SQLAlchemy Base；启动时创建的是 models.Base 的表。共享同一元数据后，相同请求成功创建并读回同一条 Receipt。
- 原前端导入了未随固定提交提供的五张 PNG。Header 复用仓库自带图标，两个机构链接显示原有名称，说明弹窗保留内容并标出缺失示意图。保留原游戏布局。
- `python -m unittest discover -s tests -v` 本机 7/7。覆盖更换收件人、未披露、未获授权的执行目标、虚构来源、策略故障、重复出示、过期版本、私聊隔离与固定重演。
- `python tools/check_http.py --port 10000` 在实际 FastAPI 上验证两局隔离、披露前后差异、可追问来源、非法身份凭据与过期操作。端口可替换。
- `python -X utf8 tools/replay.py` 用同一策略运行三组固定输入。成功路径中，事件 1 是玩家出示，2 是裁定通过，3 是两人私下交流，4 是玩家后来询问时听到的陈述。第 4 项向第 3 项追溯。独立结案、真人体验及模型语言品质须另行验收。

## 原界面的实测记录

同一套 Node 22 依赖在上游固定版本运行原构建，首先报错缺少 `../assets/logo.png`。因此原版调查界面无法直接开始试玩。修复分支保留原界面，修正缺少的静态导入、弹窗样式类型和证物模块的导入顺序，并锁定依赖。缺少原头像的角色显示姓名首字。

在本机 Chrome 用 Playwright 操作真实 React 页面和 FastAPI，限制浏览器只访问回环地址。以下是已执行的浏览器检查。普通角色与助手聊天用显式标识的模拟服务，新增角色行动用离线策略。

| 操作 | 实际观察 |
|---|---|
| 先与御史、张昌宗普通交谈，再问御史是否有人查登记 | 原助手与证人能显示模拟文本。御史对登记给出否定回答 |
| 在公主聊天框点击发送证物，选择秘录，再回御史处追问 | 同一问题得到肯定回应。追问后才给出公主姓名，玩家未直接收到私聊 |
| 写下推理笔记，指认公主，再返回改指武惠妃 | 笔记可保存并读回。错认被拒。选对嫌疑人后出现原作动机题，提交后能进入真凶对话 |
| 刷新重开，通过证物库先给张昌宗出示，再给公主出示 | 新局起初没有此前的私聊。前一次出示后御史仍回答没有，后一次出示后回答有人来问 |

上游结案有一项明确限制。离线聊天返回文本时，动机题会退回预设选项；现有动机提交函数接受任一所选答案。因此本轮验证了指认与结案页面流程，动机的推理正确性还需单独设计和验收。

浏览器脚本为 `tools/browser_smoke.cjs`，使用独立安装的 Playwright 和 Chromium。运行本地演示后执行 `node tools/browser_smoke.cjs`。可通过 `PLAYWRIGHT_MODULE` 指向已有 Playwright，通过 `CHROME_PATH` 指定 Chrome，通过 `DEMO_PORT` 选择前端端口。设置 `DEMO_SCREENSHOT` 可以保存同一时刻的截图。[实况截图](evidence/palace-investigation.png) · [三组固定输入的事件记录](evidence/paths.jsonl)

构建验证使用 `npm run build`，退出码为 0，输出可部署的静态文件；上游组件仍有未使用变量和 Hook 依赖警告。此处交付公开源码与本机演示，未部署公网游戏服务。

## 参考经验与下一阶段

AI Murder Mystery V2 的 [PrivateNpcAgentCoordinator](https://github.com/DilanRG/ai-murder-mystery-v2/blob/e0047c3a480e193dc22a6d280ea3a2b88bd6149b/backend/game/private_npc_agents.py) 把角色候选、提案和回退分开。Detective Agentic Mysteries 的 [主动触发](https://github.com/suuus/detective-agentic-mysteries/blob/4ed665694fe35bd7b0283ad03c7ea2bfbf1eb0f2/public/js/npcApproach.js) 与 [会面调度](https://github.com/suuus/detective-agentic-mysteries/blob/4ed665694fe35bd7b0283ad03c7ea2bfbf1eb0f2/server.ts) 提供事件调度对照。G03 的代码独立实现，无空间场景，普通玩家无法查询私聊日志。上游整份剧本可以进入原浏览器和自由聊天提示，当前只保证**新增角色控制器**的视角隔离；这里验证的是本机单人游戏。

阶段 1 的交付是可验证的有限行动。进入阶段 2 后，同一个校验入口将接收自然语言委派的候选，继续实现接受、拒绝、协商、任务去重、异步回报与取消。之后再验证第二个案件配置、真实模型授权、快照回溯和批量评测。当前记录支持追查因果，尚未实现从任意事件回滚。
