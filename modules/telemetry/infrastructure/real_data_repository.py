"""Task 3.1 只读适配器的分层兼容导入模块。"""

from modules.telemetry.repository import RealDataRepository, RepositoryResult

__all__ = ["RealDataRepository", "RepositoryResult"]
