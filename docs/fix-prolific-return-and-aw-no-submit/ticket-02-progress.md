# Ticket 2 implementation report

状态：已实现，未部署。

## 交付

- 新增 `prolific.ctc_verification_app.reconciliation.reconcile_current_state`，只读分页读取平台 submissions，并扫描本地正式结果、`excluded-results`、drafts 和 assignments。
- 报告分离平台 submission、本地最终结果、临时占位；按完成码分类 normal/NOCODE/unknown/absent。
- 核对 study/session/participant；记录归档、草稿、其他 session 和身份不一致证据。
- RETURNED、TIMED-OUT、AWAITING REVIEW 分别输出分类与拟动作；查询/文件故障不转化为“无答案”。
- 所有结果为 JSON-ready report，明确 `writes_performed: false`；没有平台写 API、消息、归档、分配或业务数据修改。

## 验证

- `python3 -m unittest tests.test_read_only_reconciliation -v`：3 passed。
- `python3 -m unittest discover -s tests -v`：30 passed。
- `python3 -m py_compile prolific/ctc_verification_app/reconciliation.py`：passed。

## 限制

- 未使用真实凭据或生产 API；当前环境未配置可用的只读平台客户端，因此没有声称 live validation。调用方需提供实现 `list_submissions(study_id, cursor, page_size)` 的客户端，并将真实分页字段适配到该接口。
- 报告是只读预览，不执行 Ticket 3–8 的归档、释放、联系、webhook 或定时任务。

提交哈希：ac94f88（本地分支）。
