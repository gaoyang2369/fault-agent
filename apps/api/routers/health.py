"""仅检查当前 API 进程存活状态的端点。"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """稳定的 API 存活检查响应契约。"""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    service: Literal["fault-agent-api"]


@router.get("/health", response_model=HealthResponse, summary="Check API process health")
async def health() -> HealthResponse:
    """不访问数据库或其他依赖，直接报告 API 进程存活。"""
    return HealthResponse(status="ok", service="fault-agent-api")
