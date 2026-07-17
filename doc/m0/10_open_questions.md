# 待确认问题

## P0：在启用真实故障码解释和阈值前必须确认

### 1. G120 精确配置

- 是 G120、G120C、G120P、G120X 还是其他变体？
- Control Unit 型号是什么？
- Power Module 型号是什么？
- 固件版本是什么？
- 使用的通信报文/Telegram 是什么？

原因：故障码、状态字、参数和可用功能可能依赖具体配置和固件。

### 2. 电机铭牌

- 厂家和型号；
- 额定功率；
- 额定电压；
- 额定电流；
- 额定速度；
- 额定转矩；
- 绝缘等级；
- 冷却方式；
- 温度传感器类型。

### 3. 数值字段单位和缩放

必须逐项确认：

```text
dc_voltage
speed_setpoint
speed_actual
current_actual
torque_setpoint
torque_actual
air_intake_temp
motor_temp
inverter_temp
actual_power
field_current
torque_current
inverter_radiator_temp
inverter_load_rate
motor_load_rate
pulse_frequency
motor_power
feedback_power
```

### 4. 状态字段编码

- 样本中 `fault_code` 仅有 `0`（490 条）和 `F1030-0/0/0`（76 条）；需确认 `0` 是否正式表示无故障；
- 样本中 `alarm_code` 566 条均为 `0`；需确认 `0` 是否正式表示无报警；
- 是否可能一次存在多个码？
- 样本中 `status` 有 `0`、`45`、`42`、`31`；各值语义仍待确认；
- `control_word` 样本值为 `5247`、`5246`、`5120`、`5182`；需确认编码进制和位定义；
- status_word 对应哪一种报文位定义？

### 5. 时间语义

- `timestamp` 已确认为样本中的 13 位 Unix 毫秒时间戳，566/566 可解析为 UTC 时间点；
- `date` 已观测为 `YYYY/MM/DD`，`time` 已观测为 `HH:mm:ss SSSms`；
- `date + time` 的源时区仍待确认；
- `date + time`、`timestamp` 与 `create_time` 的正式语义关系仍待确认；
- `create_time` 是否为入库时间；
- 是否存在跨日、夏令时或设备时钟漂移。

## P1：在建立行为异常和健康基线前确认

### 6. 正常数据窗口

至少提供一段由工程师确认的健康运行区间，用于：

- 正常温升；
- 正常负载；
- 正常速度误差；
- 正常启动/停机过程；
- 正常采样抖动。

### 7. 模拟数据生成逻辑

- 是否人为注入了故障？
- 哪些字段受故障影响？
- 是否存在标签或事件清单？
- 模拟值是否遵循真实单位和物理关系？

### 8. 工况

G120-1 驱动的负载是什么？

- 泵；
- 风机；
- 输送；
- 其他机械。

工况会影响速度、转矩、功率和诊断逻辑。

## P2：不阻塞骨架开发

- 简版报告模板样式；
- 是否需要 PDF；
- 知识文档审批流程；
- 管理员是否可编辑规则；
- 工程师确认故障后是否需要生成维修记录；
- 数据保留周期。

## 建议处理方式

当前无需等待这些答案才能开始 M1。开发时：

- 所有未知单位标记为 `null`；
- 所有未确认阈值规则 `enabled: false`；
- 状态字和控制字仅展示原值；
- 故障码只在编码摸底和手册版本确认后解释；
- 使用 Fixture 测试代替真实工业结论。
