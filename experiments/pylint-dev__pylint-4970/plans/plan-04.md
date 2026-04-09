# Fix: `min-similarity-lines=0` should disable duplicate code check

## Context

When users set `min-similarity-lines` to `0` in the rcfile, they expect the duplicate code check to be disabled (similar to how flake8 treats `0` as disabling a check). Instead, pylint treats every line as a potential duplicate because the comparison at `similar.py:527` (`if eff_cmn_nb > self.min_lines`) becomes `if eff_cmn_nb > 0`, causing nearly every line to be flagged.

## Changes

### File: `pylint/checkers/similar.py`

1. **`SimilarChecker.close()` (line 831)** — Add early return when `self.min_lines == 0` to skip similarity computation entirely.

2. **`Similar.run()` (line 391)** — Add early return when `self.min_lines == 0` for the standalone CLI path.

3. **Option help text (line 742)** — Update help string to mention that `0` disables the check.

## Verification

1. Create a test file with some duplicate lines, run `pylint --min-similarity-lines=0` and confirm no `R0801` messages are emitted.
2. Run existing similarity tests to ensure no regressions: `python -m pytest tests/checkers/unittest_similar.py`
