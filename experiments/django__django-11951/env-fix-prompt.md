/plan Fix the Docker test environment for django__django-11951.

Repo: django/django (version 3.1)
Docker image: swe-env:django-django-11951

The environment check failed:
  test_patch_only: exit_code=1, 18 passed, 1 failed

Key issues to investigate:
1. Check the test output in /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/django__django-11951/env-check.json for errors
2. Check if the Dockerfile at /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/django__django-11951/env-build/Dockerfile has correct dependencies
3. The test framework is: django

After fixing, rebuild and verify:
  python scripts/build-env.py /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/django__django-11951
  python scripts/check-env.py /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/django__django-11951 --image swe-env:django-django-11951

Save this plan to /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/django__django-11951/plans/env-fix-plan.md