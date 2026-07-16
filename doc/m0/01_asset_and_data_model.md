# 资产与数据模型

## 1. 为什么不能直接建模为“G120 电机”

项目中的 `G120-1` 应被视为一个驱动系统别名，而不是准确的电机型号。驱动系统至少分为：

```text
DriveSystem: G120-1
├── Inverter
│   ├── Product family: SINAMICS G120
│   ├── Control Unit: TODO
│   ├── Power Module: TODO
│   └── Firmware: TODO
└── Motor
    ├── Manufacturer: TODO
    ├── Model: TODO
    ├── Rated power: TODO
    ├── Rated voltage: TODO
    ├── Rated current: TODO
    ├── Rated speed: TODO
    ├── Insulation class: TODO
    └── Temperature sensor: TODO
```

变频器故障、驱动系统异常和电机机械/电气根因需要分开表达。

## 2. 核心实体

### DriveSystem

```yaml
id: uuid
asset_code: G120-1
display_name: G120驱动系统1
asset_type: DRIVE_SYSTEM
status: ACTIVE
```

### Component

```yaml
id: uuid
asset_id: uuid
component_type: INVERTER | MOTOR
component_code: string
manufacturer: string
model: string
firmware_version: string|null
```

### SignalDefinition

```yaml
signal_code: motor_temp
display_name: 电机温度
source_column: motor_temp
component_type: MOTOR
data_type: float
unit: TODO
sampling_interval_seconds: 3
diagnostic_enabled: false
```

`diagnostic_enabled` 只有在单位、语义和合理范围确认后才可以置为 `true`。

### Observation

```yaml
source_record_id: bigint
asset_id: uuid
observed_at: timestamptz
signal_code: string
value: number|string
quality: GOOD | DEGRADED | BAD
source_table: real_data
```

第一版不必把宽表全部拆成长表持久化，但领域服务应将宽表转换为统一 Observation/TelemetryFrame。

### ReportedEvent

```yaml
event_type: FAULT | ALARM | STATUS_CHANGE
event_code: string
reported_at: timestamptz
source: DEVICE_REPORTED
manual_entry_id: string|null
```

### Anomaly

```yaml
anomaly_type: string
severity: INFO | LOW | MEDIUM | HIGH | CRITICAL
start_at: timestamptz
end_at: timestamptz
detection_rule_id: string
evidence_ids: [string]
```

### Hypothesis

```yaml
hypothesis_code: string
target_component: INVERTER | MOTOR | DRIVE_SYSTEM | UNKNOWN
score: number|null
supporting_evidence_ids: [string]
contradicting_evidence_ids: [string]
unverified_conditions: [string]
```

### ConfirmedFault

```yaml
confirmed_fault_code: string
confirmed_by: user_id
confirmed_at: timestamptz
confirmation_method: INSPECTION | REPAIR_RESULT | MANUFACTURER_DIAGNOSTIC
```

LLM 不能创建 `ConfirmedFault`。

## 3. 必须区分的三类结果

| 类型 | 含义 | 示例 |
|---|---|---|
| ReportedFaultEvent | 设备上报了一个故障码 | 变频器上报 Fxxxxx |
| Hypothesis | 系统依据数据和知识形成的原因假设 | 可能存在过载或冷却异常 |
| ConfirmedFault | 人工检查或维修结果确认 | 风扇损坏导致散热异常 |

## 4. 数据库建议

M0/M1 推荐分为：

- **源数据数据库**：现有 `real_data`，只读；
- **应用数据库**：用户、资产、诊断运行、Evidence、报告、知识元数据；
- **文档存储**：厂家手册原文件；
- **检索索引**：第一版可使用 PostgreSQL 全文检索和向量扩展。

源表不应承担 Agent 会话、权限和诊断证据存储。
