# 07: 状态通知自动触发安全对账

**Status:** Approved draft — pending tracker publication

**Publication label:** ready-for-agent

**Blocked by:** 02 — 研究者能只读查看平台与本地差异。

**What to build:** 从公网HTTPS签名事件到可靠持久化、当前API状态核查和只读对账报告，实现自动触发；定期当前状态对账补偿漏事件。

- [ ] 验签、研究隔离、事件去重、乱序处理与中断恢复均可验证。
- [ ] 通知只作为核查触发源，不假定包含完成码，也不假定接入前历史事件可回放。
- [ ] API故障保留待办并重试，不触发迁移或消息；调度参数明确可配置。
- [ ] 核实账号/workspace权限及HTTPS条件，保留其他订阅/secret，不覆盖既有集成。
- [ ] 完整演示“签名事件/定时触发→最新状态→对账报告”，本票不启用生产动作。
