# Plan: Treat `min-similarity-lines=0` as disabled

## Context

When `min-similarity-lines` is set to `0`, users expect the duplicate code check to be disabled (similar to flake8's convention of treating `0` as disabling a check). Currently, setting it to `0` does not explicitly skip the check — it relies on `hash_lineset()` producing empty results due to `range(0)` being empty, which is an accidental side effect rather than intentional behavior. The fix should add an explicit early return when `min_lines == 0` so the check is cleanly and predictably disabled.

## Changes

### 1. Add early return in `Similar._compute_sims()` — `pylint/checkers/similar.py:395`

Add a guard at the top of `_compute_sims()` to skip all similarity computation when `self.min_lines == 0`:

```python
def _compute_sims(self) -> List[Tuple[int, Set[LinesChunkLimits_T]]]:
    """compute similarities in appended files"""
    if self.min_lines == 0:
        return []
    ...
```

This is the main entry point called by both `SimilarChecker.close()` and `Similar.run()`, so a single guard covers both paths.

### 2. Update option help text — `pylint/checkers/similar.py:742`

Update the help string to document that `0` disables the check:

```python
"help": "Minimum lines number of a similarity. Set to 0 to disable.",
```

### 3. Add test — `tests/checkers/unittest_similar.py`

Add a test that verifies `--duplicates 0` produces no similarity output (no false positives):

```python
def test_min_similarity_lines_zero_disables_check() -> None:
    output = StringIO()
    with redirect_stdout(output), pytest.raises(SystemExit) as ex:
        similar.Run(["--duplicates", "0", SIMILAR1, SIMILAR2])
    assert ex.value.code == 0
    assert "similar lines in" not in output.getvalue()
```

## Files to modify

- `pylint/checkers/similar.py` — early return in `_compute_sims()` + help text update
- `tests/checkers/unittest_similar.py` — new test for `min-similarity-lines=0`

## Verification

```bash
python -m pytest tests/checkers/unittest_similar.py -v
```
