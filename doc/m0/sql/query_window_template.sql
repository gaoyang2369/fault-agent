-- 只读窗口查询模板。
-- 不要从 Agent 或 HTTP 请求接收任意列名。
-- 应由代码使用信号白名单构造 SELECT 列表。

SELECT
    id,
    timestamp,
    device_name,
    inverter_name,
    date,
    time,
    status,
    fault_code,
    alarm_code,
    control_word,
    status_word,
    dc_voltage,
    speed_setpoint,
    speed_actual,
    current_actual,
    torque_setpoint,
    torque_actual,
    air_intake_temp,
    motor_temp,
    inverter_temp,
    actual_power,
    field_current,
    torque_current,
    system_run_time,
    inverter_radiator_temp,
    inverter_load_rate,
    motor_load_rate,
    pulse_frequency,
    motor_power,
    feedback_power,
    create_time
FROM real_data
WHERE device_name = :device_name
  AND inverter_name = :inverter_name
  AND create_time >= :start_time
  AND create_time < :end_time
ORDER BY create_time ASC
LIMIT :max_rows;
