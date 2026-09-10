# 沿用现有 submissions 的部署适配

状态：只读准备完成，未重启/部署/启用动作。用户授权先检查当前与新机制的衔接；历史归档与消息清单仍须在执行前确认。

## 已核实的实际配置

- 当前进程1335723，从/home/label/label_ctc运行CTC app，监听127.0.0.1:8002。现有代理配置为72.62.250.126:80→127.0.0.1:8002；这是读取配置，不是外部浏览器可达性证明。
- 数据目录：/home/label/label_ctc/prolific/ctc_verification_app/data_train_first100_prolific。
- 候选文件：/home/label/label_ctc/tables/ctc_verification_train_balanced_first100.jsonl；100个sample，bundle_size=1，redundancy=3，本地assignment_timeout_minutes=240。Prolific平台14分钟超时是另一层设置，不将240误改14。
- 295份submissions、59份drafts、31份excluded文件，连同assignments共386文件。events.json、contacts.json、approval.json尚不存在，不假定已接入事件或已有发信账本。
- 新控制器redundancy默认1，必须显式配置3；不改变既有完成链接。令牌/完成码不写仓库。

## 兼容性与当前清单证据

原数据复制到私有/tmp隔离目录后，以新VerificationStore、原100候选及1/3/240参数读取成功；原文件和复制文件hash一致，未改变生产文件，957条解析记录无错误。957是解析记录（含分配等），不是提交数。证据preflight-evidence.json。

真实API刷新研究专用列表：2952唯一session与meta.count一致，与上一完整对账逐一比较无新/丢失ID，无状态或participant变化。299AW、2593Returned、60TimedOut。前次逐条对账及六人专项复核仍可作为本次准备依据；执行前仍需新鲜复查。

历史重点清单：1Returned本地结果、1TimedOut本地结果拟分别归档；6AW缺失（5NOCODE、1正常完成码）仅为联系候选，不能直接发信。详单/tmp/prolific-ticket08-focus-actions.csv，归档方案不是删除，既有研究者测试及其他归档保持原处。零当前临时占用，不能把2651条释放预案说成可释放2651个名额。

## 部署顺序

1. 切换前复核正在运行进程及数据变化；创建持久私有备份并验证清单/hash。现有/tmp副本是兼容性演练，不当作唯一生产回退备份。
2. 标注服务仍绑定原数据目录、候选及1/3/240参数，保留实际完成URL；使用已审查代码启动。不得清空或重置assignments、submissions、drafts和历史归档。
3. 同步器首次配置明确activation_boundary（实际启用时刻），当前已有记录均按历史/未知来源处理。首次不得将旧记录伪装成NEW事件或开机自动发历史消息。新本地联系账本为空不代表平台从未聊过。
4. 先仅只读预览，核实研究者/workspace和聊天可见范围；先不设置执行批准，不传--execute。控制器初始化仍可能创建本地运行文件，因此只有部署时才在生产目录构造它，本次只在副本验证。
5. 配置真实HTTPS webhook接收入口、签名密钥、订阅去重与调度归属；现有HTTP标注入口不能作为已验证HTTPS webhook入口。不把未验证workspace_visibility设true，模板缺失值应阻止启动。
6. 展示刷新后的历史归档/联系名单，再按明确批准执行历史处理；新典型消息按照已确认规则及生产启用授权处理，不逐次重复业务规则批准。
7. 在真实浏览器检查标题之外的任务、说明、音频实际播放和失败提示；只读/预览阶段不冒用真实参与者创建新assignment。需要试做时使用明确的隔离验证入口/数据，生产验证方式在切换计划中列明。
8. 停用优先阻止后续同步动作。程序回退不自动恢复归档、不抹去发送账本，不撤回已发请求；恢复数据必须单独对照备份和实际新提交，不覆盖新答案。

## 尚待补齐的部署配置

实际HTTPS receiver URL/域名与证书、研究者/workspace消息覆盖证明、签名密钥和订阅现状、常驻进程管理及实际启用时刻。当前draft配置不包含密钥且缺必要已验证信息，故不可直接执行；这不是部署成功声明。
