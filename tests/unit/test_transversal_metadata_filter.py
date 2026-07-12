from src.memory.synthesis.transversal import _summary_lines


def test_summary_lines_preserves_semantic_sentences_containing_metadata_words():
    lines = _summary_lines(
        "- We discussed the artifact: provenance is important.\n"
        "- Session: s1\n"
        "- Blended coherence: 0.690 (LSA rel=1.00)\n"
    )

    assert lines == ["We discussed the artifact: provenance is important."]
