import pytest
from web.services.loop_detector import LoopDetector, LOOP_WINDOW_SIZE, LOOP_PHRASE_REPEATS


@pytest.mark.anyio
async def test_initially_clean():
    d = LoopDetector()
    assert d.check("hello") is None


@pytest.mark.anyio
async def test_same_token_repeated_triggers():
    d = LoopDetector()
    for _ in range(LOOP_WINDOW_SIZE - 1):
        d.check("abc")
    result = d.check("abc")
    assert result is not None
    assert "mismo token repetido" in result


@pytest.mark.anyio
async def test_different_tokens_no_loop():
    d = LoopDetector()
    for i in range(LOOP_WINDOW_SIZE + 5):
        assert d.check(str(i)) is None


@pytest.mark.anyio
async def test_inside_code_block_skips_phrase_check():
    d = LoopDetector()
    for ch in "```html-widget\n.content{color:red;} ":
        d.check(ch)
    inner = ".content{color:red;} "
    for _ in range(LOOP_PHRASE_REPEATS + 2):
        for ch in inner:
            d.check(ch)
    assert d.check("x") is None  # skipped


@pytest.mark.anyio
async def test_after_code_block_trigger_works():
    d = LoopDetector()
    for ch in "```html-widget\n<div>x</div>\n```\n":
        d.check(ch)
    block = "B" * 50  # 50 identical chars = a phrase that repeats
    triggered = False
    for _ in range(6):
        for ch in block:
            if d.check(ch) is not None:
                triggered = True
                break
        if triggered:
            break
    assert triggered


@pytest.mark.anyio
async def test_any_code_block_skips_phrase_check():
    """Any triple-backtick block (not just html-widget) should skip phrase check."""
    d = LoopDetector()
    for ch in "```python\ndata = \n    print('test')\n":
        d.check(ch)
    inner = "    print('test')\n"
    for _ in range(LOOP_PHRASE_REPEATS + 2):
        for ch in inner:
            d.check(ch)
    assert d.check("x") is None


@pytest.mark.anyio
async def test_token_check_still_triggers_inside_code_block():
    """Repeated-token check should still fire even inside a code block."""
    d = LoopDetector()
    for ch in "```css\n":
        d.check(ch)
    # Now repeat same token 15 times inside the code block
    for _ in range(LOOP_WINDOW_SIZE):
        d.check("a")
    result = d.check("a")
    assert result is not None
    assert "mismo token repetido" in result
