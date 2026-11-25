# G03 验收记录

## Issue #5 云端验收

2026 年 11 月 25 日（北京时间）在 Codex Cloud 从 PR #2 的 `0119ed0c49a7b9d936374126401dc5f1a93c5964` 派生分支 `feature/g03-agent-investigation`，基线 35 项单测重新通过。下列结果均来自本轮。复验的实现及脚本提交为 `5a4f4657ee207c0c662fc59fe9638fb4662c5e51`。新 Draft PR 的目标分支是 `feature/scottishfold-delegation`。[Issue #5](https://github.com/bingc11/g03-dynamic-mystery/issues/5)

| 最终标准 | 本轮验证 |
| --- | --- |
| 1 · 真实模型证据 | `llm-required` 启动完整 FastAPI，雾港和宫廷各完成 12 次真实决策请求，均为 `deepseek-flash`、`driver=llm` 且无失败或降级。记录提示版本 `g03-issue5-v2`、时间、用量和原始候选。另用严格模式在生产 Chromium 走通雾港。 |
| 2 · 完整玩家循环 | 原对话框覆盖普通聊天、已知信息询问、澄清、委托、私下联络、进度与来源、查阅材料及玩家结案。生产 Chromium 回归两案与原旧剧本。 |
| 3 · 角色差异 | 同一秘录分别展示给太平公主、御史大夫、张昌宗。程序记录各自关系、目标和所知材料，以及真实模型选中的不同动作。对同一接收事件，再用自动化验证不同信任条件改变接收者反应。 |
| 4 · 权限 | 非法候选、伪造隐藏证物、跨席回报、跨席历史游标和过早展示解释均被拒绝。记录玩家笔记为推测，未提升为事实。固定场景未见越权执行或私聊泄露。 |
| 5 · 追溯 | 事件保有稳定 ID、来源、可见范围与因果。回溯支持角色筛选和截至某一节点。父链接只投影到本席可见事件，私聊原文和 ID 保持私有。 |
| 6 · 可靠性 | 测试覆盖 6 路重复恢复、服务重启、刷新、过期、非法/格式错误输出、严格模式超时后重新结算、保存事务失败。子进程在构造结算后未落库直接退出，API 拒绝占用中的租约，租约期满后只结算一次。该试验通过测试数据库强制模拟到期。 |
| 7 · 意图质量 | 56 条固定语料覆盖指定路由并补增联系回执、记忆查询和双目标保护。最终严格真实模型加同主题只读判别得到 55/56（98.21%），无把错误意图路由为新委托。原始模型候选单算 49/56（87.5%）。 |
| 8 · 三案复用 | 合成《信标校验》只添加案件 JSON。完整 FastAPI 运行联络、出示前置材料、查阅与授予隐藏证物并结案。 |
| 9 · 玩家辅助 | 模型按所在席位信息组织任务草稿，选中一步只填入对话框。原文可以编辑。总结区分核实材料、待核实主张和玩家推测，保留来源。 |
| 10 · 回归 | 43 项 Python 单测、两项完整 FastAPI 集成检查、Mock / Rules 双案固定情境、React 生产构建和 Chromium 回归。构建产物 `main.167c29d0.js`，396.89 kB gzip，保留上游 lint 警告。 |
| 11 · 文档 | 启动和模型配置、调用预算、架构与权限、剧本制作、课堂路径、复现命令和证据均可从下方进入。 |

### 执行命令

```sh
NPC_DECISION_MODE=mock python -m unittest discover -s tests
python tools/check_delegation.py
python tools/check_investigation.py
python tools/simulate_cases.py --driver mock --output /tmp/g03-mock.json
python tools/simulate_cases.py --driver rules --output /tmp/g03-rules.json
python tools/check_intents.py --output /tmp/g03-intent-mock.json
python tools/check_intents.py --mode llm-required --max-attempts 65 --output /tmp/g03-intent-live.json
python tools/check_live_investigation.py --output /tmp/g03-strict-cases.json
python tools/simulate_cases.py --driver llm --contrast --max-provider-attempts 7 --output /tmp/g03-roles.json
(cd web && npm run build)
```

两个完整 FastAPI 检查与上述最终命令退出 0。真实角色对照的模式为 `llm`，实测四次请求都成功，无降级。固定语料的历史首跑为 49/56，退出 1。加同主题只读分类后重新运行完整 56 条语料，退出 0。唯一误判是「替我核对这两份证词」走澄清。澄清无副作用，明确说出校时日志可继续。Mock 为 55/56，唯一错误是把询问监控显示时刻当作闲聊。语料命中率只反映该固定集合。[意图评测复测](docs/evidence/issue5/intent-deepseek.json) · [Mock 对照](docs/evidence/issue5/intent-mock.json) · [固定语料](tools/intent_samples.tsv)

严格双案共 24 次成功请求、42,181 个输入 token、215 个输出 token、24.406 秒累计外部请求时长。严格意图复测共 56 次成功请求、94,995 个输入 token、503 个输出 token、61.617 秒累计时长。另一次严格雾港 Chromium 流程有 7 次全部成功的请求，9,569 个输入 token、67 个输出 token、8.284 秒累计时长，无回退。报告保留归一化后的路由和原始候选 ID。公开记录使用固定测试输入，并省略密钥、邀请凭据和隐藏思维链。[严格双案事件轨迹](docs/evidence/issue5/strict-cases.json) · [生产浏览器模型记录](docs/evidence/issue5/strict-browser-model.json) · [角色对照](docs/evidence/issue5/role-comparison.json)

启动 `python tools/round2_runtime.py --data-dir /tmp/g03-browser --api-port 10116 --web-port 5116`。安装 Playwright 后用 Chromium 验证生产界面。复跑真实雾港时启动器加 `--llm-required`，浏览器命令加 `DEMO_LIVE=1`。示例使用 `chromium` 的系统路径。

```sh
npm install --prefix /tmp/g03-browser-tools playwright
PLAYWRIGHT_MODULE=/tmp/g03-browser-tools/node_modules/playwright \
CHROME_PATH=/usr/bin/chromium DEMO_API_PORT=10116 DEMO_PORT=5116 \
node tools/browser_delegation.cjs
```

### 试玩与材料

在《雾港停电案》向宋屿发出「帮我去问问门卫昨晚谁进过仓库」，再向阮岑问「是谁来问过西门出入？」。打开「调查记录」，输入「先弄清两座钟，再核对出入和送审底单」，点「拆解调查目标」。把建议填入指定角色的对话框，确认措辞并主动发送。更新复盘后选择角色和截止事件，继续取证并由玩家结案。

- [真实雾港结案截图](docs/evidence/issue5/strict-harbor.png) · [对应事件](docs/evidence/issue5/strict-harbor.jsonl)
- [宫廷 Mock 通关截图](docs/evidence/issue5/palace-closed.png) · [对应事件](docs/evidence/issue5/palace-closed.jsonl)
- [雾港第二席截图](docs/evidence/issue5/harbor-second-seat.png) · [对应事件](docs/evidence/issue5/harbor-second-seat.jsonl)
- [草稿与回溯 Mock 浏览器截图](docs/evidence/issue5/plan-replay.png) · [对应事件](docs/evidence/issue5/plan-replay.jsonl)
- [启动说明](README.md) · [系统与权限边界](docs/ARCHITECTURE.md) · [案件接入](docs/CASE_AUTHORING.md) · [8 分钟课堂路线](docs/CLASSROOM.md)

合成案件用于引擎测试，未在剧本库上架。双席在独立 Chromium 会话验证，真人课堂观察仍待进行。普通闲聊采用可审计的角色候选，模型可以挑选表达和辅助步骤。柔性指代仍可能需要追问。独立 `tsc --noEmit` 的 Mantine 基线问题与个别缺失旧头像保持列在历史记录中。

## Issue #4 交付验收

2026 年 11 月 25 日在 Codex Cloud 从 `c576b2aeaf25f4ce219992e69a51882bedb546e9` 继续，19 项基线单测独立复跑通过。最终验收使用 Python 3.12.14、Node 24.22.3、Chromium 156.0.8078.79、完整 `main:app` 和生产 React 前端。两案使用不同的案件数据与同一套角色、任务、席位和事件引擎。[主任务](https://github.com/bingc11/g03-dynamic-mystery/issues/4) · [Draft PR #2](https://github.com/bingc11/g03-dynamic-mystery/pull/2)

| 项目 | 云端实测结果 |
| --- | --- |
| A · 玩家体验 | 从剧本库开始，经过普通聊天、证物出示、自然语言委托、角色私下联系、追问、线索总结和复盘，由玩家提交结案。Mock 的双浏览器验证覆盖两席位的独立调查、证物持有、显式共享和各自结案。浏览器回归运行了雾港案、宫廷案和一项旧剧本普通对话。 |
| B · 真实角色行为 | 官方 `deepseek-flash`（DeepSeek V4.1 Flash）通过模型查询和真实结构化响应。生产页面中宋屿接受委托、联系阮岑，阮岑独立披露，后续追问连到已有事件。同样出示秘录，真实模型让太平公主私下联系、御史查阅、张昌宗暂缓。实际连接错误触发了规则回退，日志及界面能区分使用的驱动。 |
| C · 可靠性与权限 | 35 项单测、两项完整 FastAPI 检查、生产构建和 Chromium 回归通过。已验证两个进程重启后恢复、六路并发恢复只结算一次、过期任务、工作失败、越权拒绝、证物持有、私聊隔离、主张与事实分开，以及结案由服务端确定。游戏运行时密钥来自服务端的忽略配置文件。模型决策有截止时间、预算、日志和规则回退。 |
| D · 可重复评测 | 两案共四组固定情境。Mock 和 Rules 各到达 6/6 条预设线索，初次 DeepSeek 到达 4/6，修正通用意图提示后，针对两处偏差的原句复测到达 3/3。在本次工作中共记录 72 次结构化游戏决策请求尝试，其中 5 次系已诊断的传输故障。公开报告包含请求摘要、选择、用量与耗时。课堂材料包含课程目标映射及教师待确认内容。 |
| E · 交付材料 | 提供原界面完整路线、双席操作、8 分钟课堂脚本、架构及权限图、案件接入指南、自动评测和真实截图及事件记录。README、STATUS 与本验收同步更新，并在 Issue #4 记录交付。 |

### 实际命令与结果

以下命令在仓库根目录使用上述环境执行。[启动与服务端配置](README.md)

```sh
NPC_DECISION_MODE=mock python -m unittest discover -s tests
python tools/check_delegation.py
python tools/check_investigation.py
(cd web && npm run build)
python tools/round2_runtime.py --data-dir /tmp/g03-mock --api-port 10105 --web-port 5105
```

- 单测 35/35。`check_delegation.py` 启动完整 FastAPI（PID 15352 → 15358），验证持久化受理、6 路并发恢复、事件只结算一次、权限与多个任务分支。`check_investigation.py` 启动另一组完整 FastAPI（PID 16579 → 16734），验证两席私有状态、持有证物、公开回报、仅席位自己能查看的调查提示、独立结案、到期与重启恢复。
- `npm run build` 退出 0，主包 `main.835f9c03.js`，396.27 kB gzip。仍有历史的 ESLint 警告。生产浏览器留证时使用的同源码构建产物为 `main.05101f47.js`。在 `web/` 单独运行锁定版本的 `./node_modules/.bin/tsc --noEmit`，基线与交付版本均在 Mantine 的声明处退出 2，诊断一致。仓库基线若干旧头像仍返回 404。
- 在完整 FastAPI 和生产前端运行下方脚本退出 0。两个 Chromium 浏览器上下文充当独立调查席位。验证了原对话框里的接受并完成、拒绝、澄清、权限不足、前置材料不足及执行失败。查回的结果包含门卫的目击主张、校时和复电记录、出入领用表、送审底单以及御史台副册。可总结线索并请求基于可见材料的下一步提示。刷新前丢弃一次恢复请求，刷新后读回且只显示一份回报。
- 真实浏览器用 `--live` 启动，雾港的联系、独立披露、共享、追问和结案链路共 4 次成功的真实模型请求。评测中另外保留 Mock、Rules、DeepSeek 四组固定样本、复测、同一证物实验和失败记录。结案解释在当前席位提交正确推理后由玩家主动展开。[自动评测和调用摘要](docs/EVALUATION.md)

```sh
npm install --prefix /tmp/g03-browser-tools playwright
PLAYWRIGHT_MODULE=/tmp/g03-browser-tools/node_modules/playwright \
CHROME_PATH=/usr/bin/chromium DEMO_API_PORT=10105 DEMO_PORT=5105 \
node tools/browser_delegation.cjs
```

### 最短路线与证据

1. 打开 `/library`，选《雾港停电案》。在宋屿的原对话框输入「帮我去问问门卫昨晚谁进过仓库」。
2. 等待回报，切到阮岑问「是谁来问过西门出入？」。调查记录中可查看回报与追问的来源及先后。
3. 可邀请第二位玩家加入。联系回报在发送者点击「公开回报」后出现在另一席的公开记录。继续核查时间、领用和送审材料，通过「提交推理」完成案件。[完整试玩路线](docs/CLASSROOM.md)

- 《雾港停电案》真实模型结案与同一局的来源记录。[生产截图](docs/evidence/issue4/live-harbor-closed.png) · [事件轨迹](docs/evidence/issue4/live-harbor-closed.jsonl)
- 同一雾港局第二席的公开事件复盘。[生产截图](docs/evidence/issue4/harbor-second-seat.png) · [事件轨迹](docs/evidence/issue4/harbor-second-seat.jsonl)
- 宫廷案的生产浏览器 Mock 结案，包含真实落库的角色核查事件。[生产截图](docs/evidence/issue4/palace-closed.png) · [事件轨迹](docs/evidence/issue4/palace-closed.jsonl)

技术验收覆盖两席位的可操作流程。尚无两位真人课堂观察记录，实际课程评分标准和认可仍由教师确认。真实模型在含糊或不同表述下可先追问，固定样本中的行动概率和耗时不能外推到所有玩家输入。[课程映射与演示](docs/CLASSROOM.md) · [已知边界](docs/ARCHITECTURE.md)

## 第二轮历史验收

### 基线复核

在 Codex Cloud 合入第二轮改动前执行 `python -m unittest discover -s tests -v`，第一轮历史用例 7 项通过。第二轮须用完整 FastAPI、生产构建和真实 Chromium 重新验收。命令、现场结果和复现路径随阶段补录。

### 角色引擎与持久化

- 运行 `python -m unittest discover -s tests -v`。其中模型选择测试用替身验证 JSON 字段、未授权候选、调用上限和超时，未向外部模型发请求。
- 完整 FastAPI 在两次独立进程中加载同一 SQLite 库，读回首次进程已受理的任务。重复请求取得相同回执，变更原请求内容复用请求 ID 返回 409，其他局查询该任务返回 404。8 个并发结算均返回同一结果，库中只产生一组受理、私聊、主张和回报事件。

### 生产构建与可重复启动

以下命令在仓库根目录运行。云端执行了 Python 3.12、Node 24 和 Chromium 156。安装使用 `npm ci --legacy-peer-deps`，以锁定与第一轮相同的依赖树。生产构建退出 0，主 JS 为 393.72 kB gzip，仍有原上游组件的 ESLint 警告。

```sh
python -m pip install -r api/requirements.txt
(cd web && npm ci --legacy-peer-deps && npm run build)
python -m unittest discover -s tests -v
python tools/check_delegation.py
python tools/round2_runtime.py --data-dir /tmp/g03-browser-run
```

单测共 15 项通过。HTTP 测试启动完整 `main:app`，在两个不同进程使用同一 SQLite 文件。测试覆盖重复提交、并发恢复、跨局隔离、非法证物和后台事件链。另有独立验证将并发恢复增至 8 个请求，终态一致且只结算一次。

另开一个终端运行生产浏览器回归。Chromium 需要在当前环境可用。

```sh
npm install --prefix /tmp/g03-browser-tools playwright
PLAYWRIGHT_MODULE=/tmp/g03-browser-tools/node_modules/playwright \
CHROME_PATH=/usr/bin/chromium \
DEMO_EVIDENCE_DIR=/tmp/g03-round2-evidence \
DEMO_NPC_DB=/tmp/g03-browser-run/npc.db \
node tools/browser_delegation.cjs
```

### 在原对话框检验

| 角色与输入 | 实际观察 |
| --- | --- |
| 太平公主：“能不能替我查一件事？” | 追问要联系的人物或要核查的材料 |
| 太平公主：“劳烦你向御史打听一下宫闱秘录的借阅登记。” | 先受理，实际私下联系御史，回报御史称出库签押不完整 |
| 御史大夫：“请帮我对一对宫闱秘录的借阅登记。” | 读取御史台副册，回报出库栏没有签押 |
| 武惠妃：“劳烦你核查一下封存的内廷名册。” | 因与调查者关系紧张拒绝 |
| 太平公主：“烦请查一查封存的内廷名册。” | 无权查阅 |
| 太平公主：“麻烦翻一翻雨夜那份原簿。” | 已受理并尝试调阅，原件无法调取，任务以失败结算 |
| 宋屿：“帮我去问问门卫昨晚谁进过仓库” | 联系阮岑，得到二十一点四十六分、编号 07 背心和未辨出脸的亲历陈述 |
| 林遥：“替我核对这两份证词。” | 调取校时和复电日志，确认监控时钟快八分钟 |
| 阮岑：“可以帮我翻翻七号背心的领用表吗？” | 缺少工单时说明条件，玩家出示工单后实际核查领用表 |

宫廷案的同一份秘录遗失记录分别交给太平公主、御史大夫和张昌宗。公主关注秘录，信任御史并选择私下询问。御史掌握副册且可直接查阅，选择核对对象。张昌宗关注香囊，缺少秘录权限，选择保留材料。事件链由单测核对。

雾港案中，林遥把同一条时钟误差观察告诉宋屿。宋屿对林遥的信任为 1 时暂时采信，会引导玩家去问阮岑用的哪座钟。信任为 0 时，他依据自身核查能力质疑，请玩家找林遥复核日志。两次都把传话保留为主张。单测验证两种状态，浏览器验证默认状态的后续线索。

浏览器验证了原普通对话、AI 搭档、人物切换、两处证物出示、笔记保存、刷新和两个案件的结案流程。测试在浏览器丢弃一次恢复请求后刷新，原已受理的任务会继续并只显示一条回报。另一次人工安排的浏览器操作核对了雾港送审底单，选择错误动机后修正，进入结案对话。

### 已知验收范围

- 云端的项目模型配置缺少授权凭据。Mock、规则回退和模型超时替身已验证，真实 LLM 未验证。
- 两宗有行动数据的案件接入统一引擎，其他剧本保留原聊天流程。普通旧聊天沿用原短期会话保存，任务和委托回报随当前浏览器历史中的同一局恢复。原推理笔记仍按浏览器会话保存，同一浏览器的不同案件能看到该玩家原有的笔记。
- 宫廷案保留第一轮报道的原作动机判定行为。雾港案使用作者提供的正确动机对比。

### 最短试玩路径与现场证据

1. 在剧本库进入《雾港停电案》，关闭开场说明，选宋屿。
2. 在原对话框输入“帮我去问问门卫昨晚谁进过仓库”。回报出现后，切换到阮岑。
3. 输入“是谁来问过西门出入？”，他会确认是宋屿联系了自己。玩家可以继续找林遥核对时间并亲自提交推理。

截图来自生产前端和完整 FastAPI。每张截图旁的 JSONL 是同一局在截图时实际已落库的事件，包含可见范围、来源和因果 ID；仅包含验收用 Mock 会话的游戏数据。

- 宫廷委托的回报与追问。[回报截图](docs/evidence/round2/palace-delegation.png) · [回报事件](docs/evidence/round2/palace-delegation.jsonl) · [追问截图](docs/evidence/round2/palace-follow-up.png) · [追问事件](docs/evidence/round2/palace-follow-up.jsonl)
- 宫廷案提交指认后的页面。[结案截图](docs/evidence/round2/palace-closed.png) · [结案时的事件](docs/evidence/round2/palace-closed.jsonl)
- 雾港案门卫的具名陈述与玩家结案。[追问截图](docs/evidence/round2/harbor-follow-up.png) · [追问事件](docs/evidence/round2/harbor-follow-up.jsonl) · [结案截图](docs/evidence/round2/harbor-closed.png) · [结案时的事件](docs/evidence/round2/harbor-closed.jsonl)

### 2026-11-25 云端恢复复验

在现有 Cloud 工作区复验 `3d81b37e15a9267918739e671b9a4d5e4204722b`。此次只更新验收和交付随记。

- `python -m unittest discover -s tests -v`，15 项通过。
- `python tools/check_delegation.py`，完整 FastAPI 从 PID 6071 重启到 6095。6 个并发恢复请求获得同一终态，库中只有一次私聊和回报。双案、私聊隔离、非法证物和失败回报均通过。
- `cd web && npm run build`，退出 0，生成 `main.4c294d83.js`，393.72 kB gzip。原有 ESLint 警告仍在。
- `python tools/round2_runtime.py --data-dir /workspace/scratch/g03-resume/browser-db` 配合上面的 Playwright 命令运行。两案从剧本库到结案均通过，雾港案的恢复请求被丢弃后刷新，游戏只显示一份回报。5 组新截图与轨迹复核了事件标识、父事件顺序以及私聊可见范围，事件数与仓库中的 5 组存档一致，分别为 14、18、46、11、38。
- 云端项目模型配置复核仍无授权凭据，真实 LLM 未验证。

仓库连接取得写权限后，验收代码和报告已推送到第二轮 Draft PR。创建时核对头部 `0b72db9ba09e12e6dcbcf496be897537b9318f63`，目标分支头部 `548d31a038a6067da852a82a47cdfdaf43e2cead`。[第二轮 Draft PR](https://github.com/bingc11/g03-dynamic-mystery/pull/2)

### 第二轮审查回归

在 `4d4369c5055803c2a3c4288f002d323624e1f9eb` 复现两条审查问题。新局直接问阮岑“昨晚西门谁进过仓库？”曾误返回联络状态。御史大夫核对副册后，旧联络也曾遮住最新结果。

- `python -m unittest discover -s tests -v` 通过 19 项。新增回归检查直接作证的来源、披露权限、进展回报与联络来源，以及多种问结果的表达会取回原回报。
- `python tools/check_delegation.py` 在完整 FastAPI 复验通过，从 PID 8305 重启到 8310。6 路并发恢复得到同一终态，私聊和回报均落库一次。
- 用现有生产前端和隔离的 FastAPI 实例跑过完整 Chromium 双案回归。专项浏览器验证了阮岑直接提供证词，宋屿无法代答，以及御史能同时提供最新副册回报和已获准追问的旧联络来源。
