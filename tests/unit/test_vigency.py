from src.memory.curator.vigency import audit_bug_candidates


def test_bug_vigency_requires_explicit_closure_marker():
    rows = audit_bug_candidates(
        [{"key": "bug:temporal-misinterpretation", "value": "old timestamps"}],
        project_text="The retrieval code is present.",
        documentation_text="Bug remains open_or_unverified.",
    )
    assert rows[0]["vigency"] == "open_or_unverified"
    rows = audit_bug_candidates(
        [{"key": "bug:temporal-misinterpretation", "value": "old timestamps"}],
        documentation_text="FIXED bug:temporal-misinterpretation after adding timestamps.",
    )
    assert rows[0]["vigency"] == "resolved"
    rows = audit_bug_candidates(
        [{"key": "bug:temporal-misinterpretation", "value": "old timestamps"}],
        documentation_text="bug:temporal-misinterpretation was fixed after adding timestamps.",
    )
    assert rows[0]["vigency"] == "resolved"
    rows = audit_bug_candidates(
        [{"key": "bug:temporal-misinterpretation", "value": "old timestamps"}],
        documentation_text="The unfixed bug:temporal-misinterpretation remains under review.",
    )
    assert rows[0]["vigency"] == "open_or_unverified"
