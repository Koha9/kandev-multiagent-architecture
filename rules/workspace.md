# 槽位：工作区规则（时间戳、临时资源）

注入位置：所有角色的【通用规则】开头。每条一行，以 `- ` 开头。
定制方法：复制本文件到 `custom/rules/workspace.md` 后修改正文，再重新部署（见 AGENTS.md「F. 定制」）。
---
- 时间戳取自系统时钟（`Get-Date -Format "yyyy-MM-dd HH:mm"` 或 `date '+%F %R'`）。
- 临时目录、后台进程、端口登记到 NOW（开发为 now）「注意」节，步骤结束前清理。