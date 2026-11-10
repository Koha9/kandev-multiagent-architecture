# 评估：用开发项目检验架构

**中文** | [English](README.en.md)

架构本身见 [../docs/workflow.md](../docs/workflow.md)，它不依赖这里的任何内容。

| 路径 | 内容 |
|---|---|
| [bench/](bench/README.md) | 基准项目：固定的小型待办应用。部署后或改完 workflow 后跑一次，结果追加到 `bench/results.md` |
| `metrics.py` | 从 Kandev 采集每个任务的排队时长、用时、审核轮数 |

运行脚本用本机的 Python 解释器（只用标准库），例如：

```
python evaluation/metrics.py --ids kandev/kandev_ids.json
```

自己的试点记录可以放在 `evaluation/pilot-*/`，这个路径已被 git 忽略。
