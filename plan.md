### M0：定义首个闭环场景

不要先覆盖所有功能，先选一个 Golden Path：

用户选择设备
  ↓
查询最近 24 小时运行数据
  ↓
识别数据异常
  ↓
检索相关故障知识
  ↓
生成候选故障
  ↓
展示证据
  ↓
生成诊断摘要

暂时不做：

自动控制设备。
自动写入工单。
多 Agent。
复杂机器学习模型。
完整报告编辑器。
复杂知识图谱。

交付物
use-cases.md
首个场景时序图
输入输出样例
异常场景列表
验收数据集
验收条件

同一固定输入能够重复得到结构一致、证据可追溯的诊断结果。

### M1：冻结核心领域模型

优先定义：

Tenant
User
Role
Asset
Component
SignalDefinition
TelemetryPoint
Alarm
FaultCode
DiagnosticRun
DiagnosticTask
Hypothesis
Evidence
Claim
Recommendation
AgentRun
AgentTask
PolicyDecision
AuditEvent
Report

重点先冻结以下关系：

Asset 1 ── N SignalDefinition
Asset 1 ── N DiagnosticRun
DiagnosticRun 1 ── N Hypothesis
Hypothesis N ── N Evidence
Claim N ── N Evidence
AgentRun 1 ── N AgentTask
状态机

DiagnosticRun：

CREATED
  ↓
DATA_PREPARING
  ↓
ANALYZING
  ↓
COMPLETED
  ├── FAILED
  ├── CANCELLED
  └── WAITING_APPROVAL

AgentRun：

RECEIVED
  ↓
UNDERSTANDING
  ↓
PLANNED
  ↓
AUTHORIZED
  ↓
RUNNING
  ↓
COMPOSING
  ↓
COMPLETED

分支：
WAITING_INPUT
WAITING_APPROVAL
PARTIALLY_COMPLETED
FAILED
CANCELLED
验收条件

所有状态变更都有明确允许的前置状态，不能任意更新状态字段。

### M2：建立接口契约仓库

定义第一批 JSON Schema：

Asset
TimeRange
TelemetryQuery
TelemetryResult
KnowledgeSearch
KnowledgeSearchResult
CreateDiagnosis
DiagnosisResult
Evidence
Claim
ExecutionPlan
AgentTask
AgentRun
ErrorResponse

定义第一批 OpenAPI：

GET  /v1/assets
GET  /v1/assets/{asset_id}
GET  /v1/assets/{asset_id}/signals

POST /v1/telemetry/queries

POST /v1/knowledge/search
GET  /v1/fault-codes/{fault_code}

POST /v1/diagnoses
GET  /v1/diagnoses/{diagnosis_id}

POST /v1/agent/runs
GET  /v1/agent/runs/{run_id}
GET  /v1/agent/runs/{run_id}/events
POST /v1/agent/runs/{run_id}/messages

GET /agent/runs/{id}/events 可以使用 SSE 返回：

run.created
plan.created
task.started
task.completed
evidence.created
answer.delta
run.completed
验收条件
OpenAPI 能通过规范校验。
DTO 能由 Schema 生成或验证。
Mock Server 能在后端未实现时返回标准样例。
前端、Agent 和测试共用同一份 Schema。
### M3：搭建工程底座

建立：

配置管理
数据库迁移
统一错误码
统一响应结构
结构化日志
Trace ID
Request ID
健康检查
就绪检查
Docker Compose
CI
单元测试
集成测试

统一错误结构：

{
  "error": {
    "code": "ASSET_NOT_FOUND",
    "message": "指定设备不存在",
    "details": {
      "asset_id": "pump-01"
    },
    "trace_id": "trace-001",
    "retryable": false
  }
}

从第一天就接入 Trace ID。OpenTelemetry 可以使用同一个执行上下文关联 Trace、日志和指标，适合追踪一次 Agent 请求经过 Planner、Tool Gateway 和领域服务的完整路径。

### M4：实现身份、资产和权限底座

先完成：

用户身份
租户
角色
资产组
用户与资产范围关系
数据敏感级别
操作权限
授权决策记录

第一版权限模型：

角色权限
+
租户范围
+
资产范围
+
操作类型
+
数据级别

接口调用过程：

用户请求
  ↓
认证
  ↓
解析 tenant_id 和 user_id
  ↓
检查 action
  ↓
检查 asset_scope
  ↓
生成 policy_decision_id
  ↓
业务执行
验收测试
游客不能查看真实运行数据
工程师只能查看分配资产
管理员不能跨租户访问
Agent 不能扩大用户资产范围
未授权 Tool 不暴露给模型
每次授权都有 decision_id
### M5：实现资产与运行数据服务

先支持：

资产查询
测点定义查询
时间范围查询
聚合
降采样
数据质量统计
缺失值统计
异常时间段标记

不要让 Agent 生成 SQL。Agent 只生成 TelemetryQuery：

{
  "asset_id": "pump-01",
  "signal_codes": [
    "vibration_rms",
    "bearing_temperature"
  ],
  "time_range": {
    "start": "2026-07-14T00:00:00Z",
    "end": "2026-07-15T00:00:00Z"
  },
  "aggregation": {
    "window": "5m",
    "functions": ["avg", "max"]
  }
}
验收条件
相同查询参数返回可重复结果。
结果包含单位、采样间隔、数据质量。
超大时间范围被拒绝或自动降采样。
未授权资产查询被拒绝。
返回结果可以直接用于图表展示。
### M6：实现知识和故障码服务

先将两类数据分开：

结构化故障码
fault_code
设备型号
故障名称
严重度
可能原因
推荐检查
适用版本

使用精确查询。

非结构化知识
设备手册
维修 SOP
故障分析文档
历史案例

使用：

元数据过滤
+ 关键词检索
+ 向量检索
+ 重排序

每条结果必须返回：

document_id
document_version
chunk_id
page
section
content_hash
score
验收条件
精确故障码优先走结构化数据库。
文档搜索可以限制设备型号和版本。
每个回答片段都能回溯到原文位置。
失效版本文档不会进入默认结果。
### M7：实现诊断服务骨架

第一版不需要复杂 ML，先实现：

数据质量检查
阈值规则
趋势规则
告警映射
故障码映射
知识案例匹配
候选故障排序

诊断流水线：

Prepare Data
  ↓
Validate Quality
  ↓
Identify Operating Condition
  ↓
Extract Features
  ↓
Execute Rules
  ↓
Retrieve Related Knowledge
  ↓
Generate Hypotheses
  ↓
Bind Evidence
  ↓
Generate Recommendations

第一版的规则可以是：

rule_id: bearing_temperature_high
version: 1.0.0
conditions:
  - signal: bearing_temperature
    operator: gt
    value: 85
    duration: 10m
output:
  hypothesis: BEARING_OVERHEATING
  score: 0.65
  severity: HIGH
验收条件
相同数据、规则版本得到相同结果。
每个 Hypothesis 至少有一条 Evidence。
结果包含支持证据和矛盾证据。
诊断结果保存规则版本和知识版本。
LLM 没有参与置信度计算。
### M8：实现 Evidence 与 Claim

所有工具返回统一包含：

{
  "data": {},
  "evidence_refs": [
    "evidence-001"
  ],
  "warnings": [],
  "data_quality": {},
  "trace_id": "trace-001"
}

Evidence 类型：

TELEMETRY_SLICE
FEATURE_VALUE
ALARM_EVENT
FAULT_CODE
RULE_HIT
MODEL_INFERENCE
DOCUMENT_CHUNK
HISTORICAL_CASE
USER_OBSERVATION
MAINTENANCE_RECORD

Claim 示例：

{
  "claim_id": "claim-001",
  "claim_type": "FAULT_HYPOTHESIS",
  "statement_code": "BEARING_OVERHEATING",
  "supporting_evidence_ids": [
    "evidence-001",
    "evidence-002"
  ],
  "contradicting_evidence_ids": [],
  "generated_by": {
    "pipeline_version": "1.0.0",
    "rule_set_version": "2026-07"
  }
}
验收条件
最终答案中的关键结论必须对应 Claim。
Claim 必须关联 Evidence。
Evidence 必须记录来源、时间范围和版本。
删除知识文档不能破坏历史诊断证据。
### M9：实现 Tool Gateway

第一版 Tool Gateway 可以是后端中的统一调用组件：

Tool Registry
Tool Schema Validator
Authorization Interceptor
Idempotency Interceptor
Audit Interceptor
Evidence Binder
Error Normalizer

工具接口：

class Tool:
    name: str
    version: str
    input_schema: dict
    output_schema: dict

    async def invoke(
        self,
        context: ToolContext,
        payload: dict
    ) -> ToolResult:
        ...

ToolContext 至少包括：

{
  "request_id": "req-001",
  "run_id": "run-001",
  "task_id": "task-001",
  "trace_id": "trace-001",
  "user_id": "user-001",
  "tenant_id": "tenant-a",
  "allowed_asset_ids": ["pump-01"],
  "purpose": "interactive_diagnosis"
}
验收条件
Tool 参数严格验证。
每次调用重新鉴权。
Tool 不接受模型传入的 user_id 和 tenant_id。
Tool 返回统一错误结构。
每个 ToolCall 都有审计记录。
### M10：实现 Agent Orchestrator

此时再接 LLM。

Agent 图建议包含：

load_context
  ↓
understand_request
  ↓
build_plan
  ↓
validate_plan
  ↓
authorize_plan
  ↓
execute_ready_tasks
  ↓
update_task_graph
  ↓
aggregate_results
  ↓
verify_evidence
  ↓
compose_answer
  ↓
finalize_run

共享状态：

class AgentState:
    run_id: str
    messages: list
    user_context: UserContext
    conversation_context: ConversationContext

    request_understanding: RequestUnderstanding | None
    execution_plan: ExecutionPlan | None

    tasks: dict[str, AgentTask]
    task_results: dict[str, ToolResult]

    evidence_ids: list[str]
    claim_ids: list[str]

    warnings: list[str]
    final_answer: str | None
LLM 使用位置
请求理解
任务拆解
缺失参数识别
低风险的计划选择
知识结果摘要
诊断结果解释
最终答案组织
非 LLM 位置
DAG 校验
权限检查
参数验证
时序计算
规则执行
诊断评分
证据绑定
状态变更
审计
验收条件
模型输出格式错误时能自动重试或失败降级。
Planner 生成非法任务时会被 Validator 拦截。
单次运行有最大步骤数和最大 Tool 调用数。
同一请求可以取消。
Agent 进程重启后能恢复运行状态。
Agent 不能访问未注册工具。

如果流程只持续数秒到数分钟，第一版可以使用 LangGraph 或自研状态机；当流程跨越较长时间、需要审批等待、崩溃恢复和可靠重试时，再在外层增加 Temporal。Temporal 的 Workflow Execution 会持久保存进度，并在失败后恢复。

### M11：实现复合意图 Planner 和 DAG Executor

实现顺序：

单任务
  ↓
多个无依赖并行任务
  ↓
串行依赖任务
  ↓
条件任务
  ↓
部分失败
  ↓
人工审批
  ↓
暂停和恢复

第一版不要让 LLM 随意生成任意图，可以只允许几个计划模板：

DATA_ONLY
KNOWLEDGE_ONLY
DIAGNOSIS
DATA_AND_KNOWLEDGE
DATA_DIAGNOSIS
DIAGNOSIS_AND_REPORT
FULL_ANALYSIS_REPORT

LLM 负责选择模板并填充参数，代码负责生成实际 DAG。

当评测数据足够后，再开放自由任务拆解。

验收条件
DAG 无循环。
并行度受限。
依赖失败时下游任务自动 BLOCKED。
独立任务可以继续执行。
重试不会重复创建诊断或报告。
计划和实际执行结果可以完整回放。
### M12：实现答案生成

答案生成器只接收结构化信息：

用户原始问题
任务执行摘要
TelemetrySummary
KnowledgeResult
DiagnosisResult
Claim 列表
Evidence 列表
Warnings

不直接接收：

数据库连接
全部原始高频数据
未经清洗的所有日志
系统密钥
未授权工具
其他租户上下文

回答结构建议固定：

结论
运行数据概览
异常发现
候选故障
证据
仍需确认的信息
建议检查项
任务执行状态
验收条件
回答中出现的数值必须存在于 Tool Result。
回答中的故障结论必须关联 Claim。
无证据时明确写“证据不足”。
不允许模型虚构已执行的检查。
### M13：实现报告服务

先做固定模板：

设备基本信息
报告时间范围
运行概览
关键指标
告警统计
诊断结果
证据与引用
建议
审批信息
版本信息

流程：

创建 Report Snapshot
  ↓
收集结构化数据
  ↓
生成描述段落
  ↓
数值一致性校验
  ↓
渲染 HTML
  ↓
导出 PDF
  ↓
计算内容 Hash
  ↓
归档
验收条件
报告内容来自固定快照。
报告生成后数据变化不会修改历史报告。
报告保存模板版本、模型版本和知识版本。
正式报告发布需要审批。
### M14：评测、安全和上线准备

建立固定评测集：

单意图请求
多意图请求
省略资产的请求
省略时间范围的请求
上下文继承请求
无权限请求
跨租户请求
错误故障码
无数据请求
数据质量较差请求
Prompt Injection
知识库间接注入
Tool 参数攻击
部分任务失败

核心指标：

意图识别准确率
任务拆解准确率
DAG 依赖准确率
Tool 选择准确率
参数抽取准确率
越权拦截率
故障码精确命中率
诊断 Top-K 命中率
结论证据覆盖率
无依据回答率
平均 Tool 调用次数
平均运行耗时
部分失败恢复率