"""API 进程的组合根。"""

from threading import Lock

from pymysql.err import MySQLError

from modules.asset.application.service import AssetSourceResolver
from modules.asset.infrastructure.in_memory_repository import InMemoryAssetRepository
from modules.iam.application.context import RequestContextFactory
from modules.iam.application.policy import IamAuthorizationPolicy
from modules.iam.application.ports import AuthenticationBackend
from modules.iam.domain.models import IamPolicyConfig
from modules.iam.infrastructure.authentication import AnonymousGuestAuthenticationBackend
from modules.telemetry.application.service import TelemetryQueryService
from modules.telemetry.mysql import MySQLQueryExecutor, create_repository_from_environment
from shared.context import RequestContext, RequestSource


class TelemetryInfrastructureUnavailableError(RuntimeError):
    """表示正式遥测基础设施缺少配置或无法建立连接。"""


class ApiCompositionRoot:
    """集中装配公共应用服务，并把数据库连接生命周期留在 API 进程。"""

    def __init__(
        self,
        telemetry_service: TelemetryQueryService | None = None,
        *,
        authentication_backend: AuthenticationBackend | None = None,
        iam_policy: IamAuthorizationPolicy | None = None,
    ) -> None:
        """可注入测试服务，正式服务在第一次遥测请求时按需创建。"""

        self._telemetry_service = telemetry_service
        self._authentication_backend = (
            authentication_backend or AnonymousGuestAuthenticationBackend()
        )
        self._context_factory = RequestContextFactory()
        self._iam_policy = iam_policy or IamAuthorizationPolicy(
            IamPolicyConfig(guest_visible_asset_ids=frozenset({"asset-g120-1"}))
        )
        self._executor: MySQLQueryExecutor | None = None
        self._lock = Lock()

    def authenticate_http(
        self,
        authorization: str | None,
        *,
        request_id: str,
        trace_id: str,
    ) -> RequestContext:
        """每个 HTTP 请求重新认证，并从可信主体构造上下文。"""

        principal = self._authentication_backend.authenticate(authorization)
        return self._context_factory.create(
            principal,
            request_id=request_id,
            trace_id=trace_id,
            request_source=RequestSource.HTTP,
        )

    def telemetry_service(self) -> TelemetryQueryService:
        """返回共享服务，且不会在应用启动或健康检查时连接源数据库。"""

        if self._telemetry_service is not None:
            return self._telemetry_service
        with self._lock:
            if self._telemetry_service is not None:
                return self._telemetry_service
            try:
                repository, executor = create_repository_from_environment()
            except (MySQLError, OSError, ValueError) as error:
                raise TelemetryInfrastructureUnavailableError(
                    "telemetry infrastructure is not available"
                ) from error
            assets = InMemoryAssetRepository.g120_fixture()
            self._executor = executor
            self._telemetry_service = TelemetryQueryService(
                AssetSourceResolver(assets),
                repository,
                policy=self._iam_policy,
            )
            return self._telemetry_service

    def close(self) -> None:
        """关闭由组合根创建的数据库连接。"""

        if self._executor is not None:
            self._executor.close()
            self._executor = None
