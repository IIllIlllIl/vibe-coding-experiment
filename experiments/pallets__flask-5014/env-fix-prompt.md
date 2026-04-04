/plan Fix the Docker test environment for pallets__flask-5014.

Repo: pallets/flask (version 2.3)
Docker image: swe-env:pallets-flask-5014

The environment check failed:
  test_patch_only: exit_code=1, 11 passed, 91 failed
  test_patch_plus_gold_patch: exit_code=1, 11 passed, 91 failed

Key issues to investigate:
1. Check the test output in /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/pallets__flask-5014/env-check.json for errors
2. Check if the Dockerfile at /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/pallets__flask-5014/env-build/Dockerfile has correct dependencies
3. The test framework is: pytest

After fixing, rebuild and verify:
  python scripts/build-env.py /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/pallets__flask-5014
  python scripts/check-env.py /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/pallets__flask-5014 --image swe-env:pallets-flask-5014

Save this plan to /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/pallets__flask-5014/plans/env-fix-plan.md