# 线上分页只读排查

研究：6a1bb20dfc7bbfabecc480ff。使用用户指定 profile。未修改平台或参与者数据。

已验证：
- 先前30页每页100，共2952行但只有1424个唯一submission ID；完整报告被一致性校验拒绝。
- 本轮每页100的第一页和第二页，各自均100个唯一ID，说明并非单页内部重复。
- 改为每页50，前3页各50个唯一ID；第2页与已读页重叠27个，第3页也重叠27个。更改page_size未消除跨页重复。
- meta.count均2952；next链接保留所请求的page/page_size/study。请求仍由客户端固定HTTPS源发送，未跟随返回的HTTP链接降级。

当前结论仅限：已观察到跨页重叠，不能将去重数量直接视为完整研究提交数。原因仍未确定，尚不能归因于服务端或本地请求参数。下一步核对官方分页契约、请求参数与稳定排序行为；不放宽完整性检查来启用动作。

人工门槛：归档隔离验证已获用户通过；缺失结果复查仍待确认。此只读调查不替代人工核验。

## 2026-09-10：官方参数与只读对照

官方文档确认 general submissions 的 study、page、page_size 参数有效，支持 ordering=started_at：
https://docs.prolific.com/api-reference/submissions/get-submissions
研究专用接口 GET /api/v1/studies/{id}/submissions/ 支持 started_at 排序：
https://docs.prolific.com/api-reference/studies/get-study-submissions

实际 GET 对照（仅输出汇总、未存参与者明细）：
- 通用接口增加 ordering=started_at 后，前3页各100行，页内唯一100，跨页重叠均0，meta.count=2952。
- 研究专用接口 ordering=started_at 一次返回2952行、2952个唯一ID，meta.count=2952；状态计数 AWAITING REVIEW=299、RETURNED=2593、TIMED-OUT=60。
- 专用接口 _links.next 为真，仍需检查具体链接语义；不能直接视作已完成遍历。

结论范围：默认分页重叠在前三页的显式排序对照中消失；这是排序相关问题的证据，不足以断言服务端根因。专用接口返回的唯一数量与meta相符。尚未完成通用接口全部排序分页及本地结果逐条对照；未修改客户端、启用自动操作或发送消息。上述299是本次平台接口状态计数，不是本地有效结果数，也不覆盖旧CSV时点。

完整排序对照已完成：30页2952行、2952唯一ID，每页跨页重叠为0，meta始终2952。与研究专用接口ID集合完全一致（双方差集均0）。专用接口next指向limit=0&offset=0，因此未将其用作分页修复。采用官方通用接口显式ordering=started_at作为修复方向，继续保留count/去重/循环完整性校验。证据：sorted-pagination-evidence.json。此证据证明本次读取完整，不证明平台默认排序内部根因，也不保证并发变动时快照一致。
