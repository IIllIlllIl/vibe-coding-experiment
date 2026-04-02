# Fix: Dynamically adding xfail marker during test execution (#7490)

## Context

In pytest 5.x, dynamically adding an xfail marker via `request.node.add_marker(pytest.mark.xfail(...))` inside a test function correctly treated the test as XFAIL. In pytest 6.x, the test is reported as FAIL instead.

**Root cause**: The xfail evaluation is cached in `item._store[xfailed_key]` during `pytest_runtest_setup` (before the test runs). By the time `pytest_runtest_makereport` runs (after the test), it reads the stale cached `None` and never re-evaluates, missing the dynamically added marker.

## Fix

### 1. `src/_pytest/skipping.py` — Re-evaluate xfail in `pytest_runtest_makereport`

After line 264 (`xfailed = item._store.get(xfailed_key, None)`), add:

```python
    # Re-evaluate if the marker was added dynamically during the test call.
    if xfailed is None and not item.config.option.runxfail:
        xfailed = evaluate_xfail_marks(item)
```

This mirrors the existing re-evaluation pattern in `pytest_runtest_call` (lines 249-251).

### 2. `testing/test_skipping.py` — Add regression tests

After line 426 (after `test_dynamic_xfail_set_during_funcarg_setup`), add:

```python
def test_dynamic_xfail_during_test(self, testdir):
    """Dynamically adding xfail marker during test execution should work."""
    p = testdir.makepyfile(
        """
        import pytest
        def test_this(request):
            request.node.add_marker(pytest.mark.xfail(reason="dynamically added"))
            assert 0
    """
    )
    result = testdir.runpytest(p, "-rx")
    result.stdout.fnmatch_lines(["*XFAIL*test_this*", "*dynamically added*"])
    result.stdout.fnmatch_lines(["*1 xfailed*"])

def test_dynamic_xfail_during_test_strict(self, testdir):
    """Dynamically adding strict xfail on a passing test should XPASS(strict)."""
    p = testdir.makepyfile(
        """
        import pytest
        def test_this(request):
            request.node.add_marker(pytest.mark.xfail(reason="dynamically added", strict=True))
    """
    )
    result = testdir.runpytest(p, "-rxX")
    result.stdout.fnmatch_lines(["*XPASS(strict)*test_this*"])
    assert result.ret != 0
```

## Verification

1. Run `pytest testing/test_skipping.py -x -v` — all existing tests pass
2. Run `pytest testing/test_skipping.py::TestXFail::test_dynamic_xfail_during_test -v` — new test passes
3. Create the reproducer from the issue and confirm it now shows XFAIL instead of FAIL
