-- real_data 数据摸底模板
-- 注意：以下以 MySQL/MariaDB 方言为参考。
-- Codex/开发者应根据实际数据库版本调整。
-- 只允许 SELECT。

-- 1. 记录总量和入库时间范围
SELECT
    COUNT(*) AS row_count,
    MIN(create_time) AS min_create_time,
    MAX(create_time) AS max_create_time
FROM real_data;

-- 2. 设备/变频器分布
SELECT
    device_name,
    inverter_name,
    COUNT(*) AS row_count,
    MIN(create_time) AS min_create_time,
    MAX(create_time) AS max_create_time
FROM real_data
GROUP BY device_name, inverter_name
ORDER BY row_count DESC;

-- 3. 字符串字段取值分布
SELECT status, COUNT(*) AS cnt
FROM real_data
GROUP BY status
ORDER BY cnt DESC
LIMIT 100;

SELECT fault_code, COUNT(*) AS cnt
FROM real_data
GROUP BY fault_code
ORDER BY cnt DESC
LIMIT 200;

SELECT alarm_code, COUNT(*) AS cnt
FROM real_data
GROUP BY alarm_code
ORDER BY cnt DESC
LIMIT 200;

SELECT control_word, COUNT(*) AS cnt
FROM real_data
GROUP BY control_word
ORDER BY cnt DESC
LIMIT 100;

SELECT status_word, COUNT(*) AS cnt
FROM real_data
GROUP BY status_word
ORDER BY cnt DESC
LIMIT 100;

-- 4. 空值率
SELECT
    COUNT(*) AS total,
    SUM(timestamp IS NULL OR timestamp = '') AS timestamp_missing,
    SUM(fault_code IS NULL OR fault_code = '') AS fault_code_missing,
    SUM(alarm_code IS NULL OR alarm_code = '') AS alarm_code_missing,
    SUM(motor_temp IS NULL) AS motor_temp_missing,
    SUM(inverter_temp IS NULL) AS inverter_temp_missing,
    SUM(speed_actual IS NULL) AS speed_actual_missing
FROM real_data;

-- 5. 数值范围
SELECT
    MIN(dc_voltage) AS dc_voltage_min,
    MAX(dc_voltage) AS dc_voltage_max,
    AVG(dc_voltage) AS dc_voltage_avg,
    MIN(speed_actual) AS speed_actual_min,
    MAX(speed_actual) AS speed_actual_max,
    AVG(speed_actual) AS speed_actual_avg,
    MIN(current_actual) AS current_actual_min,
    MAX(current_actual) AS current_actual_max,
    AVG(current_actual) AS current_actual_avg,
    MIN(motor_temp) AS motor_temp_min,
    MAX(motor_temp) AS motor_temp_max,
    AVG(motor_temp) AS motor_temp_avg,
    MIN(inverter_temp) AS inverter_temp_min,
    MAX(inverter_temp) AS inverter_temp_max,
    AVG(inverter_temp) AS inverter_temp_avg,
    MIN(motor_load_rate) AS motor_load_rate_min,
    MAX(motor_load_rate) AS motor_load_rate_max,
    AVG(motor_load_rate) AS motor_load_rate_avg
FROM real_data;

-- 6. 重复候选记录
SELECT
    device_name,
    inverter_name,
    timestamp,
    COUNT(*) AS duplicate_count
FROM real_data
GROUP BY device_name, inverter_name, timestamp
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC
LIMIT 500;

-- 7. 原始时间格式样本
SELECT id, timestamp, date, time, create_time
FROM real_data
ORDER BY id
LIMIT 200;

-- 实际采样间隔、分位数和冻结信号建议使用 Python 数据摸底工具完成，
-- 因为 timestamp 当前为 varchar，且实际格式和时区未确认。
