# 领域术语表

| 术语 | 定义 |
|---|---|
| DriveSystem | 变频器、电机及其控制关系组成的驱动系统 |
| Inverter | 变频器。当前系列为 SINAMICS G120，具体型号待确认 |
| Motor | 被驱动电机，型号和铭牌待确认 |
| Observation | 某时间点采集到的字段或信号值 |
| TelemetryFrame | 同一时间点的一组运行字段 |
| DataQuality | 数据是否完整、及时、可解析、可用于特定分析 |
| ReportedEvent | 设备状态、故障码或报警码直接上报的事件 |
| FaultCode | 设备上报的故障标识，需要按具体产品和固件解释 |
| AlarmCode | 设备上报的报警标识，通常表示警告状态，不自动等同于停机故障 |
| Anomaly | 运行数据不符合已配置规则或健康基线 |
| Hypothesis | 对异常原因的可验证候选解释 |
| ConfirmedFault | 经过人工检查、维修结果或制造商诊断确认的故障 |
| Claim | 系统输出的一条结构化结论 |
| Evidence | 支持或反驳 Claim 的数据、规则命中、故障码、文档片段或人工观察 |
| Recommendation | 下一步检查或处理建议，不代表已执行 |
| DiagnosisRun | 一次可追踪、可复现的诊断运行 |
| AgentRun | 一次用户请求对应的 Agent 编排运行 |
| RuleProfile | 一组适用于特定资产和版本的可配置规则 |
| KnowledgeSnapshot | 诊断时所使用知识库的固定版本 |
| ReportSnapshot | 报告生成时冻结的结构化数据 |
| Reported fault | 设备明确上报故障码 |
| Root cause | 导致故障现象的实际原因，通常需要额外检查确认 |

## 禁止混用

- `fault_code != null` 不等于根因已确认；
- `Anomaly` 不等于 `ConfirmedFault`；
- `severity` 不等于 `confidence`；
- `confidence` 不等于数据质量；
- 管理员不等于可以跳过审计；
- LLM 解释不等于诊断证据。
