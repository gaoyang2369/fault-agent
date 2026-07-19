"""公开 telemetry HTTP 路由。"""

from uuid import uuid4

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse

from apps.api.composition import (
    ApiCompositionRoot,
    TelemetryInfrastructureUnavailableError,
)
from modules.asset.application.service import AssetNotFoundError
from modules.iam.application.ports import AuthenticationError
from modules.telemetry.application.commands import TelemetryQueryCommand
from modules.telemetry.application.results import TelemetryQueryResult
from shared.errors import ErrorDetail, ErrorResponse

router = APIRouter(prefix="/v1/telemetry", tags=["telemetry"])


@router.post(
    "/queries",
    response_model=TelemetryQueryResult,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
async def query_telemetry(
    command: TelemetryQueryCommand, request: Request
) -> TelemetryQueryResult | Response:
    """从可信 HTTP 边界构造上下文，并复用公共遥测应用服务。"""

    trace_id = str(uuid4())
    composition = _composition_root(request)
    try:
        context = composition.authenticate_http(
            request.headers.get("Authorization"),
            request_id=str(uuid4()),
            trace_id=trace_id,
        )
        service = composition.telemetry_service()
        return await service.query(command, context)
    except AssetNotFoundError:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "ASSET_NOT_FOUND",
            "asset or its source mapping was not found",
            trace_id,
        )
    except (TypeError, ValueError) as error:
        return _error_response(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_TELEMETRY_QUERY",
            str(error),
            trace_id,
        )
    except AuthenticationError as error:
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "AUTHENTICATION_REQUIRED",
            str(error),
            trace_id,
        )
    except PermissionError as error:
        return _error_response(
            status.HTTP_403_FORBIDDEN,
            "TELEMETRY_ACCESS_DENIED",
            str(error),
            trace_id,
        )
    except TelemetryInfrastructureUnavailableError:
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "TELEMETRY_UNAVAILABLE",
            "telemetry infrastructure is not available",
            trace_id,
            retryable=True,
        )


def _composition_root(request: Request) -> ApiCompositionRoot:
    """读取由应用工厂安装的组合根。"""

    composition = request.app.state.composition_root
    if not isinstance(composition, ApiCompositionRoot):
        raise RuntimeError("API composition root is not configured")
    return composition


def _error_response(
    status_code: int,
    code: str,
    message: str,
    trace_id: str,
    *,
    retryable: bool = False,
) -> JSONResponse:
    """按统一公开错误契约构造 JSON 响应。"""

    payload = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            retryable=retryable,
            trace_id=trace_id,
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))
