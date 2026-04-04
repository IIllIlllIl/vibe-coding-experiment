# Fix: Dynamically adding xfail marker in test no longer ignores failure (#7490)

## Context

In pytest 5.x, dynamically adding an xfail marker via `request.node.add_marker(pytest.mark.xfail(...))` during test execution caused the test to be treated as xfailed. In pytest 6.x, this no longer works — the test fails normally.

## Root Cause

In `src/_pytest/skipping.py`, the xfail marker evaluation happens at two points:

1. **`pytest_runtest_setup`** (line 242): Evaluates xfail marks and caches result in `item._store[xfailed_key]`. At this point, no dynamic marker exists yet.

2. **`pytest_runtest_call`** (line 249-251): Re-evaluates if cached value is `None`. But this is a hookwrapper — the evaluation runs **before** `yield`, so the test function (which adds the marker) hasn't executed yet.

3. **`pytest_runtest_makereport`** (line 264): Reads the cached `xfailed` value. Since it's `None` (no marker was found in steps 1-2), no xfail treatment is applied.

The marker is added during step 2's `yield` (inside the test body), but by step 3, the stale cached `None` is used.

## Fix

**File:** `src/_pytest/skipping.py`, in `pytest_runtest_makereport` (around line 264).

Re-evaluate xfail marks in `pytest_runtest_makereport` when the cached value is `None`. At this point the test has already executed, so any dynamically-added markers will be present.

```python
# Current (line 264):
xfailed = item._store.get(xfailed_key, None)

# Change to:
xfailed = item._store.get(xfailed_key, None)
if xfailed is None:
    item._store[xfailed_key] = xfailed = evaluate_xfail_marks(item)
```

## Test

**File:** `testing/test_skipping.py`

Add a test case matching the issue's reproducer — a test that dynamically adds an xfail marker via `request.node.add_marker()` and then fails, verifying it is reported as XFAIL rather than FAIL.

## Verification

```bash
# Run the specific test
python -m pytest testing/test_skipping.py -k "test_dynamic_xfail_set_during_test" -v

# Run all skipping tests
python -m pytest testing/test_skipping.py -v

# Quick manual verification with the reproducer from the issue
```
