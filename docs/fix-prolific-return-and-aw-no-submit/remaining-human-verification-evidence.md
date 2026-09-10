# 剩余人工核验：证据准备

版本 cc98597。2026-09-10 协调任务执行，均为隔离数据与本地模拟 HTTP API，未联系真实参与者。尚未获得用户对此文档各项的人工通过；当前问答仍停在缺失结果复查。

## 防重复发送与异常转人工

命令：`python3 -m unittest tests.test_ticket_08_authentic_recovery -q`，1项通过。

实际链路：签名事件进入接收器→首次发现无结果→测试时钟推进10分钟→本地API收到消息POST后断开连接→发送结果记为 delivery_unknown→销毁接收器并从磁盘重建触发器、控制器、账本、数据存储→调度复查。

断开前后累计POST始终为1。重建后状态 manual_review，send_outcome=unknown。该证据证明不因响应丢失而再次发信，不能证明对方已阅读或实际平台已送达。

## 处理中停用

命令：`python3 tests/ticket08_concurrent_disable_fixture.py`，退出0。

第一条消息已开始发送时，由独立进程停用后续动作。实际输出POST只有给合成参与者PS1的一条；PS2为actions_disabled，未发送第二条；S3_assignment_preserved=true，scheduler_error=null。第一条进行中的请求允许完成，停用不声称撤销已发送消息。旧接收/审批记录不等于授权新动作。

该案例与既有 CLI 重启停用证据互补。人工批准仍待用户逐项确认，未部署或合并Ticket8。
