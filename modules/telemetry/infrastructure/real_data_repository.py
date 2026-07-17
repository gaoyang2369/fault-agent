"""Layered import for the Task 3.1 read-only adapter."""

from modules.telemetry.repository import RealDataRepository, RepositoryResult

__all__ = ["RealDataRepository", "RepositoryResult"]
