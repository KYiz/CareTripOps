# CareTrip Ops V4.0 增量审计（2026-10-09）

## 结论与范围

本次审计针对源码与可运行的本地静态检查。唯一确认并修复的 P0 是 Case ID 越权访问：此前任何取得 Case ID 的人都能读取需求、报价、审批 nonce、订单和审计记录，并可提交澄清、审批或恢复。新增随机 Case access token、服务端哈希、HTTP 路由检查和 Live Guide WebSocket 检查。`0004_case_access` 迁移后创建的新 Case 才有 token；旧 Case 没有可恢复的 token，应新建 Case。该 token 是浏览器持有的 demo capability，不是用户身份认证或细粒度授权。

**当前模拟闭环的判断：源码具备有条件完成能力，但本次不能确认“可靠跑通”。** 固定 Auckland 三人三天、NZD 预算的路径有需求、报价、核验、授权、模拟订单及回读；本次无法运行 PostgreSQL 集成测试、容器或浏览器端到端测试。非 Auckland 目的地只有示意行程，不具备可执行的模拟供应商闭环。

## 已实现并测试通过

- Case token 的前端 TypeScript 类型检查通过；前端现有 6 个路由与照片测试通过；Python 应用与迁移文件 `compileall` 通过。这些检查只证明静态和局部行为，不证明数据库或浏览器流程。
- 现有代码中，审批记录绑定 Case、Offer ID/版本、金额、币种和 Case 状态版本；决策比较报价到期时间与 PASS assessment。订单使用唯一 idempotency key 和 approval 唯一约束，执行后回读。此前的数据库测试覆盖重复审批、冲突报价和重复模拟预订，但其结果不适用于本次新代码。

## 已实现但未验证

- LangGraph 使用 `thread_id=case_id`，澄清和审批在 checkpoint interrupt；恢复入口要求 `RECOVERY_REQUIRED`。服务仅配置一个 Uvicorn worker，进程内任务表按 Case 去重。当前版本尚未对数据库与 checkpoint 故障、并发恢复或多进程部署做故障注入。
- Evidence Worker 计算 PASS/REVIEW/BLOCK，Manager 对不通过候选进行一次 rerank，审批与预订技能再次要求 PASS。规则基于合成证据；没有真实供应商真实性保证。
- Case token 检查及新增越权集成测试已写入源码，但未在迁移后的 PostgreSQL 上执行。Live Guide 的 token WebSocket 握手与语音服务也未实测。
- Dashboard 展示报价、证据、Agent 事件和模拟订单；Mobile 展示最终 PASS 报价、分开的方案复核/执行确认和订单结果。运行时显示尚未重新验收。

## 部分实现

- **授权执行：** 审批与预订的服务端门禁较完整，但方案确认主要是前端交互，没有独立、持久化的“方案已确认”记录。审批记录没有单独的 `expires_at` 列，靠不可变报价的到期时间校验。Case token 无用户身份、共享、撤销或权限范围；本次不建立完整账户系统。
- **可靠执行：** Gemini requirements 使用同步 SDK 调用，但位于 LangGraph 同步节点中；双模型规划使用异步 SDK、30 秒超时，语音澄清的同步提取放到 `asyncio.to_thread`。若干 `async def` API/Guide 路径直接进行同步 SQLAlchemy 操作，会短时间占用事件循环。连接池只使用 SQLAlchemy 默认参数和 `pool_pre_ping`，未按部署并发数进行容量验证。每 Case 模型调用次数、Live session 次数有上限，但没有全局 API 并发限制。
- **恢复：** 同一 Case 的数据库写入多处有行锁；审批幂等与订单唯一约束可处理常见重试。业务数据库提交与 LangGraph checkpoint 不是一个原子事务；跨故障边界不能声明 exactly once。
- **前端状态：** My Trips 仅列出该浏览器保存的 Case ID；token 新增后同一浏览器的新 Case 可访问。旧链接或其他浏览器只有 Case ID 会被拒绝。Live Guide 是 Case 相关的建议与示意行程修订，不是实时 GPS、供应商订单管理或已核实的行中信息。

## 尚未实现

- Traveller Profile、可分配的 Agent Permissions、Privacy Settings 与用户身份体系；暂不应在 UI 中声称它们可用。若做最小下一步，可先定义身份主体与 Case owner、只读/可审批/可执行权限、可撤销授权记录及数据保留选择，再接入前端权限入口。没有这些服务端对象时，单独做权限开关会造成误导。
- 真实供应商 API adapter 与统一的报价/可用性契约；当前 `search_suppliers` 和 `verify_evidence` 直接读取固定目录。可保留 Worker/Manager/审批技能边界，在发现与核验处引入 adapter，但需重新评估供应商事实、报价有效期和错误语义。
- 真实库存、预订、付款、取消、退款、改签、订单对账、实时行中事件与人工接管。

## 未来商业版本所需

- 账户认证、监护/代理关系与授权范围；把授权绑定旅行者、Case、供应商、报价快照、金额/币种、期限、具体动作，支持撤销、审计和敏感资料最小化。
- 供应商合同与 API adapter、可信来源和更新时间、库存锁定、报价重验、真实预订幂等键、异步确认/失败补偿、订单对账与客服升级。
- 明确的 PII/健康偏好同意与保留策略；多实例可恢复执行、容量规划、全局模型/供应商限流、超时与重试策略、可观测性、真实环境的并发和故障测试。

## 本次验证限制与上线门槛

本机没有 pytest 或 Docker 可执行环境；Vite build 因 Windows `realpath EPERM` 中止。上线演示前必须运行 `alembic upgrade head`、当前源码的 PostgreSQL 集成测试（包含新越权用例）、前端构建，并在浏览器验证 Case 创建到模拟订单、拒绝路径、刷新恢复及 Live Guide。不得把 Mock Supplier 表述为实时旅游数据，也不能声称模型幻觉已被完全消除。
