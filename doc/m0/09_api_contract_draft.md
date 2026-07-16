# 第一批 API 契约草案

## 1. 设计原则

- HTTP Controller、Agent Tool 共用 Application Service；
- Agent 不访问数据库；
- 查询和诊断接口分开；
- 长任务通过 Run ID 查询；
- 所有请求由后端注入用户上下文；
- 结构化结果与自然语言解释分开。

## 2. 资产

```http
GET /v1/me
GET /v1/assets
GET /v1/assets/{asset_id}
GET /v1/assets/{asset_id}/signals
```

## 3. 运行数据

```http
POST /v1/telemetry/queries
```

请求：

```json
{
  "asset_id": "G120-1",
  "time_range": {
    "start": "2026-07-16T00:00:00Z",
    "end": "2026-07-16T01:00:00Z"
  },
  "signals": [
    "speed_setpoint",
    "speed_actual",
    "motor_temp",
    "fault_code",
    "alarm_code"
  ],
  "aggregation": {
    "window_seconds": 60,
    "functions": ["min", "max", "avg"]
  }
}
```

后端必须根据角色重写/验证时间跨度和数据粒度。

## 4. 故障知识

```http
GET  /v1/fault-codes/{fault_code}
POST /v1/knowledge/search
POST /v1/knowledge/documents
POST /v1/knowledge/documents/{document_id}/publish
```

最后两个接口仅管理员。

## 5. 诊断

```http
POST /v1/diagnoses
GET  /v1/diagnoses/{diagnosis_id}
GET  /v1/diagnoses/{diagnosis_id}/evidence
POST /v1/diagnoses/{diagnosis_id}/review
```

诊断请求：

```json
{
  "asset_id": "G120-1",
  "time_range": {
    "start": "...",
    "end": "..."
  },
  "diagnosis_profile": "G120_DRIVE_BASIC",
  "include_report": false
}
```

工程师确认：

```json
{
  "decision": "CONFIRM | REJECT | NEED_MORE_DATA",
  "hypothesis_id": "hyp-001",
  "confirmed_fault_code": null,
  "comment": "..."
}
```

`confirmed_fault_code` 只能在 `CONFIRM` 时由有权限用户填写。

## 6. 报告

```http
POST /v1/reports
GET  /v1/reports/{report_id}
GET  /v1/reports/{report_id}/content
```

## 7. Agent

```http
POST /v1/agent/runs
GET  /v1/agent/runs/{run_id}
GET  /v1/agent/runs/{run_id}/events
POST /v1/agent/runs/{run_id}/messages
POST /v1/agent/runs/{run_id}/cancel
```

Agent 请求：

```json
{
  "message": "检查 G120-1 最近一小时，有故障的话解释并生成报告。",
  "conversation_id": null
}
```

Agent 返回结构：

```json
{
  "run_id": "run-001",
  "status": "RUNNING",
  "resolved_context": {
    "asset_id": "G120-1",
    "time_range": {
      "start": "...",
      "end": "..."
    }
  },
  "plan": {
    "template": "DIAGNOSIS_AND_REPORT",
    "tasks": []
  }
}
```

## 8. Agent Tools

第一批：

```text
list_assets
get_asset
get_signal_definitions
query_telemetry
profile_data_quality
detect_reported_events
lookup_fault_code
search_knowledge
create_diagnosis
get_diagnosis
get_evidence
generate_report
```

Tool 不应接受：

```text
user_id
role
allowed_asset_ids
database connection string
raw SQL
```

这些由 ToolContext 注入。

## 9. 报告输出

第一版优先生成：

- JSON ReportSnapshot；
- HTML；
- 可选 PDF。

结构化报告先于 LLM 描述。
