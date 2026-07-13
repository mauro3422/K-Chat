from __future__ import annotations

import subprocess
import sys


def test_tools_package_import_is_lazy() -> None:
    script = r"""
import importlib
import sys

tools = importlib.import_module("src.tools")
print("src.tools.registry" in sys.modules)
print("src.tools.runner" in sys.modules)
print(hasattr(tools, "ToolRegistry"))
print("src.tools.registry" in sys.modules)
print("src.tools.runner" in sys.modules)
print(hasattr(tools, "run_parallel_tools"))
print("src.tools.runner" in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip().splitlines() == [
        "False",
        "False",
        "True",
        "True",
        "False",
        "True",
        "True",
    ]


def test_tools_package_keeps_default_registry_helper() -> None:
    script = r"""
import importlib

tools = importlib.import_module("src.tools")
registry = tools.get_default_registry()
print(type(registry).__name__)
print("remember" in registry.tool_map)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip().splitlines() == [
        "ToolRegistry",
        "True",
    ]
