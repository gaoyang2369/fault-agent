# faultAgent

Python 3.12+、FastAPI 的模块化单体项目骨架。API 与 Agent worker 使用独立入口；当前阶段不包含 LLM、生产数据库连接、设备控制或工业阈值。

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

健康检查：`GET /health`。

