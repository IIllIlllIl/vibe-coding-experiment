# Fix: Dynamically added xfail marker no longer ignores failure (pytest #7490)

## Context

In pytest 5.x, dynamically adding an xfail marker via `request.node.add_marker(mark)` inside a test body caused the test to be treated as xfail. In 6.0.0rc1, this broke — the test fails instead. The regression was introduced by the refactoring of skip/xfail evaluation in `src/_pytest/skipping.py`.

## Root Cause

The xfail evaluation timing is wrong for dynamically added markers:

1. **`pytest_runtest_setup`** (line 232) evaluates xfail marks → finds none → sets `item._store[xfailed_key] = None`
2. **`pytest_runtest_call`** (line 247, before `yield`) re-evaluates → still `None` (marker hasn't been added yet)
3. `yield` runs the test body → `request.node.add_marker(mark)` adds xfail, then `assert 0` fails
4. Nothing after `yield` re-evaluates xfail marks
5. **`pytest_runtest_makereport`** (line 260) sees `xfailed = None` → treats failure as a real failure, not xfail

## Fix

**File: `src/_pytest/skipping.py`** — `pytest_runtest_call` (line 247-257)

Add a re-evaluation of xfail marks **after** `yield`, so dynamically added markers are picked up:

```python
@hookimpl(hookwrapper=True)
def pytest_runtest_call(item: Item) -> Generator[None, None, None]:
    xfailed = item._store.get(xfailed_key, None)
    if xfailed is None:
        item._store[xfailed_key] = xfailed = evaluate_xfail_marks(item)

    if not item.config.option.runxfail:
        if xfailed and not xfailed.run:
            xfail("[NOTRUN] " + xfailed.reason)

    yield

    # The test may have dynamically added an xfail marker during execution.
    if item._store.get(xfailed_key, None) is None:
        item._store[xfailed_key] = evaluate_xfail_marks(item)
```

This works because `pytest_runtest_makereport` runs after `pytest_runtest_call` fully completes (including post-yield code), so it will see the updated `xfailed_key` value.

## Test

**File: `testing/test_skipping.py`**

Add a test case matching the exact scenario from the issue report:

```python
def test_dynamic_xfail_set_during_test(self, testdir):
    """Test that xfail marker added dynamically during test execution works (#7490)."""
    p = testdir.makepyfile(
        """
        import pytest
        def test_xfail_test(request):
            mark = pytest.mark.xfail(reason="xfail")
            request.node.add_marker(mark)
            assert 0
    """
    )
    result = testdir.runpytest(p, "-rxX")
    result.stdout.fnmatch_lines(["*1 xfailed*"])
```

## Verification

1. Run the new test: `python -m pytest testing/test_skipping.py::TestEvaluationOfXFailBoolCondition::test_dynamic_xfail_set_during_test -xvs`
2. Run the existing xfail tests: `python -m pytest testing/test_skipping.py -x`
3. Verify the exact scenario from the issue:
   ```
   # Create test_foo.py with the reproducer
   python -m pytest test_foo.py -rsx
   # Should show XFAIL, not FAIL
   ```
