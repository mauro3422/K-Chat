from web.services.widget_contract import (
    WIDGET_STATE_CODE_PREFIX,
    extract_inline_widget_states,
    normalize_inline_widget_code,
)


def test_normalize_inline_widget_code_repairs_optional_chain_assignment():
    assert normalize_inline_widget_code("obj?.foo.bar = 1;") == "obj.foo.bar = 1;"


def test_extract_inline_widget_states_uses_code_prefix():
    msgs = [
        ("assistant", "Before\n```html-widget calc\nobj?.foo.bar = 42;\n```\nAfter", None, None, None, None),
        ("user", "ignore", None, None, None, None),
    ]

    states = extract_inline_widget_states(msgs)

    assert states == {f"{WIDGET_STATE_CODE_PREFIX}calc": "obj.foo.bar = 42;"}
