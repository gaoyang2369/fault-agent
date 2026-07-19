# faultAgent

faultAgent 是 Python 3.12+、FastAPI 实现的工业驱动系统只读诊断后端。当前已完成 M0 定义以及
Task 1～5 的第一版：工程底座、`real_data` 摸底工具、遥测查询链路、领域契约和 IAM 授权骨架。
知识检索、规则引擎、诊断服务、报告、审计和 Agent 编排尚未实现。

首次接触项目请先阅读 [项目快速上手](doc/项目快速上手.md)；它说明了当前完成度、核心调用链、
既有 Task 检查结果、推荐阅读顺序和后续路线。

## 本地开发

```powershell
python -m pip install -e ".[dev]"
ruff format --check .
ruff check .
mypy
pytest
```

```powershell
uvicorn apps.api.main:app --reload
Invoke-RestMethod http://127.0.0.1:8000/health
```

公开接口：

- `GET /health`：API 存活检查，不连接数据库。
- `POST /v1/telemetry/queries`：受权的只读遥测查询；首次调用时按环境配置连接数据源。

默认认证后端只允许无凭据的游客身份，游客受白名单资产、最近一小时、聚合粒度和敏感信号限制。
这只是开发安全边界，不是生产认证方案。

## 文件与目录说明

| 路径 | 作用 |
|---|---|
| `AGENTS.md` | 最高优先级的仓库架构、领域、诊断、安全、数据和开发规则 |
| `README.md` | 项目入口、运行命令和文件地图 |
| `doc/项目快速上手.md` | 完成度、架构、请求链路、阅读顺序、Task 审查和后续计划 |
| `plan.md` | 早期长期路线草案；包含未实现设想，不代表当前状态 |
| `pyproject.toml` | 包元数据、依赖、命令入口及 ruff/mypy/pytest 配置 |
| `.env.example` | 数据库、源时区、查询限制和质量策略的无凭据环境变量示例 |
| `.gitignore` | 凭据、缓存、构建物和数据摸底生成物的忽略规则 |
| `.github/` | 持续集成工作流 |

### 运行入口

| 路径 | 作用 |
|---|---|
| `apps/api/main.py` | FastAPI 应用工厂、生命周期和命令行启动入口 |
| `apps/api/composition.py` | 认证、IAM、资产、遥测仓储和数据库连接的组合根 |
| `apps/api/routers/health.py` | `GET /health` 路由 |
| `apps/api/routers/telemetry.py` | `POST /v1/telemetry/queries` 路由和统一错误映射 |
| `apps/agent_worker/main.py` | 独立 Agent worker 进程入口；当前没有编排任务 |
| `apps/agent_worker/telemetry_tool.py` | 每次重新认证并复用遥测应用服务的 Agent Tool |

### 领域模块

| 路径 | 作用 |
|---|---|
| `modules/asset/domain/models.py` | DriveSystem、Inverter/Motor Component 和 SignalDefinition |
| `modules/asset/application/` | 资产仓储端口与资产/源映射解析服务 |
| `modules/asset/infrastructure/` | G120-1 开发 Fixture 和私有 real_data 源定位模型 |
| `modules/iam/domain/models.py` | 可信主体、授权动作和策略配置 |
| `modules/iam/application/` | 认证端口、上下文工厂和角色/资产/时间/粒度授权策略 |
| `modules/iam/infrastructure/authentication.py` | 匿名游客及内存 Bearer 测试认证后端 |
| `modules/telemetry/domain/` | Observation、TelemetryPoint 和数据质量门控 |
| `modules/telemetry/application/` | 公开查询命令、结果、端口和 TelemetryQueryService |
| `modules/telemetry/infrastructure/real_data_repository.py` | 固定只读 SQL、时间归一、去重、聚合、限制和质量汇总 |
| `modules/telemetry/mysql.py` | PyMySQL 只读会话及环境变量装配 |
| `modules/evidence/domain/models.py` | 不可变 Evidence 快照、判别 payload 和 Claim 证据约束 |
| `modules/diagnosis/domain/models.py` | ReportedEvent、Anomaly、Hypothesis、Recommendation、ConfirmedFault 和诊断结果 |
| `modules/knowledge/` | 知识模块边界，Task 6 尚未实现 |
| `modules/report/` | 报告模块边界，尚未实现 |
| `modules/audit/` | 审计模块边界，尚未实现 |

### 公共契约、工具与测试

| 路径 | 作用 |
|---|---|
| `shared/context.py` | 可信请求上下文、角色和请求来源 |
| `shared/identifiers.py` | 公共强类型标识别名 |
| `shared/time.py` | 时区感知时间范围模型 |
| `shared/errors.py` | 统一公开错误响应模型 |
| `contracts/generate_jsonschema.py` | 从 Pydantic 模型生成版本化 JSON Schema |
| `contracts/jsonschema/` | 对外 JSON Schema；不要手工改动后忘记同步模型 |
| `contracts/examples/` | Schema 正反例和诊断场景示例 |
| `tools/profile_real_data.py` | `real_data` SELECT-only 数据摸底 CLI |
| `real_data_profile.json` | 2026-07-16 数据摸底机器可读快照 |
| `real_data_profile.md` | 同一摸底快照的人类可读报告 |
| `tests/unit/` | 领域不变量、IAM、仓储、服务、工具和注释约束测试 |
| `tests/integration/` | 公开命令到仓储、HTTP 和 IAM 边界的组合测试 |
| `tests/contract/` | JSON Schema、示例和公共契约一致性测试 |
| `doc/m0/` | M0 范围、术语、数据契约、诊断策略、验收场景和 Task 说明 |

`doc/m0/README.md` 是 M0 文档索引；建议重点阅读 `05_source_data_contract.md`、
`12_data_profile_findings.md`、`14_domain_contracts.md` 和 `15_iam_authorization.md`。

## real_data 只读摸底

通过进程环境变量提供连接信息，不要提交真实 `.env` 或生产凭据：

```powershell
$env:REAL_DATA_DSN = "mysql+pymysql://user:password@host:3306/database"
$env:REAL_DATA_TABLE = "real_data"
$env:REAL_DATA_QUERY_TIMEOUT_SECONDS = "15"
python -m tools.profile_real_data
```

工具默认最多读取 10,000 条样本并写出 JSON/Markdown。表名固定为 `real_data`，SQL 由工具内部
定义，动态列来自显式白名单；统计结果是数据事实，不是工业阈值或故障结论。
