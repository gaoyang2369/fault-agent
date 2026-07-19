"""API 进程的组合根。"""

from threading import Lock

from pymysql.err import MySQLError

from modules.asset.application.service import AssetSourceResolver
from modules.asset.infrastructure.in_memory_repository import InMemoryAssetRepository
from modules.telemetry.application.ports import GuestTelemetryPolicy
from modules.telemetry.application.service import TelemetryQueryService
from modules.telemetry.mysql import MySQLQueryExecutor, create_repository_from_environment


class TelemetryInfrastructureUnavailableError(RuntimeError):
    """表示正式遥测基础设施缺少配置或无法建立连接。"""


class ApiCompositionRoot:
    """集中装配公共应用服务，并把数据库连接生命周期留在 API 进程。"""

    def __init__(self, telemetry_service: TelemetryQueryService | None = None) -> None:
        """可注入测试服务，正式服务在第一次遥测请求时按需创建。"""

        self._telemetry_service = telemetry_service
        self._executor: MySQLQueryExecutor | None = None
        self._lock = Lock()

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
                policy=GuestTelemetryPolicy(frozenset({"asset-g120-1"})),
            )
            return self._telemetry_service

    def close(self) -> None:
        """关闭由组合根创建的数据库连接。"""

        if self._executor is not None:
            self._executor.close()
            self._executor = None
