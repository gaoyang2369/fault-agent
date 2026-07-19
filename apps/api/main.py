"""FastAPI 应用进程入口。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.api.composition import ApiCompositionRoot
from apps.api.routers.health import router as health_router
from apps.api.routers.telemetry import router as telemetry_router
from modules.iam.application.policy import IamAuthorizationPolicy
from modules.iam.application.ports import AuthenticationBackend
from modules.telemetry.application.service import TelemetryQueryService


def create_app(
    telemetry_service: TelemetryQueryService | None = None,
    *,
    authentication_backend: AuthenticationBackend | None = None,
    iam_policy: IamAuthorizationPolicy | None = None,
) -> FastAPI:
    """创建并装配 HTTP 应用，启动阶段不连接外部基础设施。"""

    composition = ApiCompositionRoot(
        telemetry_service,
        authentication_backend=authentication_backend,
        iam_policy=iam_policy,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        composition.close()

    application = FastAPI(title="faultAgent API", version="0.1.0", lifespan=lifespan)
    application.state.composition_root = composition
    application.include_router(health_router)
    application.include_router(telemetry_router)
    return application


app = create_app()


def run() -> None:
    """使用 Uvicorn 启动本地 API 开发服务器。"""
    import uvicorn

    uvicorn.run("apps.api.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
