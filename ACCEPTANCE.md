# G03 第二轮验收

## 基线复核

在 Codex Cloud 合入第二轮改动前执行 `python -m unittest discover -s tests -v`，第一轮历史用例 7 项通过。第二轮须用完整 FastAPI、生产构建和真实 Chromium 重新验收。命令、现场结果和复现路径随阶段补录。

## 角色引擎与持久化

- 运行 `python -m unittest discover -s tests -v`。其中模型选择测试用替身验证 JSON 字段、未授权候选、调用上限和超时，未向外部模型发请求。
- 完整 FastAPI 在两次独立进程中加载同一 SQLite 库，读回首次进程已受理的任务。重复请求取得相同回执，变更原请求内容复用请求 ID 返回 409，其他局查询该任务返回 404。8 个并发结算均返回同一结果，库中只产生一组受理、私聊、主张和回报事件。

## 生产构建与可重复启动

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

## 在原对话框检验

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

## 已知验收范围

- 云端的项目模型配置缺少授权凭据。Mock、规则回退和模型超时替身已验证，真实 LLM 未验证。
- 两宗有行动数据的案件接入统一引擎，其他剧本保留原聊天流程。普通旧聊天沿用原短期会话保存，任务和委托回报随当前浏览器历史中的同一局恢复。原推理笔记仍按浏览器会话保存，同一浏览器的不同案件能看到该玩家原有的笔记。
- 宫廷案保留第一轮报道的原作动机判定行为。雾港案使用作者提供的正确动机对比。

## 最短试玩路径与现场证据

1. 在剧本库进入《雾港停电案》，关闭开场说明，选宋屿。
2. 在原对话框输入“帮我去问问门卫昨晚谁进过仓库”。回报出现后，切换到阮岑。
3. 输入“是谁来问过西门出入？”，他会确认是宋屿联系了自己。玩家可以继续找林遥核对时间并亲自提交推理。

截图来自生产前端和完整 FastAPI。每张截图旁的 JSONL 是同一局在截图时实际已落库的事件，包含可见范围、来源和因果 ID；仅包含验收用 Mock 会话的游戏数据。

- 宫廷委托的回报与追问。[回报截图](docs/evidence/round2/palace-delegation.png) · [回报事件](docs/evidence/round2/palace-delegation.jsonl) · [追问截图](docs/evidence/round2/palace-follow-up.png) · [追问事件](docs/evidence/round2/palace-follow-up.jsonl)
- 宫廷案提交指认后的页面。[结案截图](docs/evidence/round2/palace-closed.png) · [结案时的事件](docs/evidence/round2/palace-closed.jsonl)
- 雾港案门卫的具名陈述与玩家结案。[追问截图](docs/evidence/round2/harbor-follow-up.png) · [追问事件](docs/evidence/round2/harbor-follow-up.jsonl) · [结案截图](docs/evidence/round2/harbor-closed.png) · [结案时的事件](docs/evidence/round2/harbor-closed.jsonl)

## 2026-11-25 云端恢复复验

在现有 Cloud 工作区复验 `3d81b37e15a9267918739e671b9a4d5e4204722b`。此次只更新验收和交付随记。

- `python -m unittest discover -s tests -v`，15 项通过。
- `python tools/check_delegation.py`，完整 FastAPI 从 PID 6071 重启到 6095。6 个并发恢复请求获得同一终态，库中只有一次私聊和回报。双案、私聊隔离、非法证物和失败回报均通过。
- `cd web && npm run build`，退出 0，生成 `main.4c294d83.js`，393.72 kB gzip。原有 ESLint 警告仍在。
- `python tools/round2_runtime.py --data-dir /workspace/scratch/g03-resume/browser-db` 配合上面的 Playwright 命令运行。两案从剧本库到结案均通过，雾港案的恢复请求被丢弃后刷新，游戏只显示一份回报。5 组新截图与轨迹复核了事件标识、父事件顺序以及私聊可见范围，事件数与仓库中的 5 组存档一致，分别为 14、18、46、11、38。
- 云端项目模型配置复核仍无授权凭据，真实 LLM 未验证。

仓库连接取得写权限后，验收代码和报告已推送到第二轮 Draft PR。创建时核对头部 `0b72db9ba09e12e6dcbcf496be897537b9318f63`，目标分支头部 `548d31a038a6067da852a82a47cdfdaf43e2cead`。[第二轮 Draft PR](https://github.com/bingc11/g03-dynamic-mystery/pull/2)
