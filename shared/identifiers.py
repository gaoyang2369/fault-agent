"""语义明确且相互区分的公开标识类型。"""

from typing import Annotated

from pydantic import Field

AssetId = Annotated[str, Field(min_length=1, max_length=128)]
AssetCode = Annotated[str, Field(min_length=1, max_length=128)]
DiagnosisId = Annotated[str, Field(min_length=1, max_length=128)]
EvidenceId = Annotated[str, Field(min_length=1, max_length=128)]
ClaimId = Annotated[str, Field(min_length=1, max_length=128)]
UserId = Annotated[str, Field(min_length=1, max_length=128)]
