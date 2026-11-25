# G03 动态悬疑调查游戏

基于 [ScottishFold007 / ai-murder-mystery](https://github.com/ScottishFold007/ai-murder-mystery/tree/3afe5bccb989ec1b8964c0ff851e99c5484c80fe) 的非商业教学改作。原作者提供 React、Mantine 和 FastAPI 调查游戏。

在原人物对话框，你可以请《深宫血色：玉玺谜云》的太平公主向御史大夫核对秘录，也可以请《雾港停电案》的宋屿问门卫昨晚谁进过仓库。人物依权限查问或核对记录，回报会标注所据的说法或材料。你可以亲自找当事人追问，再决定怎么结案。

## 打开原游戏

使用 Python 3.12 虚拟环境以及 Node 22 或 24。在仓库根目录安装依赖并构建前端。

```sh
python -m pip install -r api/requirements.txt
cd web
npm ci --legacy-peer-deps
npm run build
cd ..
python tools/round2_runtime.py --data-dir /tmp/g03-round2
```

打开 http://127.0.0.1:5001/library，进入《雾港停电案》。在宋屿的原对话框发送“帮我去问问门卫昨晚谁进过仓库”。等待回报后，切换到阮岑问“是谁来问过西门出入？”。

演示用 Mock，无需模型密钥。刷新当前页面可恢复已受理任务和行动回报，从剧本库重开会创建一局新委托会话。普通闲聊按照原游戏保存方式运行。要切换到已配置的项目模型，运行完整 FastAPI 应用并使用 `NPC_DECISION_MODE=auto`（默认）。`mock` 可重复验收，`rules` 显式禁用模型。

[本轮验收与复现](ACCEPTANCE.md) · [本轮状态和源码](STATUS.md) · [第一轮历史记录](docs/PHASE1.md)

基底保留原许可与署名，原项目追溯至 Paul Scotti 和 Will Beddow 的 AI Murder Mystery Hackathon。[原作使用说明](https://github.com/ScottishFold007/ai-murder-mystery/blob/3afe5bccb989ec1b8964c0ff851e99c5484c80fe/README.md) · [许可全文](LICENSE)
