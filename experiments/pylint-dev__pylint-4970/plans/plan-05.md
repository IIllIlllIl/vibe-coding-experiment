# Fix: `min-similarity-lines=0` should disable duplicate code check

## Context
Setting `min-similarity-lines` to `0` in the rcfile should disable the duplicate code check entirely (similar to how flake8 treats `0` as disabling a check). Instead, it processes all lines and raises spurious duplicate-code errors.

## File to modify
`pylint/checkers/similar.py`

## Changes

### 1. `SimilarChecker.close()` (line ~831)
Add an early return when `self.min_lines == 0` to skip the entire similarity computation:

```python
def close(self):
    """compute and display similarities on closing (i.e. end of parsing)"""
    if self.min_lines == 0:
        return
    ...
```

### 2. `Similar._compute_sims()` (line ~395)
Add a guard for when the class is used standalone (not via `SimilarChecker`):

```python
def _compute_sims(self) -> List[Tuple[int, Set[LinesChunkLimits_T]]]:
    """compute similarities in appended files"""
    if self.min_lines == 0:
        return []
    ...
```

### 3. `Run()` standalone function (line ~887)
Handle the CLI case too:

```python
sim = Similar(min_lines, ...)
if min_lines == 0:
    # No similarity check needed
    ...
```
(Or just let it pass through since `_compute_sims` will return empty.)

## Verification
- Run `python -m pylint --disable=all --enable=duplicate-code --min-similarity-lines=0 <some_file>` and confirm no duplicate-code messages are emitted.
- Run existing tests: `pytest tests/test_self.py -k duplicate`
