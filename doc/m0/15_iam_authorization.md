# Task 5 IAM 与授权边界

## 1. 可信上下文

HTTP 和 Agent tool 的业务 payload 均不能提供 `user_id`、`roles` 或 `asset_scope`。认证适配器
验证边界凭据后返回 `TrustedPrincipal`，再由 `RequestContextFactory` 写入请求来源、请求标识和
追踪标识。默认开发认证后端只在无认证头时签发固定游客身份；工程师和管理员必须通过显式配置的
认证后端进入系统。

## 2. 确定性授权

`IamAuthorizationPolicy` 同时检查角色能力和资产范围：

- 游客只能访问 `guest_visible_asset_ids`，时间范围必须完全位于当前时刻最近一小时内，必须使用
  60 秒或更粗的聚合窗口，并禁止查询 `status_word`、`control_word`；
- 工程师只能访问 `engineer_asset_assignments[user_id]` 中的资产，可查询原始或聚合遥测，并可对
  已分配资产执行诊断和生成报告；
- 管理员可访问全部本地资产并管理知识；
- 未装配 IAM 策略时，遥测应用服务默认拒绝，而不是放行。

这些规则位于 IAM/Application 层，不进入只读 `RealDataRepository`。授权发生在解析私有源定位
之前，HTTP 与 Agent tool 最终复用同一个 `TelemetryQueryService`。

## 3. Agent tool

`ReauthenticatingAgentToolContextProvider` 在每次 Tool 调用时重新读取并验证 worker 会话凭据，
生成新的 `RequestContext`。`TelemetryQueryTool` 不接受身份、角色或资产范围参数，也不缓存上一次
调用的上下文；即使同一 Agent run 中权限发生变化，下一次调用也会重新执行认证和授权。

## 4. TODO-SECURITY

- 生产认证协议、令牌签发方、签名验证、撤销和会话生命周期尚未确定；当前仅提供端口、匿名游客
  后端和不含真实凭据的内存测试后端。
- `guest_visible_asset_ids` 与 `engineer_asset_assignments` 当前由受信组合配置注入；接入应用数据库
  后需增加分配变更审计和缓存失效机制。
- 数据“最新时刻”目前以授权时钟为上界。接入持续更新数据源前，需要确定是否改为经验证的资产
  数据水位，并保证该水位不能由 LLM 或请求 payload 提供。
