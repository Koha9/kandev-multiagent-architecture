# 评估：用具体开发项目检验架构

> 这里的内容都和某个具体的开发项目有关，用来检验多 agent 架构的效果。架构本身见 [../docs/workflow.md](../docs/workflow.md)，它不依赖这里的任何内容。

| 路径 | 内容 |
|---|---|
| `pilot-*/` | 试点记录（时间线、事件记录、评价）。涉及具体的个人项目，只保存在本机，被 git 忽略，不在公开仓库中。v3 的改进来自试点 1，结论已经写进 [docs/workflow.md](../docs/workflow.md) 的「已否决的设计」和「变更记录」 |
| [bench/](bench/README.md) | 基准项目：固定的小型待办应用，每次改 workflow 后跑一次，结果追加到 `bench/results.md` |
| `metrics.py` | 从 Kandev 采集每个任务的排队时长、用时、审核轮数（试点和基准通用） |

运行脚本用本机的 Python 解释器（只用标准库，下面用 `<python>` 表示），例如：

```
<python> evaluation/metrics.py --ids <某次试点的 kandev_ids.json>
```
