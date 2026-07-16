"""Smoke tests for required modular-monolith package boundaries."""

import importlib

import pytest

REQUIRED_PACKAGES = (
    "apps.api",
    "apps.agent_worker",
    "modules.iam",
    "modules.asset",
    "modules.telemetry",
    "modules.knowledge",
    "modules.diagnosis",
    "modules.evidence",
    "modules.report",
    "modules.audit",
    "contracts",
)


@pytest.mark.parametrize("package_name", REQUIRED_PACKAGES)
def test_required_package_is_importable(package_name: str) -> None:
    assert importlib.import_module(package_name) is not None
