# 槽位：Git 规则

注入位置：模块管理、开发、审核、合并角色的 prompt 头部，作为【Git 规则】一段。正文为空（出厂状态）时不注入。
这里写你自己的 git 习惯，例如提交信息的语言和格式、是否允许 amend / force、提交粒度、签名。每条一行，以 `- ` 开头。
不能在这里改的（引擎依赖它们）：分支拓扑（`mod/<模块>`、`integration`）、commit message 以任务 id 开头、合并步骤的快进合入。
推送远端、PR 还是本地合并按项目定，写在项目的 conventions.md 和 environment.md 里，不写在这里。
定制方法：复制本文件到 `custom/rules/git.md`，在 `---` 之后写正文，再重新部署（见 AGENTS.md「F. 定制」）。
---