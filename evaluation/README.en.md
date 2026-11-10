# Evaluation: testing the architecture with development projects

[中文](README.md) | **English**

For the architecture itself, see [../docs/workflow.en.md](../docs/workflow.en.md); it does not depend on anything here.

| Path | Contents |
|---|---|
| [bench/](bench/README.en.md) | Benchmark project: a fixed small to-do app. Run it once after deploying or after changing the workflow, and append the result to `bench/results.md` |
| `metrics.py` | Collects each task's queue time, elapsed time and review rounds from Kandev |

Run the scripts with this machine's Python interpreter (standard library only), for example:

```
python evaluation/metrics.py --ids kandev/kandev_ids.json
```

Your own pilot run records can go in `evaluation/pilot-*/`; that path is git-ignored.
