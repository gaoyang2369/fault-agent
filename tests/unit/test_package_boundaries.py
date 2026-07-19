"""模块化单体必要包边界的冒烟测试。"""

import ast
import importlib
import re
from pathlib import Path

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

PYTHON_SOURCE_ROOTS = ("apps", "contracts", "modules", "shared", "tests", "tools")
CHINESE_CHARACTER = re.compile(r"[\u4e00-\u9fff]")


@pytest.mark.parametrize("package_name", REQUIRED_PACKAGES)
def test_required_package_is_importable(package_name: str) -> None:
    """验证架构要求的各顶层包均可独立导入。"""

    assert importlib.import_module(package_name) is not None


def test_all_python_modules_classes_and_functions_have_chinese_docstrings() -> None:
    """防止新增 Python 模块、类或函数时遗漏中文用途说明。"""

    missing: list[str] = []
    for root_name in PYTHON_SOURCE_ROOTS:
        for path in Path(root_name).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            documented_nodes: list[
                ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
            ] = [tree]
            documented_nodes.extend(
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            )
            for node in documented_nodes:
                docstring = ast.get_docstring(node)
                if docstring is None or CHINESE_CHARACTER.search(docstring) is None:
                    name = getattr(node, "name", "<module>")
                    line = getattr(node, "lineno", 1)
                    missing.append(f"{path}:{line}:{name}")

    assert missing == [], "缺少中文 docstring：\n" + "\n".join(missing)
