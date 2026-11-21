# 基准项目：每次改 workflow 后跑一次

> 目的：用一个固定的小项目比较不同 workflow 版本，不必每次都用真实项目做一次完整试点。结果可比的前提是需求、环境和 profile 都不变。
> 规模：需求按 2 个功能模块、每个模块 2 个任务（其中 1 个有前置任务）设计，实际怎么分由 pm 决定。除此之外每次都有固定的 baseline 模块（环境与骨架，最先运行）；任务描述没有写 `integration_test`，按缺省值 auto 还会有结合测试模块（最后运行）。所以通常是 4 个模块任务。
> 时长：原来估计 30–45 分钟，那是只算 2 个功能模块时的数字；加上 baseline 模块和结合测试模块后还没有实测（[results.md](results.md) 目前为空），第一次运行后按实际更新。会产生真实的 agent 会话费用。
> 在哪里跑：结果记在源仓库里，所以用源仓库的部署（链接模式）来跑和记录。独立安装目录里也有一份 `evaluation/`，但它不在版本库里，记在那里的结果不会被提交。

## 任务描述（原样使用，只替换尖括号）

```
[TASK v1]
project: bench-todo
mode: unattended
plan_only: false
mgmt_root: <工作目录>/bench/todo-mgmt-<版本>-<日期>
mgmt_template: <安装目录>/mgmt-template
repo: <工作目录>/bench/todo
role: pm
scope: pm
parent: user
pm: self
branch: <自动> base main
---
# 目标
一个本地运行的待办清单 Web 应用，用于基准测试，不对外。

# 需求（重要度从高到低）
1. 后端（Python 标准库或 FastAPI 二选一）提供待办的增、删、改、查 HTTP 接口，数据存 SQLite。
2. 前端单页：列出待办、添加、勾选完成、删除；刷新页面后数据仍在。
3. 待办可以设置截止日期，过期的待办在列表中标红。
4. 手机宽度（390px）下布局不横向滚动。

# 运行条件
- 不调用 ask_user_question_kandev；需要用户决定的事写 ADR 并登记到 attention.md。
- 本地合并，不推送远端。不使用 Docker。
- 不做任何真实 AI 或付费 API 调用（额度上限全部为 0）。
```

仓库 `<repo>` 事先用 `git init` 建一个只有 README 的空仓库（main 分支）。

## 采集的指标

运行结束（到达「人工终审」）后，在源仓库中采集每个任务的指标（`--ids` 指向这次部署的 ids 文件）：

```
python evaluation/metrics.py --ids kandev/kandev_ids.json
```

输出是每个任务一行的 JSON，不需要存进仓库；想留底可以重定向到 `evaluation/pilot-*/`（已被 git 忽略）。然后在源仓库的 [results.md](results.md) 里追加一行：

| 版本 | 日期 | 总时长 | 排队合计 | 审核退回 | 守护告警 | 人工干预 | 需求覆盖（R 满足 / 总数） | 备注 |
|---|---|---|---|---|---|---|---|---|

- 总时长：pm 任务创建到进入「人工终审」。
- 排队合计：各开发任务 `wait_min` 之和（metrics.py 输出）。
- 守护告警：`agents/guard/journal.md` 中的 ALERT 行数。
- 需求覆盖：final-report「需求覆盖」中"满足"的条数 / 4。
