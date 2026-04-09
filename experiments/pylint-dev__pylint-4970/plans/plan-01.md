# Fix: `min-similarity-lines=0` should disable duplicate code checking

## Context

Setting `min-similarity-lines` to `0` in the rcfile should disable duplicate code checking (consistent with how flake8 treats `0` as disabling a check). Currently, it does not — the similarity computation still runs and produces incorrect results. The fix should short-circuit when `min_lines == 0` so the check is skipped entirely.

## File to modify

- `pylint/checkers/similar.py`

## Changes

### 1. Add early return in `Similar._iter_sims()` (line ~530)

When `self.min_lines == 0`, return immediately without yielding any commonalities. This single change covers both the standalone `Run()` CLI path and the `SimilarChecker.close()` checker path, since both flow through `_compute_sims()` which calls `_iter_sims()`.

```python
def _iter_sims(self):
    if self.min_lines == 0:
        return
    ...
```

### 2. Update help text for `min-similarity-lines` option (line ~742)

Mention that setting it to `0` disables the check:

```python
"help": "Minimum lines number of a similarity. Set to 0 to disable.",
```

## Verification

Run the existing similarity tests:
```bash
python -m pytest tests/checkers/unittest_similar.py -v
```

Additionally, test manually that `min-similarity-lines=0` produces no duplicate errors:
```bash
python -m pylint --enable=R0801 --min-similarity-lines=0 tests/input/similar1 tests/input/similar2
```
