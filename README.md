# G03 动态悬疑调查游戏

在原有调查面板中扮演调查者。你可以和 NPC 交谈、出示证物并用自己的话委托调查。角色会按自己的知识、关系和权限决定是否联系别人或查阅资料。请留意回报的来源、把目击陈述与核实记录分开，再由你提交最终推理。

《雾港停电案》是完整试玩主线，《深宫血色：玉玺谜云》用同一套调查引擎。两名玩家可以用独立浏览器窗口加入同一案件，保有自己的对话和证物，并主动分享回报。

## 启动

使用 Python 3.12 虚拟环境和 Node.js 22 或 24。在仓库根目录执行。

```sh
python -m pip install -r api/requirements.txt
(cd web && npm ci --legacy-peer-deps && npm run build)
python tools/round2_runtime.py --data-dir ./data/mock
```

打开 http://127.0.0.1:5001/library。默认演示使用 Mock，无需 API 密钥。邀请同局玩家时，复制「调查记录 → 邀请玩家」返回的链接，用独立浏览器窗口打开。

### 启用真实 DeepSeek

参考 `api/.env.example` 在服务端的 `api/.env` 中配置。配置文件应保留在本机，不提交到仓库。

| 变量 | 值 |
| --- | --- |
| `INFERENCE_SERVICE` | `deepseek` |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | `deepseek-flash` |
| `DEEPSEEK_API_KEY` | 你的 DeepSeek API 密钥 |
| `NPC_DECISION_MODE` | `llm` |

`deepseek-flash` 对应 DeepSeek-V4.1-Flash-1017。启用后，后台用真实模型选择结构化行动，案件数据和规则引擎保留事实、权限及结案判定。[DeepSeek 模型文档](https://api-docs.deepseek.com/quick_start/pricing/)

```sh
python tools/round2_runtime.py --live --data-dir ./data/deepseek
```

先结束占用同一端口的 Mock 演示。启动器默认使用前端端口 5001、API 端口 10000。真实模型不可用或达到预算时，调查决策降级为规则，面板会标记其来源。常规自动回归用 Mock 或 Rules，避免测试依赖外部模型。

## 第一条委托

1. 在剧本库打开《雾港停电案》，选择宋屿。
2. 输入「帮我去问问门卫昨晚谁进过仓库」。宋屿回报后，你可以在对话中公开这条线索给同局玩家。
3. 问阮岑「是谁来问过西门出入？」，再找林遥核对两份证词的时间。「调查记录」可以整理线索、建议下一步和回看已有事件。

[完整试玩及课堂演示](docs/CLASSROOM.md) · [架构与权限边界](docs/ARCHITECTURE.md) · [新案件接入](docs/CASE_AUTHORING.md) · [验收和复现](ACCEPTANCE.md) · [自动评测与真实模型记录](docs/EVALUATION.md)

基于 ScottishFold007 / ai-murder-mystery 的非商业教学改作，沿用原 React、Mantine 和 FastAPI 调查游戏。原项目追溯至 Paul Scotti 和 Will Beddow 的 AI Murder Mystery Hackathon。[原作使用说明](https://github.com/ScottishFold007/ai-murder-mystery/blob/3afe5bccb989ec1b8964c0ff851e99c5484c80fe/README.md) · [许可全文](LICENSE)
