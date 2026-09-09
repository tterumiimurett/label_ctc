# Ticket 2 implementation report

状态：已实现并完成本地修复轮次，未部署。

## 交付

- 新增 `prolific.ctc_verification_app.reconciliation.reconcile_current_state`，只读分页读取平台 submissions，并扫描本地正式结果、`excluded-results`、drafts 和 assignments。
- 报告分离平台 submission、本地最终结果、临时占位；按完成码分类 normal/NOCODE/unknown/absent。
- 核对 study/session/participant；记录归档、草稿、其他 session 和身份不一致证据。
- RETURNED、TIMED-OUT、AWAITING REVIEW 分别输出分类与拟动作；查询/文件故障不转化为“无答案”。
- 所有结果为 JSON-ready report，明确 `writes_performed: false`；没有平台写 API、消息、归档、分配或业务数据修改。
- 修复审查发现：递归扫描 `excluded_submissions`，解析错误保留为 `read_error`，规范化 participant 字段并拒绝缺失/错 study，RETURNED/TIMED-OUT 有结果进入人工复核，过期/已提交占位不计入，支持研究有效完成码集合和同参与者同研究其他 session 证据。
- 新增 `ProlificSubmissionClient` 与 JSON CLI，包含只读认证、分页、429/5xx/网络重试和限流等待。

## 验证

- `python3 -m unittest tests.test_read_only_reconciliation -v`：3 passed。
- `python3 -m unittest discover -s tests -v`：33 passed。
- 修复轮次聚焦测试：6 passed；覆盖损坏 JSON、递归归档、官方 participant 对象、状态分类、占位过期和 HTTP 429。
- `python3 -m py_compile prolific/ctc_verification_app/reconciliation.py`：passed。

## 限制

- 未使用真实凭据或生产 API；当前环境未配置可用的只读平台客户端，因此没有声称 live validation。调用方需提供实现 `list_submissions(study_id, cursor, page_size)` 的客户端，并将真实分页字段适配到该接口。
- 报告是只读预览，不执行 Ticket 3–8 的归档、释放、联系、webhook 或定时任务。

原实现提交哈希：bc0a708。
修复提交哈希：d5730c4。
