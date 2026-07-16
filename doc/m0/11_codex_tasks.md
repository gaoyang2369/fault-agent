# 可直接交给 Codex 的任务

## 使用方式

Codex 适合在仓库中读取文档、创建文件、编写代码并运行测试。每个任务应单独提交，检查 diff 后再进入下一项。

---

## Task 1：建立仓库骨架

```text
阅读根目录 AGENTS.md 和 docs/m0 全部文件。

建立 Python 3.12 + FastAPI 项目骨架，采用模块化单体：
- apps/api
- apps/agent_worker
- modules/iam
- modules/asset
- modules/telemetry
- modules/knowledge
- modules/diagnosis
- modules/evidence
- modules/report
- modules/audit
- contracts
- tests

要求：
- 使用 pyproject.toml；
- 加入 ruff、mypy、pytest；
- 提供健康检查；
- 不实现 LLM；
- 不连接生产数据库；
- 不发明工业阈值；
- 运行全部检查并报告结果。
```

---

## Task 2：为 `real_data` 编写数据摸底工具

```text
根据 docs/m0/05_source_data_contract.md 和 sql/data_profile.sql，
实现一个只读 CLI：python -m tools.profile_real_data。

输入通过环境变量提供数据库 DSN。
输出 JSON 和 Markdown，包含：
- 表记录数；
- 时间字段解析率；
- 设备名/变频器名分布；
- 实际采样间隔分布；
- 字符串字段 Top 值；
- 数值字段空值率、最小、最大、均值、标准差和分位数；
- fault_code/alarm_code 分布；
- 重复记录；
- 可能的固定值/冻结字段。

安全要求：
- 只执行 SELECT；
- 不打印密码；
- 查询有超时；
- 默认限制样本量；
- 所有 SQL 参数化；
- 为解析和统计添加测试。
```

---

## Task 3：实现源数据适配器

```text
实现 modules/telemetry 的 RealDataRepository 和 TelemetryQueryService。

要求：
- 源表只读；
- 将 timestamp 或 date+time 转换为 observed_at；
- source timezone 必须配置；
- 返回数据质量告警；
- 支持按 device_name/inverter_name、时间范围查询；
- 支持 signals 白名单；
- 支持聚合和最大返回点数；
- 游客查询约束不要写在 Repository，放在权限/Application 层；
- 不允许原始 SQL 从 API 或 Agent 传入；
- 添加单元测试和集成测试。
```

---

## Task 4：实现领域模型和契约

```text
根据 docs/m0 定义 Pydantic v2 模型：
DriveSystem
Component
SignalDefinition
TimeRange
DataQuality
ReportedEvent
Anomaly
Evidence
Claim
Hypothesis
Recommendation
DiagnosisRequest
DiagnosisResult
ErrorResponse

要求：
- 禁止未知字段；
- 时间使用带时区 datetime；
- Observation、Anomaly、Hypothesis、ConfirmedFault 分开；
- ConfirmedFault 必须有 confirmed_by 和 confirmed_at；
- Hypothesis 至少需要一条支持证据，或明确 evidence_status=INSUFFICIENT；
- 生成 JSON Schema；
- 添加正反例测试。
```

---

## Task 5：实现权限骨架

```text
实现游客、工程师、管理员三类权限。

规则：
- 游客只能访问白名单资产、最近一小时、聚合数据；
- 工程师访问已分配资产，可诊断和生成报告；
- 管理员访问全部资产并管理知识；
- 所有 Tool 调用重新授权；
- 不信任请求中的 user_id、role、asset_scope；
- 添加越权和时间范围测试。
```

---

## Task 6：实现故障码归一化和知识接口

```text
先实现结构化接口和 Fixture，不抓取网络内容。

要求：
- FaultCodeEntry 带 product_variant、firmware_range、document_version、source_location；
- fault_code 原始值和规范化值都保留；
- 未映射代码返回 UNMAPPED_FAULT_CODE；
- 文档状态 DRAFT/PUBLISHED/RETIRED；
- 只有 PUBLISHED 进入默认检索；
- 添加版本冲突测试。
```

---

## Task 7：实现规则框架，不创建真实阈值

```text
实现 RuleProfile 和 RuleEngine 框架。

第一批只实现：
- 数据缺失；
- 采样间隔异常；
- 信号冻结；
- 通用持续条件执行器；
- fault_code/alarm_code 事件检测。

所有温度、负载、电流、速度误差规则用示例配置且 enabled=false。
规则命中必须生成 RuleHit Evidence。
不得让 LLM执行规则或计算置信度。
```

---

## Task 8：实现单 Agent 编排骨架

```text
实现一个 Orchestrator，不拆多个自由 Agent。

节点：
load_context
understand_request
select_plan_template
validate_plan
authorize_plan
execute_tasks
aggregate_results
verify_evidence
compose_answer

初期计划模板：
TELEMETRY_ONLY
FAULT_CODE_LOOKUP
BASIC_DIAGNOSIS
DIAGNOSIS_AND_REPORT

使用假的/可替换 LLM Adapter。
DAG 校验、权限、参数、规则和状态转换必须是确定性代码。
```

---

## Task 9：一致性审查

```text
只审查，不修改文件。

检查：
- 实现是否违反 AGENTS.md；
- Agent 是否直接访问数据库；
- 是否由 LLM决定权限、阈值、置信度或 ConfirmedFault；
- 所有关键 Claim 是否关联 Evidence；
- 游客一小时限制能否被复合请求绕过；
- 时间和单位是否存在隐式假设；
- API、JSON Schema 和测试是否一致；
- 状态机是否存在非法跳转。

按 Critical/High/Medium/Low 输出。
```

## Codex 不能完成的工作

Codex 可以帮助编码和检查，但不能替代以下信息：

- 真实设备和电机铭牌；
- 厂家适用手册；
- 故障码和状态字解释；
- 单位和缩放；
- 现场健康基线；
- 工业阈值批准；
- 最终故障确认。
