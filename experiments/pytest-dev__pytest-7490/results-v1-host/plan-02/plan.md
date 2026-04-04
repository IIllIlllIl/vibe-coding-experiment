# Fix: Dynamically adding xfail marker in test body no longer ignores failure (pytest#7490)

## Context

In pytest 5.x, calling `request.node.add_marker(pytest.mark.xfail(...))` inside a test function body caused the test to be treated as XFAIL when it failed. In pytest 6.0.0rc1, the same test FAILS instead — the dynamically added marker is ignored.

## Root Cause

The xfail marker evaluation happens at specific points in the test lifecycle:

1. **Setup phase** (`skipping.py:232`): `pytest_runtest_setup` evaluates xfail markers and caches result in `item._store[xfailed_key]`
2. **Call phase** (`skipping.py:247`): `pytest_runtest_call` hookwrapper re-evaluates only if cached value is `None` — but this runs **before `yield`**, i.e., BEFORE the test function body executes
3. **Report phase** (`skipping.py:261`): `pytest_runtest_makereport` reads the cached `xfailed` value to decide how to report the result

When a marker is added inside the test function body (after `yield` in step 2), the evaluation in step 2 already completed with `None`. The report phase reads the stale `None` from the cache, so the failure is not treated as xfail.

Note: Markers added via fixtures (`request.applymarker`) still work because fixture setup runs during the setup phase, BEFORE the call-phase evaluation.

## Fix

In `pytest_runtest_makereport` (`src/_pytest/skipping.py:261`), when `xfailed` is `None`, re-evaluate xfail marks before checking the condition at line 279. This catches markers dynamically added during the test body.

### Change in `src/_pytest/skipping.py`

In `pytest_runtest_makereport`, after line 264:
```python
xfailed = item._store.get(xfailed_key, None)
```

Add re-evaluation:
```python
if xfailed is None:
    xfailed = evaluate_xfail_marks(item)
```

This is a minimal, targeted fix. It only changes the report-making path and doesn't affect the setup/call evaluation logic.

### Add test in `testing/test_skipping.py`

Add a test case that reproduces the exact scenario from the issue — dynamically adding an xfail marker inside the test function body using `request.node.add_marker()`.

Also consider enabling/fixing the disabled test `xtest_dynamic_xfail_set_during_setup` at line 385.

## Verification

1. Create a test file matching the issue's reproduction case:
   ```python
   import pytest
   def test_xfail_test(request):
       mark = pytest.mark.xfail(reason="xfail")
       request.node.add_marker(mark)
       assert 0
   ```
2. Run `pytest -rsx test_file.py` — should show XFAIL, not FAIL
3. Run existing xfail tests: `pytest testing/test_skipping.py -x` — all should pass
4. Run full test suite to check for regressions: `pytest testing/test_skipping.py`
