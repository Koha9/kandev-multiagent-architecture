# report · dev:<任务id>

<!-- Kandev 任务文档 report，写者：开发 agent。每次上报覆盖写；round 与「开发」步骤的 entry 一致。读者：审核 agent、模块 agent。 -->

```yaml
task: auth-02
round: 1
result: done            # done（全部 AC 实现并通过）| blocked（做不完，填 remaining）| dropped（无需改动，填 drop_reason）
commit: <hash>
changes:                # 只写路径和摘要，不贴代码
  - path: src/auth/api/login.py
    summary: 新增登录接口
tests:
  - command: pytest tests/auth -q
    result: 12 passed
  - command: ruff check src/auth
    result: 0 errors
scope_check: "OK auth-02: 2 个改动文件都在 owns 范围内"   # tools/check_owns.py 的输出原文
acceptance:
  - id: AC-1
    result: pass        # pass | fail | unverified(原因)
    evidence: tests/auth/test_login.py::test_login_ok
  - id: AC-2
    result: pass
    evidence: tests/auth/test_login.py::test_login_bad_credentials
visual_evidence: []     # ui: true 时必填：[{page, viewport, before: <路径|无（新界面）>, after: <路径>}]
initiatives: []         # 范围内的重要取舍和主动做的改进：[{what, why}]
suggestions: []         # 范围外值得做的事或需求理解上的疑问，交给模块 agent 决定：[{what, why}]
deviations: []          # 与契约不一致的地方及原因
interface_changes: []   # 对接口的任何改动（应事先获得模块 agent 同意，写明消息 id）
fixed_findings: []      # 被退回时：逐条对应 review 中的 findings
remaining: []           # result=blocked 时：还没做完的部分和卡住的原因
defects: []             # 结合测试任务测出的产品缺陷（此时 result=blocked）：[{test, steps, expected, actual, suspect}]
manual_checks: []       # 结合测试任务中自动化工具做不到、改为手动验证的场景：[{scenario, why_manual, evidence}]
drop_reason: null       # result=dropped 时：为什么不需要改动，附证据（命令输出、已覆盖它的任务或提交）
open_questions: []
```
