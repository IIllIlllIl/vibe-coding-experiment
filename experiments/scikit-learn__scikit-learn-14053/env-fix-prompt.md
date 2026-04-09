/plan Fix the Docker test environment for scikit-learn__scikit-learn-14053.

Repo: scikit-learn/scikit-learn (version 0.22)
Docker image: swe-env:scikit-learn-scikit-learn-14053

The environment check failed:
  test_patch_only: exit_code=4, 0 passed, 0 failed
  test_patch_plus_gold_patch: exit_code=4, 0 passed, 0 failed

Key issues to investigate:
1. Check the test output in experiments/scikit-learn__scikit-learn-14053/env-check.json for errors
2. Check if the Dockerfile at experiments/scikit-learn__scikit-learn-14053/env-build/Dockerfile has correct dependencies
3. The test framework is: unknown

After fixing, rebuild and verify:
  python scripts/build-env.py experiments/scikit-learn__scikit-learn-14053
  python scripts/check-env.py experiments/scikit-learn__scikit-learn-14053 --image swe-env:scikit-learn-scikit-learn-14053

Save this plan to experiments/scikit-learn__scikit-learn-14053/plans/env-fix-plan.md