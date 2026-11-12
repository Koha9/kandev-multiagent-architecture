# review · rev:<任务id>

<!-- Kandev 任务文档 review，写者：审核 agent。每轮覆盖写，历史轮次由模块 agent 在验收时汇总。读者：开发 agent、模块 agent。 -->

```yaml
task: auth-02
round: 1                  # = 审核步骤的 step_entry_number
reviewer_session: <session uuid>   # 别人要就结论提问时，用它定位这次审核会话
verdict: pass             # pass | minor | direction
checks:                   # 审核者自己重跑的结果
  - command: pytest tests/auth -q
    result: 12 passed
  - command: ruff check src/auth
    result: 0 errors
scope_check: "OK auth-02: 2 个改动文件都在 owns 范围内"   # 审核者自己运行 tools/check_owns.py 的输出原文；VIOLATION 即 high 级 finding
criteria:                 # evidence 必须是审核者亲自确认的内容，不能只转述 report
  - id: AC-1
    result: pass          # pass | fail | unverified(原因，例如需要真实调用)
    evidence: test_login_ok 断言 200 且响应含 token；我运行时通过
  - id: AC-2
    result: pass
    evidence: test_login_bad_credentials
visual_check: null        # ui: true 时：截图是否存在、是否与 AC 一致boundary_check:           # 至少 1 个边界情况的亲自抽查
  - case: 空题库时抽题
    result: 返回 count=0，没有异常（test_practice.py::test_empty_bank）
findings:                 # 只指出问题，不写实现方案
  - severity: high        # high | medium | low
    where: src/auth/api/login.py:42
    issue: 用户不存在与密码错误返回了不同的错误信息
    expected: 两者都返回 BAD_CREDENTIALS（AC-2）
direction_issue: null     # verdict=direction 时填写：{summary, affects, suggestion}
```
