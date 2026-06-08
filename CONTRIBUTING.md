# Contributing to OpenInterview

感谢你考虑参与 OpenInterview。这个项目面向计算机类校招面试训练，欢迎贡献方向题库、评分标准、模型适配器、前端体验和工程化能力。

## 开发原则

- 校招优先：所有功能都应服务计算机类校招面试训练。
- 可解释：面试追问和评分需要能追溯到方向、难度、rubric 或候选人回答。
- 可替换：LLM、ASR 和 TTS 都应通过适配层接入。
- 可本地运行：核心流程应该能在无 API key 的情况下跑通。

## 本地验证

```powershell
cd apps\api
python -m unittest discover -s tests
```

## 贡献方向

- 新增岗位方向：例如客户端、数据库内核、编译器、运维开发。
- 完善题库和追问链路。
- 增加本地模型 provider。
- 改进面试报告和复习计划。
