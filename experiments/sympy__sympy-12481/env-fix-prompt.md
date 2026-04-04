/plan Fix the Docker test environment for sympy__sympy-12481.

Repo: sympy/sympy (version 1.0)
Docker image: swe-env:sympy-sympy-12481

The environment check failed:
  test_patch_only: exit_code=4, 0 passed, 0 failed
  test_patch_plus_gold_patch: exit_code=4, 0 passed, 0 failed

Key issues to investigate:
1. Check the test output in /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/sympy__sympy-12481/env-check.json for errors
2. Check if the Dockerfile at /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/sympy__sympy-12481/env-build/Dockerfile has correct dependencies
3. The test framework is: pytest

After fixing, rebuild and verify:
  python scripts/build-env.py /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/sympy__sympy-12481
  python scripts/check-env.py /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/sympy__sympy-12481 --image swe-env:sympy-sympy-12481

Save this plan to /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/sympy__sympy-12481/plans/env-fix-plan.md