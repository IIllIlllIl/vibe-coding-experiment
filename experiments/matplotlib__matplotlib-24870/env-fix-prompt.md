/plan Fix the Docker test environment for matplotlib__matplotlib-24870.

Repo: matplotlib/matplotlib (version 3.6)
Docker image: swe-env:matplotlib-matplotlib-24870

The environment check failed:
  test_patch_only: exit_code=1, 63 passed, 3 failed
  test_patch_plus_gold_patch: exit_code=1, 64 passed, 2 failed

Key issues to investigate:
1. Check the test output in experiments/matplotlib__matplotlib-24870/env-check.json for errors
2. Check if the Dockerfile at experiments/matplotlib__matplotlib-24870/env-build/Dockerfile has correct dependencies
3. The test framework is: pytest

After fixing, rebuild and verify:
  python scripts/build-env.py experiments/matplotlib__matplotlib-24870
  python scripts/check-env.py experiments/matplotlib__matplotlib-24870 --image swe-env:matplotlib-matplotlib-24870

Save this plan to experiments/matplotlib__matplotlib-24870/plans/env-fix-plan.md