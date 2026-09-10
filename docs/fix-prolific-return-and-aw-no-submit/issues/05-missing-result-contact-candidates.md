# 05: 确认缺失后生成唯一待联系请求

**Status:** Approved draft — pending tracker publication

**Publication label:** ready-for-agent

**Blocked by:** 02 — 研究者能只读查看平台与本地差异。

**What to build:** 从 AW 缺失发现经过十分钟复查、消息历史核查，到生成带已确认文案的待发请求或人工核查项；不实际发送。

- [ ] 检查全部AW；完整答案不因NOCODE/未知码触发请求。
- [ ] 十分钟等待可跨重启，重复事件不跳过等待或生成重复请求。
- [ ] 草稿、身份错配、其他session结果、保存故障、历史访问失败或关联不明转人工。
- [ ] 核对 return_requested 与可访问聊天，按session去重；不承诺不存在的消息历史覆盖。
- [ ] 报告展示确切 session、证据及已确认文案，历史候选清单可单独确认。


## Confirmed answer-arrival amendment

A complete identity-matched final answer arriving during the ten-minute missing-result wait resolves the same session normally with zero message POSTs and no new manual item, including after restart. Status changes, prior contact, uncertain delivery, identity conflicts, drafts, errors, other-session results, and established manual/outbound records remain protected.
