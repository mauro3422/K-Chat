from src.tools.loader import TOOL_MAP, TOOL_DEFINITIONS

EXPECTED_TOOLS = [
    "fetch_url",
    "get_tool_history",
    "get_widget_code",
    "execute_command",
    "list_files",
    "read_file",
    "read_skill",
    "save_memory",
    "save_widget",
    "update_widget",
    "web_search",
    "write_file",
]

CIRCULAR_SENSITIVE_TOOLS = [
    "get_tool_history",
    "get_widget_code",
    "save_widget",
    "update_widget",
]


def test_tool_map_has_all_expected():
    for name in EXPECTED_TOOLS:
        assert name in TOOL_MAP, f"Missing tool {name!r} in TOOL_MAP"


def test_tool_definitions_has_all_expected():
    for name in EXPECTED_TOOLS:
        assert name in TOOL_DEFINITIONS, f"Missing tool {name!r} in TOOL_DEFINITIONS"


def test_extra_tools_not_accidentally_included():
    assert "__init__" not in TOOL_MAP
    assert "loader" not in TOOL_MAP
    assert "runner" not in TOOL_MAP
    assert "_path_helpers" not in TOOL_MAP
    assert "_widget_helpers" not in TOOL_MAP


def test_tool_map_and_definitions_have_same_keys():
    assert set(TOOL_MAP.keys()) == set(TOOL_DEFINITIONS.keys())


def test_tool_map_values_are_callable():
    for name, func in TOOL_MAP.items():
        assert callable(func), f"{name} tool is not callable"


def test_tool_definitions_required_fields():
    for name, defn in TOOL_DEFINITIONS.items():
        assert "type" in defn, f"{name} missing 'type'"
        assert "function" in defn, f"{name} missing 'function'"
        func = defn["function"]
        assert "name" in func, f"{name} missing 'function.name'"
        assert func["name"] == name, f"{name} function.name mismatch"
        assert "description" in func, f"{name} missing 'function.description'"
        assert "parameters" in func, f"{name} missing 'function.parameters'"
        params = func["parameters"]
        assert "type" in params, f"{name} missing 'parameters.type'"
        assert "properties" in params, f"{name} missing 'parameters.properties'"


def test_tool_definitions_parameters_have_object_type():
    for name, defn in TOOL_DEFINITIONS.items():
        params = defn["function"]["parameters"]
        assert params["type"] == "object", f"{name} parameters.type is not 'object'"


def test_tool_definitions_not_empty():
    assert len(TOOL_MAP) > 0
    assert len(TOOL_DEFINITIONS) > 0


def test_module_attribute_exported():
    for name in EXPECTED_TOOLS:
        import importlib
        mod = importlib.import_module(f"src.tools.{name}")
        assert hasattr(mod, "DEFINITION"), f"src.tools.{name} missing DEFINITION"
        assert hasattr(mod, "run"), f"src.tools.{name} missing run()"


# ── Regression: circular import en tools que usan src.api ──────────────

def test_circular_sensitive_tools_have_lazy_imports():
    """Verifica que las tools con dependencia circular importen src.api
    dentro de run(), no al nivel del módulo."""
    for name in CIRCULAR_SENSITIVE_TOOLS:
        import importlib
        mod = importlib.import_module(f"src.tools.{name}")
        source = open(mod.__file__).read()
        for line in source.splitlines():
            if line.startswith("from src.api import") or line.startswith("from src.tools"):
                raise AssertionError(
                    f"{name} tiene import a nivel módulo: {line!r} "
                    "(debe estar dentro de run() para evitar circular import)"
                )


def test_circular_sensitive_tools_run_imports_api():
    """Ejecuta run() en cada tool sensible para verificar que el import
    lazy dentro de la función no falla."""
    import logging
    logging.disable(logging.CRITICAL)

    for name in CIRCULAR_SENSITIVE_TOOLS:
        import importlib
        mod = importlib.import_module(f"src.tools.{name}")
        fn = getattr(mod, "run")
        kwargs = {"_session_id": None}
        if name == "get_tool_history":
            kwargs["limit"] = 5
        elif name in ("save_widget", "update_widget"):
            kwargs["widget_id"] = "test"
            kwargs["code"] = "<div>test</div>"
        elif name == "get_widget_code":
            kwargs["widget_id"] = "test"
        result = fn(**kwargs)
        assert isinstance(result, str), f"{name}.run() should return str, got {type(result)}"


def test_build_tools_md_generates_all_10():
    """Verifica que la auto-generación de TOOLS.md incluya las tools
    sin errores de circular import."""
    from src.context import _build_tools_md
    result = _build_tools_md()
    for name in EXPECTED_TOOLS:
        assert f"- **{name}**" in result, f"{name} missing from auto-generated TOOLS.md"


def test_build_tools_md_no_errors():
    """Verifica que _build_tools_md() no lance excepciones."""
    import logging
    logging.disable(logging.CRITICAL)
    from src.context import _build_tools_md
    result = _build_tools_md()
    assert len(result) > 0
    assert result.startswith("# Available Tools")


def test_build_tools_md_idempotent():
    """Verifica que regenerar TOOLS.md dos veces dé el mismo resultado."""
    import logging
    logging.disable(logging.CRITICAL)
    from src.context import _build_tools_md
    r1 = _build_tools_md()
    r2 = _build_tools_md()
    assert r1 == r2, "TOOLS.md generation is not idempotent"


def test_all_tools_accept_kwargs_or_session_id():
    """Todas las herramientas deberían aceptar _session_id o **kwargs."""
    for name, func in TOOL_MAP.items():
        import inspect
        sig = inspect.signature(func)
        has_session_id = "_session_id" in sig.parameters
        has_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )
        assert has_session_id or has_kwargs, (
            f"{name}.run() debe tener _session_id o **kwargs"
        )
