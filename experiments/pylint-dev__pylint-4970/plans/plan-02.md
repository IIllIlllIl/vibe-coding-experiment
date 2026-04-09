# Fix: `min-similarity-lines=0` should disable duplicate code checking

## Context

Setting `min-similarity-lines` to `0` in the rcfile should disable duplicate code checking (similar to how flake8 treats `0` as disabling a check). Instead, the check still runs and produces unwanted results. The fix should skip the similarity computation entirely when `min_lines == 0`.

## File to modify

- `pylint/checkers/similar.py`

## Changes

### 1. Add early return in `Similar._compute_sims()` (line ~395)

When `self.min_lines == 0`, return an empty list immediately, skipping all similarity computation:

```python
def _compute_sims(self) -> List[Tuple[int, Set[LinesChunkLimits_T]]]:
    """compute similarities in appended files"""
    if self.min_lines == 0:
        return []
    # ... existing code ...
```

This single change covers both:
- **SimilarChecker** (pylint plugin) — `close()` calls `self._compute_sims()`
- **Standalone `Run()`** — `sim.run()` calls `_display_sims(self._compute_sims())`

### 2. Add test in `tests/checkers/unittest_similar.py`

Add a test verifying that `min_lines=0` produces no similarity reports.

## Verification

1. Run existing tests: `python -m pytest tests/checkers/unittest_similar.py`
2. Run new test to confirm the fix
3. Manually test: create a pylintrc with `min-similarity-lines=0` and verify no duplicate-code messages
