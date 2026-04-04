/plan Fix the Docker test environment for sympy__sympy-24443.

Repo: sympy/sympy (version 1.12)
Docker image: swe-env:sympy-sympy-24443

The environment check failed:
  test_patch_only: exit_code=1, 2 passed, 2 failed

Key issues to investigate:
1. Check the test output in /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/sympy__sympy-24443/env-check.json for errors
2. Check if the Dockerfile at /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/sympy__sympy-24443/env-build/Dockerfile has correct dependencies
3. The test framework is: pytest

After fixing, rebuild and verify:
  python scripts/build-env.py /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/sympy__sympy-24443
  python scripts/check-env.py /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/sympy__sympy-24443 --image swe-env:sympy-sympy-24443

Save this plan to /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/sympy__sympy-24443/plans/env-fix-plan.md