# Fix Prolific RETURNED and awaiting review without local results

状态：业务讨论已确认，to-spec 规格已合成；8 张票及依赖已批准、issue 待 tracker 配置发布。未实施自动同步、自动消息或线上代码变更。

本目录集中保存本任务的 grilling、术语、证据、spec 和 tickets；不保存真实参与者明细、完成码、API token 或生产提交。任务级术语放在此目录，以遵循用户要求，避免扩展仓库其他工作流。

- [术语](CONTEXT.md)
- [已验证事实与证据](evidence.md)
- [Grilling 讨论与待决事项](grilling.md)
- [规格](spec.md)
- [实施 tickets](tickets.md)

用户已确定方向：同步平台 RETURNED 到本地归档；对平台待审核但无本地结果的记录进行核查，并在确认条件满足后自动请求退回。业务边界已在 grilling Rounds 1–3 确认。

已有操作：2026-09-08 经授权将 22 份 RETURNED、7 份研究者测试结果归档，保留分配历史及迁移清单。此操作不是持续同步机制。

尚无满足必要性条件的架构决策记录（ADR）；不把未确定提案写成已接受 ADR。
