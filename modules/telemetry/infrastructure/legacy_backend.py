"""把 Task 3.1 源表查询桥接为 Task 4 公开结果。"""

from modules.asset.infrastructure.models import RealDataSourceLocator
from modules.telemetry.application.commands import (
    AggregationFunction,
    AggregationSpec,
    TelemetryQueryCommand,
)
from modules.telemetry.application.results import SourceMetadata, TelemetryQueryResult
from modules.telemetry.domain.models import SignalQuality, SignalValue, TelemetryPoint
from modules.telemetry.domain.quality import AllowedAnalysis, DataQualitySummary
from modules.telemetry.models import (
    AggregationFunction as LegacyAggregationFunction,
)
from modules.telemetry.models import (
    AggregationSpec as LegacyAggregationSpec,
)
from modules.telemetry.models import (
    RequestContext as LegacyRequestContext,
)
from modules.telemetry.models import (
    TelemetryQuery,
)
from modules.telemetry.service import TelemetryQueryService as LegacyTelemetryQueryService
from shared.context import RequestContext
from shared.identifiers import AssetId


class LegacyRealDataBackend:
    """临时基础设施兼容后端，Task 3.1 迁移完成后删除。"""

    def __init__(self, legacy_service: LegacyTelemetryQueryService) -> None:
        """保存待桥接的旧版遥测查询服务。"""

        self._legacy_service = legacy_service

    def query(
        self,
        *,
        asset_id: AssetId,
        source_locator: object,
        command: TelemetryQueryCommand,
        context: RequestContext,
    ) -> TelemetryQueryResult:
        """转换新旧命令、上下文、质量和点模型，并隐藏私有源定位信息。"""

        if not isinstance(source_locator, RealDataSourceLocator):
            raise TypeError("real_data backend requires RealDataSourceLocator")
        legacy_result = self._legacy_service.query(
            TelemetryQuery(
                device_name=source_locator.device_name,
                inverter_name=source_locator.inverter_name,
                start=command.time_range.start,
                end=command.time_range.end,
                signals=command.signal_codes,
                aggregation=_legacy_aggregation(command.aggregation),
                max_points=command.max_points,
            ),
            LegacyRequestContext(
                request_id=context.request_id,
                trace_id=context.trace_id,
                user_id=context.user_id,
                roles=tuple(role.value for role in context.roles),
            ),
        )
        allowed_map = {
            "POINT": AllowedAnalysis.POINT_SUMMARY,
            "REPORTED_EVENT": AllowedAnalysis.REPORTED_EVENT_DETECTION,
            "TREND": AllowedAnalysis.TREND_ANALYSIS,
            "DURATION": AllowedAnalysis.DURATION_RULES,
        }
        quality = DataQualitySummary(
            **legacy_result.data_quality.model_dump(exclude={"allowed_analyses"}),
            allowed_analyses=tuple(
                allowed_map[item] for item in legacy_result.data_quality.allowed_analyses
            ),
            warnings=tuple(warning.code for warning in legacy_result.warnings),
        )
        points = tuple(
            TelemetryPoint(
                observed_at=point.observed_at,
                asset_id=asset_id,
                source_record_ids=point.source_record_ids,
                values={
                    code: SignalValue(
                        value=value.value,
                        unit=value.unit,
                        quality=_quality(value.quality),
                    )
                    for code, value in point.values.items()
                },
            )
            for point in legacy_result.points
        )
        return TelemetryQueryResult(
            asset_id=asset_id,
            time_range=command.time_range,
            points=points,
            data_quality=quality,
            warnings=tuple(warning.code for warning in legacy_result.warnings),
            source_metadata=SourceMetadata(
                scanned_rows=legacy_result.scanned_rows,
                matched_rows=legacy_result.matched_rows,
                discarded_duplicate_count=legacy_result.discarded_duplicate_count,
                truncated=legacy_result.truncated,
            ),
        )


def _legacy_aggregation(spec: AggregationSpec | None) -> LegacyAggregationSpec | None:
    """把公开聚合配置转换为旧版服务使用的枚举和模型。"""

    if spec is None:
        return None
    mapping = {
        AggregationFunction.MIN: LegacyAggregationFunction.MIN,
        AggregationFunction.MAX: LegacyAggregationFunction.MAX,
        AggregationFunction.AVG: LegacyAggregationFunction.AVG,
    }
    return LegacyAggregationSpec(
        window_seconds=spec.window_seconds,
        functions=tuple(mapping[item] for item in spec.functions),
    )


def _quality(value: str) -> SignalQuality:
    """把旧版文本质量状态映射为公开信号质量枚举。"""

    if value == "GOOD":
        return SignalQuality.GOOD
    if value in {"MISSING", "MISSING_OR_INVALID"}:
        return SignalQuality.MISSING
    return SignalQuality.BAD
