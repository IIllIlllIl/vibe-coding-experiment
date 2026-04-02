/plan Fix the Docker test environment for pytest-dev__pytest-7490.

Repo: pytest-dev/pytest (version 6.0)
Docker image: swe-env:pytest-dev-pytest-7490

The environment check failed:
  test_patch_only: exit_code=1, 73 passed, 2 failed

Key issues to investigate:
1. Check the test output in /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/pytest-dev__pytest-7490/env-check.json for errors
2. Check if the Dockerfile at /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/pytest-dev__pytest-7490/env-build/Dockerfile has correct dependencies
3. The test framework is: pytest

After fixing, rebuild and verify:
  python scripts/build-env.py /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/pytest-dev__pytest-7490
  python scripts/check-env.py /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/pytest-dev__pytest-7490 --image swe-env:pytest-dev-pytest-7490

Save this plan to /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/pytest-dev__pytest-7490/plans/env-fix-plan.md