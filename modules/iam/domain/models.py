"""可信身份、授权动作和确定性 IAM 配置。"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.context import Role
from shared.identifiers import AssetId, UserId


class StrictModel(BaseModel):
    """拒绝未知字段且实例不可变的 IAM 模型基类。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class TrustedPrincipal(StrictModel):
    """由认证后端验证后交给应用边界的主体，不来自业务 payload。"""

    user_id: UserId
    roles: frozenset[Role] = Field(min_length=1)
    authenticated_at: datetime

    @model_validator(mode="after")
    def require_aware_authentication_time(self) -> "TrustedPrincipal":
        """认证时间必须包含明确时区。"""

        if self.authenticated_at.tzinfo is None or self.authenticated_at.utcoffset() is None:
            raise ValueError("authenticated_at must be timezone-aware")
        return self


class IamAction(StrEnum):
    """Task 5 需要确定性授权的应用动作。"""

    QUERY_TELEMETRY = "QUERY_TELEMETRY"
    RUN_DIAGNOSIS = "RUN_DIAGNOSIS"
    GENERATE_REPORT = "GENERATE_REPORT"
    MANAGE_KNOWLEDGE = "MANAGE_KNOWLEDGE"


class IamPolicyConfig(StrictModel):
    """从受信配置装配的资产范围和游客数据粒度边界。"""

    guest_visible_asset_ids: frozenset[AssetId] = frozenset()
    engineer_asset_assignments: dict[UserId, frozenset[AssetId]] = Field(default_factory=dict)
    guest_max_age_seconds: int = Field(default=3600, gt=0, le=3600)
    guest_min_aggregation_window_seconds: int = Field(default=60, ge=60)
    guest_restricted_signal_codes: frozenset[str] = frozenset({"control_word", "status_word"})
