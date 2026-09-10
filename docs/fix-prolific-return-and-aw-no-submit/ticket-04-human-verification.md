> 历史核验材料：本文描述修订前的提交和规则，不是当前验收要求。2026-09-10 用户已重新确认业务规则及复核方式；以对应 issues/ 文档和 human-review-protocol.md 为准。当前修订实现仍在独立审查中。

# Ticket 04 — human verification pending

Reviewed commit `cf3792c`, workspace `/tmp/prolific-round-c-20260909/ticket-04`, independent task `01a0852b-94eb-7673-8d9d-c5502859bf0e`.

Both independent review axes passed. Root full suite: 83 passed; Spec reviewer independently ran 18 assignment tests. These results support the following isolated demonstration; they do not replace user verification or authorize production changes.

| Synthetic scenario | Observed result to verify |
| --- | --- |
| S1 times out without final answer | Its claim is released and replacement S2 can receive capacity |
| S1 times out with a final answer | Answer preserved, manual review, no RETURNED archive |
| Old S1 assigns/submits/saves draft after release | Rejected; cannot consume capacity again |
| Process interrupts before/after claim removal, then new participant arrives | Recovery completes once without revisiting S1 page |
| Repeated timeout has wrong participant/study | Manual review; original assignment/lifecycle bytes unchanged |
| Timeout manual conflict later receives RETURNED observation | Stays manual; no automatic conversion |

To inspect, resume the task with `codex resume 01a0852b-94eb-7673-8d9d-c5502859bf0e`, or run `python3 -m unittest tests.test_ctc_verification_assignment -v` in its workspace. Use only its synthetic temporary data; no real session or production allocation should be used for this demo.

Pending user decision: confirm the above behavior satisfies the desired timeout policy before code merge. This confirmation does not authorize production releases, migrations, messages or deployment. Ticket06 has a separate verification document; both tickets must complete the gate before starting Ticket08.
