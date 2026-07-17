# `real_data` 源数据契约

## 1. 数据源定位

`dcma.real_data` 是 M0/M1 的模拟历史运行数据源。应用只读访问，不直接修改源记录。2026-07-16 的只读摸底覆盖该表全部 566 条记录，完整结果见 `12_data_profile_findings.md` 和仓库根目录的 `real_data_profile.json` / `real_data_profile.md`。

## 2. 原始字段分类

### 标识和时间

| 字段 | 类型 | M0 用途 | 风险 |
|---|---|---|---|
| id | bigint | 源记录 ID | 不能作为业务资产 ID |
| timestamp | varchar | 首选采集时间 | 已观测为 13 位 Unix 毫秒时间戳；566/566 可解析 |
| date | varchar | 采集日期回退候选 | 已观测格式 `YYYY/MM/DD` |
| time | varchar | 采集时间回退候选 | 已观测格式 `HH:mm:ss SSSms`；本地时区仍待确认 |
| create_time | datetime | 数据入库时间 | 不一定是采集时间 |
| device_name | varchar | 电机/设备名称候选 | 样本唯一值 `G120电机1`；与 `G120-1` 映射待确认 |
| inverter_name | varchar | 变频器名称候选 | 样本唯一值 `G120电机1`；与资产/部件映射待确认 |

### 状态和事件

| 字段 | M0 用途 | 启用条件 |
|---|---|---|
| status | 状态变化和运行阶段 | 已观测 `0`、`45`、`42`、`31`；语义确认后 |
| fault_code | 设备上报故障事件 | 已观测 `0`、`F1030-0/0/0`；无事件值和产品/固件语义确认后 |
| alarm_code | 设备上报报警事件 | 已观测全为 `0`；无事件值确认后 |
| control_word | 控制状态参考 | 明确编码/位定义后 |
| status_word | 状态位解析 | 明确报文类型和位定义后 |
| system_run_time | 累计运行时间 | 明确格式和单位后 |

### 电气、机械和控制量

| 字段 | 推测语义 | 单位状态 |
|---|---|---|
| dc_voltage | 直流母线电压 | TODO |
| speed_setpoint | 速度设定 | TODO |
| speed_actual | 实际速度 | TODO |
| current_actual | 实际电流 | TODO |
| torque_setpoint | 转矩设定 | TODO |
| torque_actual | 实际转矩 | TODO |
| actual_power | 实际功率 | TODO |
| field_current | 励磁/磁场电流 | TODO |
| torque_current | 转矩电流分量 | TODO |
| motor_power | 电机功率 | TODO |
| feedback_power | 反馈功率 | TODO |
| pulse_frequency | 脉冲/开关频率 | TODO |

### 温度和负载

| 字段 | 推测语义 | 单位状态 |
|---|---|---|
| air_intake_temp | 进风温度 | 推测 °C，待确认 |
| motor_temp | 电机温度 | 推测 °C，待确认传感器/模型 |
| inverter_temp | 变频器温度 | 推测 °C，待确认具体测点 |
| inverter_radiator_temp | 散热器温度 | 推测 °C，待确认 |
| inverter_load_rate | 变频器负载率 | 推测 %，待确认 |
| motor_load_rate | 电机负载率 | 推测 %，待确认 |

## 3. 时间归一化规则

生成统一字段：

```text
observed_at: TIMESTAMP WITH TIME ZONE
ingested_at: TIMESTAMP WITH TIME ZONE
```

优先级：

1. 将 13 位 `timestamp` 按 Unix 毫秒时间戳解析为 UTC 时间点；
2. 失败时按已观测格式解析 `date + time`；该回退路径必须使用配置的 `SOURCE_TIMEZONE`；
3. 两者都存在且相差超过允许误差时，标记 `TIMESTAMP_CONFLICT`；
4. `create_time` 只作为入库时间；
5. Unix 时间戳本身表示 UTC 时间点；`date + time` 和无时区的 `create_time` 仍须通过配置 `SOURCE_TIMEZONE` 解释，不能由 LLM 决定。

## 4. 数据去重

推荐唯一候选键：

```text
(device_name, inverter_name, observed_at)
```

若同一候选键存在多条：

- 优先保留 `create_time` 最新记录；
- 保留重复计数；
- 标记 `DUPLICATE_SOURCE_RECORD`；
- 不删除源表数据。

## 5. 采样质量

暂定：

```yaml
nominal_interval_seconds: 3
jitter_warning_seconds: 3
gap_warning_seconds: 9
```

数据完整率按查询窗口和名义 3 秒采样估算：

- `>= 95%`：`ACCEPTABLE`
- `80% - 95%`：`DEGRADED`
- `< 80%`：`INSUFFICIENT`，默认禁止趋势/持续时间类诊断

以上仅为软件分析策略，可配置，不是设备安全阈值。

## 6. 空值和编码摸底

必须对以下字段统计：

- NULL；
- 空字符串；
- `"0"`；
- `"0000"`；
- `"None"`；
- `"null"`；
- 其他占位符；
- 故障码前缀和位数；
- 报警码前缀和位数；
- status 枚举；
- control_word/status_word 的进制和长度。

当前样本中 `fault_code="0"` 出现 490 次，`fault_code="F1030-0/0/0"` 出现 76 次，`alarm_code="0"` 出现 566 次。`"0"` 只是候选无事件值，在设备配置或数据生成规范确认前不得直接固化为领域规则；`F1030-0/0/0` 只能先作为原始上报码保留，不得在缺少适用手册时扩写含义。

## 7. 宽表适配输出

领域服务推荐返回：

```json
{
  "observed_at": "2026-07-16T00:00:00Z",
  "asset_code": "G120-1",
  "values": {
    "motor_temp": {
      "value": 70.2,
      "unit": null,
      "quality": "GOOD"
    }
  },
  "reported": {
    "status": "RUNNING",
    "fault_code": null,
    "alarm_code": null
  }
}
```

单位未确认时必须返回 `null`，不能由 LLM猜测。

## 8. 第一批数据摸底输出

Codex/后端需要生成：

- 总记录数；
- 最早和最晚时间；
- 每个设备名和变频器名的记录数；
- 实际采样间隔分布；
- 所有字符串字段的 Top 值；
- 所有数值字段的 min/max/avg/stddev/分位数；
- 空值率；
- 重复时间戳；
- 时间解析失败率；
- 故障码和报警码分布；
- 温度、负载、速度和功率字段的明显异常范围。

该输出已由 `python -m tools.profile_real_data` 实现并于 2026-07-16 对 `dcma.real_data` 执行。当前快照结论见 `12_data_profile_findings.md`。
