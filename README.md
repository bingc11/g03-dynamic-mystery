# G03 动态悬疑调查游戏

基于 [ScottishFold007 / ai-murder-mystery](https://github.com/ScottishFold007/ai-murder-mystery/tree/3afe5bccb989ec1b8964c0ff851e99c5484c80fe) 的非商业教学改作。原作者提供 React、Mantine 和 FastAPI 调查游戏。本项目探索如何让原有角色根据自己获知的线索采取可核验的行动。

**阶段一可以复演一个真实改变下一步调查的行动。** 在《深宫血色：玉玺谜云》中，玩家给太平公主看秘录遗失记录。公主可以私下联系御史；玩家再去询问，才会听到御史对这次联系的陈述。改给另一人看，御史收到的信息随之改变。角色与游戏规则均在本地运行。[演示步骤、源码地图和验证记录](docs/PHASE1.md)

## 一分钟看懂改动

在仓库根目录执行以下命令。复演和规则测试仅需 Python 3.12 标准库。

```sh
python -X utf8 tools/replay.py
python -m unittest discover -s tests -v
```

## 打开原游戏

使用 Python 3.12 的虚拟环境和 Node 22。在仓库根目录安装后端依赖并开启本地模式：

```sh
python -m pip install -r api/requirements.txt
python tools/local_demo.py
```

在第二个终端执行：

```sh
cd web
npm install --legacy-peer-deps
npm run start:local
```

浏览器打开 http://127.0.0.1:5001 。普通对话清楚标注为本地模拟；“离线行动”由角色知识和裁判决定。原项目的真实模型配置保留，启动此演示不需要 API key。建议在同一页中切换受访者；刷新页面会开启新的行动会话。

基底保留原许可与署名，原项目追溯至 Paul Scotti 和 Will Beddow 的 AI Murder Mystery Hackathon。上游的运行环境配置与数据库不进入此公开仓库。[原作使用说明](https://github.com/ScottishFold007/ai-murder-mystery/blob/3afe5bccb989ec1b8964c0ff851e99c5484c80fe/README.md) · [许可全文](LICENSE)
