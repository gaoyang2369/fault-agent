"""Process-local health endpoint."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Stable health-check response contract."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    service: Literal["fault-agent-api"]


@router.get("/health", response_model=HealthResponse, summary="Check API process health")
async def health() -> HealthResponse:
    """Report liveness without accessing databases or other dependencies."""
    return HealthResponse(status="ok", service="fault-agent-api")
