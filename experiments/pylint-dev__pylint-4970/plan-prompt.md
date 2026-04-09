/plan Setting `min-similarity-lines` to `0` should stop pylint from checking duplicate code

Setting `min-similarity-lines` to `0` in the rcfile doesn't disable checking for duplicate code, it instead treats every line of code as duplicate and raises many errors.

Setting `min-similarity-lines` to `0` should disable the duplicate code check, similar to how flake8 treats `0` as disabling a check.

The fix should be in `pylint/checkers/similar.py` — when `min_lines == 0`, the duplicate code check should be skipped entirely.

Save this plan to ../plans/plan-01.md
