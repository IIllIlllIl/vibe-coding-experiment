# Fix: Dynamically adding xfail marker in test no longer ignores failure (pytest#7490)

## Context

In pytest 5.x, dynamically adding an xfail marker via `request.node.add_marker(pytest.mark.xfail())` during test execution worked correctly — the test was treated as xfailed. After a refactoring in pytest 6.0 (commit 3e6fe92b7), the xfail evaluation became static: it's evaluated once during setup and cached. Markers added **during the test function** itself are never picked up.

**Root cause**: In `src/_pytest/skipping.py`, `evaluate_xfail_marks()` is called in `pytest_runtest_setup` (line 242) and cached in `item._store[xfailed_key]`. When no marker exists, `None` is cached. In `pytest_runtest_call` (line 249-251), re-evaluation happens **before** `yield` (before the test runs), so a marker added inside the test body is still missed. `pytest_runtest_makereport` (line 264) only reads the cached value and never re-evaluates.

## Fix

**File**: `src/_pytest/skipping.py` — `pytest_runtest_makereport` (line 264)

Add a re-evaluation of xfail marks in `pytest_runtest_makereport` when the cached result is `None`. This is the hook that determines the final test outcome, so re-evaluating here catches markers added at any point during execution.

**Change** (line 264):
```python
# Before:
xfailed = item._store.get(xfailed_key, None)

# After:
xfailed = item._store.get(xfailed_key, None)
if xfailed is None:
    xfailed = item._store[xfailed_key] = evaluate_xfail_marks(item)
```

This is the same pattern already used in `pytest_runtest_call` (line 250-251), but placed at the point where the outcome is actually determined.

**Why this works**: If the test added a dynamic xfail marker and then failed, `evaluate_xfail_marks()` will now find it and return an `Xfail` object. The subsequent logic (lines 279-293) will then correctly set `rep.outcome = "skipped"` and `rep.wasxfail`.

**Why this is safe**: If no marker was added, the re-evaluation just returns `None` again (no-op). The `None` check prevents overwriting a previously evaluated `Xfail` result.

## Test

**File**: `testing/test_skipping.py`

Add a test case that reproduces the issue from the bug report:
```python
def test_dynamic_xfail_during_test(self, testdir):
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

Also add a test for the xpass case (dynamic xfail marker, but test passes):
```python
def test_dynamic_xfail_during_test_passing(self, testdir):
    p = testdir.makepyfile(
        """
        import pytest
        def test_xfail_test(request):
            mark = pytest.mark.xfail(reason="xfail")
            request.node.add_marker(mark)
    """
    )
    result = testdir.runpytest(p, "-rxX")
    result.stdout.fnmatch_lines(["*1 xpassed*"])
```

## Verification

1. Run the new tests: `python -m pytest testing/test_skipping.py -k "dynamic_xfail_during" -v`
2. Run existing skipping tests to check for regressions: `python -m pytest testing/test_skipping.py -v`
3. Reproduce the exact scenario from the issue:
   ```
   echo 'import pytest
   def test_xfail_test(request):
       mark = pytest.mark.xfail(reason="xfail")
       request.node.add_marker(mark)
       assert 0' > /tmp/test_foo.py
   python -m pytest -rxX /tmp/test_foo.py
   ```
   Expected: `1 xfailed` instead of `1 failed`
