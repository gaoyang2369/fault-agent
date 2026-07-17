# Task 4 领域模型与公共契约

## 1. 公共契约与源数据模型

公共 HTTP API、未来的 Agent Tool 和诊断模块只使用 `asset_id` 或 `asset_code`。公共查询模型是
`TelemetryQueryCommand`，公共返回模型是 `TelemetryQueryResult`；二者都不包含源表的
`device_name`、`inverter_name`、表名、连接信息或 SQL。

`device_name` 和 `inverter_name` 属于只读 `real_data` 适配器的定位信息，只存在于
Infrastructure 层的 `RealDataSourceLocator`。调用链为：

```text
HTTP Controller / Agent Tool
→ TelemetryQueryCommand
→ TelemetryQueryService
→ AssetSourceResolver
→ RealDataSourceLocator
→ RealDataRepository
```

身份、角色和请求来源由可信边界构造 `RequestContext` 后注入，不从查询命令读取。Task 4
只定义该上下文和授权 Port；游客一小时等具体策略留给 Task 5。

## 2. 为什么公共请求使用资产标识

源名称是遗留存储的定位细节，可能改变、重复或与领域部件边界不一致。稳定资产标识使 API、
诊断结果和 Evidence 不依赖某张表的字段命名，也防止调用方绕过资产解析和授权。

`asset_code` 适合用户输入和 Fixture；Application 层将其解析为稳定 `asset_id`，后续公共结果只
携带 `asset_id`。

## 3. G120-1 到源数据的映射

`G120-1` 被建模为 `DriveSystem`，包含独立的 `INVERTER` 和 `MOTOR` Component。当前
`InMemoryAssetRepository.g120_fixture()` 显式配置：

```text
G120-1 → asset-g120-1 → RealDataSourceLocator("G120电机1", "G120电机1")
```

该映射来自 2026-07-16 数据摸底观测，只是开发 Fixture，不是已确认的现场资产身份。代码中以
`TODO-DOMAIN` 标记。

## 4. 观测、事件、异常、假设和确认故障

- `Observation`：某个源记录在某时刻提供的信号值，是数据事实。
- `ReportedEvent`：设备直接上报的故障、报警或状态变化；上报码不等于根因。
- `Anomaly`：已配置且带版本的规则对数据作出的异常判定。
- `Hypothesis`：可验证的候选解释，可同时包含支持证据、矛盾证据和未验证条件；`score` 可空，
  且不表示最终故障概率。
- `ConfirmedFault`：经认证人员通过检查、维修结果或厂家诊断确认的故障。Task 4 只定义模型，
  不提供创建接口，Agent/LLM 不能创建。

## 5. Evidence 与 Claim

Evidence 是可独立解释的历史快照，保存来源引用、内容哈希、时间范围和受控 payload。payload
使用明确的判别联合，禁止未校验的任意 `dict[str, Any]`。历史 Evidence 不要求当前源记录仍然
存在才能解释。

Material Claim 默认至少引用一条支持 Evidence。证据不足时必须显式设置
`evidence_status=INSUFFICIENT`，不能用空证据列表表达正常结论。

## 6. 数据质量门控

`allowed_analyses` 使用稳定枚举。`INSUFFICIENT` 不允许趋势或持续时间规则；存在数据大间隔时
不允许持续时间规则。完整率、名义采样周期和间隔阈值仍由运行配置注入，它们是软件数据质量
策略，不是工业设备阈值。

## 7. TODO-DOMAIN

- 确认 `G120-1` 与源值 `G120电机1` 的正式映射及变更管理方式。
- 确认具体 G120 变体、控制单元、功率模块和固件。
- 确认电机型号、铭牌和温度传感器信息。
- 确认全部数值字段的单位和缩放；确认前单位保持 `null`，相关诊断禁用。
- 确认 `fault_code`、`alarm_code` 的无事件值和产品/固件语义。
- 确认 `status`、`control_word`、`status_word` 编码。
- 确认 `date + time` 与 `create_time` 的时区、语义及其与 `observed_at` 的有界偏差。
- 获得经工程师确认的健康基线和经批准的工业规则配置。

## 8. 临时兼容层

Task 3.1 的 `modules.telemetry.models.TelemetryQuery`、旧 `TelemetryQueryService` 和旧结果类型暂时
保留，供既有查询回归测试及内部适配使用。它们是 deprecated 兼容层；新的 API/Application
代码只能导入 `modules.telemetry.application` 下的 Command、Result 和 Service。计划在完成调用方
迁移并加入 Task 5 权限策略后删除旧公共导出。
