# faultAgent

Python 3.12+、FastAPI 的模块化单体项目骨架。API 与 Agent worker 使用独立入口；当前阶段不包含 LLM、生产数据库连接、设备控制或工业阈值。

首次接触项目请先阅读 [项目快速上手](doc/项目快速上手.md)，其中包含当前完成度、架构、
核心查询链路、推荐阅读顺序和后续任务。

## 开发

```powershell
python -m pip install -e ".[dev]"
ruff format --check .
ruff check .
mypy
pytest
```

启动 API：

```powershell
uvicorn apps.api.main:app --reload
```

健康检查：`GET /health`。公开遥测查询：`POST /v1/telemetry/queries`；真实 IAM 接入前，HTTP
调用按游客策略限制为白名单资产、最长一小时和聚合数据。

## real_data 只读摸底

通过进程环境变量提供连接信息；不要提交真实 `.env`：

```powershell
$env:REAL_DATA_DSN = "mysql+pymysql://user:password@host:3306/database"
$env:REAL_DATA_TABLE = "real_data"
$env:REAL_DATA_QUERY_TIMEOUT_SECONDS = "15"
python -m tools.profile_real_data
```

默认最多读取 10,000 条样本，并输出 `real_data_profile.json` 和 `real_data_profile.md`。全表查询仅用于记录数、设备/变频器分布、字符串字段 Top 值及受限数量的重复候选；所有数据库语句均为内部定义的 `SELECT`，CLI 不接受原始 SQL 或任意表名。
