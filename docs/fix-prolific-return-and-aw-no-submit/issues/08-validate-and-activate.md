# 08: 只读验收后启用完整同步流程

**Status:** Approved draft — pending tracker publication

**Publication label:** ready-for-agent

**Blocked by:** 01、04、06、07（03、05、02 已由这些票传递阻塞）。

**What to build:** 将自动触发接入已验证的归档、超时释放和消息动作，先在真实API只读运行，再按获批清单和开关启用。

- [ ] 使用当前平台状态输出完整只读动作清单，验证权限和关联准确性。
- [ ] 隔离验证完整链路：状态事件→对账→归档/释放或消息；迟交、重启、乱序不破坏约束。
- [ ] 用户确认报告和验证结果后才启用生产迁移/释放/消息；历史消息清单单独确认。
- [ ] 独立记录每个动作和失败原因，可关闭后续自动动作；不把回滚当作自动恢复已归档结果。
- [ ] 提供真实浏览器任务、说明、音频与失败提示验证证据，缺失证据明确列出。


**Answer-arrival amendment:** See [`answer-arrival-amendment.md`](../answer-arrival-amendment.md). A complete identity-matched final answer during the missing-result wait resolves normally; status/contact/uncertain/identity exceptions remain manual.
