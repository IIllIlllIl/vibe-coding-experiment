# Task Selection Rationale

> Generated: 2026-03-31 14:03 UTC

## 1. Overview

| Metric | Value |
|--------|------:|
| SWE-bench Verified total tasks | 500 |
| Tasks passing exclusion filter | 500 |
| Tasks excluded | 0 |
| **Tasks selected** | **30** |
| Random seed | `42` |

## 2. Random Seed & Reproducibility

All random shuffling uses Python's `random.Random(42)`. This ensures the selection is fully deterministic and reproducible. Changing the seed would produce a different 30-task subset, but the stratified sampling constraints (repo coverage, difficulty, type) would still hold.

## 3. Exclusion Criteria

The following exclusion filters are applied before selection:

| Filter | Description | Excluded |
|--------|-------------|--------:|
| `empty_fail_to_pass` | Tasks with no FAIL_TO_PASS test cases | 0 |
| `empty_gold_patch` | Tasks with empty or missing gold patch | 0 |
| `insufficient_problem_statement` | Tasks with problem statement < 50 chars | 0 |

**Total excluded: 0 / 500** (0.0%)

## 4. Repository Distribution

### Allocation Rule

Each of the 12 repositories in SWE-bench Verified receives 1-4 tasks, proportional to its available task count (capped at 4). Total = 30.

| Repository | Available | Target | Selected | Coverage |
|------------|--------:|-------:|--------:|----------|
| astropy | 22 | 2 | 2 | 100% |
| django | 231 | 4 | 4 | 100% |
| flask | 1 | 1 | 1 | 100% |
| matplotlib | 34 | 3 | 3 | 100% |
| pylint | 10 | 2 | 2 | 100% |
| pytest | 19 | 2 | 2 | 100% |
| requests | 8 | 2 | 2 | 100% |
| scikit-learn | 32 | 3 | 3 | 100% |
| seaborn | 2 | 2 | 2 | 100% |
| sphinx | 44 | 3 | 3 | 100% |
| sympy | 75 | 4 | 4 | 100% |
| xarray | 22 | 2 | 2 | 100% |
| **Total** | **500** | **30** | **30** | **100%** |

### Original vs Selected
```
  astropy         █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  22  ->  ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░  2
  django          ██████████████░░░░░░░░░░░░░░░░ 231  ->  ████░░░░░░░░░░░░░░░░░░░░░░░░░░  4
  flask           ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   1  ->  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  1
  matplotlib      ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░  34  ->  ███░░░░░░░░░░░░░░░░░░░░░░░░░░░  3
  pylint          █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  10  ->  ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░  2
  pytest          █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  19  ->  ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░  2
  requests        ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   8  ->  ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░  2
  scikit-learn    ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░  32  ->  ███░░░░░░░░░░░░░░░░░░░░░░░░░░░  3
  seaborn         ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   2  ->  ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░  2
  sphinx          ███░░░░░░░░░░░░░░░░░░░░░░░░░░░  44  ->  ███░░░░░░░░░░░░░░░░░░░░░░░░░░░  3
  sympy           ████░░░░░░░░░░░░░░░░░░░░░░░░░░  75  ->  ████░░░░░░░░░░░░░░░░░░░░░░░░░░  4
  xarray          █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  22  ->  ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░  2
```

## 5. Difficulty Distribution

### Classification Rules

- **Easy**: 1 file modified, < 20 lines changed
- **Medium**: 2-3 files modified, or 20-50 lines changed
- **Hard**: >= 4 files modified, or > 50 lines changed

#### Original Pool vs Selected

| Category | Original | | Selected | |
|----------|---------:|------|---------:|------|
| easy       |  414 ( 83%) | █████████████████░░░ |   13 ( 43%) | █████████░░░░░░░░░░░ |
| medium     |   71 ( 14%) | ███░░░░░░░░░░░░░░░░░ |   15 ( 50%) | ██████████░░░░░░░░░░ |
| hard       |   15 (  3%) | █░░░░░░░░░░░░░░░░░░░ |    2 (  7%) | █░░░░░░░░░░░░░░░░░░░ |

**Target**: Easy 30% (9), Medium 50% (15), Hard 20% (6)

> **Note**: The actual difficulty distribution is constrained by the available tasks in each repository. Repositories with fewer available tasks may not have enough hard candidates, shifting the distribution toward easy/medium.

## 6. Task Type Distribution

### Classification Method

Task types are inferred via keyword matching on `problem_statement` and `hints_text`:
- **Feature**: Contains keywords like `add support`, `implement`, `new feature`, `allow`
- **Refactor**: Contains keywords like `refactor`, `deprecate`, `remove`, `rename`
- **Bug Fix**: Default category when neither feature nor refactor signals are strong enough

#### Original Pool vs Selected

| Category | Original | | Selected | |
|----------|---------:|------|---------:|------|
| bug_fix    |  285 ( 57%) | ███████████░░░░░░░░░ |   13 ( 43%) | █████████░░░░░░░░░░░ |
| feature    |  149 ( 30%) | ██████░░░░░░░░░░░░░░ |   14 ( 47%) | █████████░░░░░░░░░░░ |
| refactor   |   66 ( 13%) | ███░░░░░░░░░░░░░░░░░ |    3 ( 10%) | ██░░░░░░░░░░░░░░░░░░ |

**Target**: Bug Fix 45-50% (14), Feature 30-35% (10), Refactor 15-20% (6)

> **Note**: Keyword-based classification is an approximation. Some tasks may be misclassified. The method is kept simple and deterministic for reproducibility.

## 7. Selected Task List

| # | Instance ID | Repo | Type | Difficulty | Files | Lines |
|--:|-------------|------|------|------------|------:|------:|
| 1 | `django__django-11951` | django | bug_fix | easy | 1 | 2 |
| 2 | `django__django-12155` | django | feature | medium | 2 | 13 |
| 3 | `django__django-13128` | django | bug_fix | medium | 1 | 22 |
| 4 | `django__django-16263` | django | bug_fix | hard | 4 | 50 |
| 5 | `sympy__sympy-12481` | sympy | bug_fix | easy | 1 | 5 |
| 6 | `sympy__sympy-24443` | sympy | bug_fix | medium | 1 | 28 |
| 7 | `sympy__sympy-20438` | sympy | refactor | medium | 3 | 13 |
| 8 | `sympy__sympy-16597` | sympy | feature | hard | 6 | 41 |
| 9 | `sphinx-doc__sphinx-9258` | sphinx | feature | easy | 1 | 2 |
| 10 | `sphinx-doc__sphinx-10673` | sphinx | feature | medium | 3 | 16 |
| 11 | `sphinx-doc__sphinx-8548` | sphinx | feature | medium | 2 | 27 |
| 12 | `matplotlib__matplotlib-25332` | matplotlib | bug_fix | easy | 1 | 7 |
| 13 | `matplotlib__matplotlib-25479` | matplotlib | refactor | medium | 2 | 5 |
| 14 | `matplotlib__matplotlib-24870` | matplotlib | bug_fix | medium | 2 | 18 |
| 15 | `scikit-learn__scikit-learn-14053` | scikit-learn | feature | easy | 1 | 2 |
| 16 | `scikit-learn__scikit-learn-25102` | scikit-learn | feature | medium | 2 | 16 |
| 17 | `scikit-learn__scikit-learn-12682` | scikit-learn | bug_fix | medium | 2 | 47 |
| 18 | `astropy__astropy-8872` | astropy | feature | easy | 1 | 6 |
| 19 | `astropy__astropy-13977` | astropy | feature | medium | 1 | 48 |
| 20 | `pydata__xarray-4629` | xarray | bug_fix | easy | 1 | 2 |
| 21 | `pydata__xarray-3305` | xarray | bug_fix | medium | 2 | 13 |
| 22 | `pytest-dev__pytest-7490` | pytest | refactor | easy | 1 | 11 |
| 23 | `pytest-dev__pytest-8399` | pytest | feature | medium | 2 | 7 |
| 24 | `pylint-dev__pylint-4970` | pylint | feature | easy | 1 | 2 |
| 25 | `pylint-dev__pylint-6528` | pylint | feature | medium | 2 | 19 |
| 26 | `psf__requests-1766` | requests | feature | easy | 1 | 3 |
| 27 | `psf__requests-1724` | requests | bug_fix | easy | 1 | 3 |
| 28 | `mwaskom__seaborn-3069` | seaborn | feature | easy | 1 | 8 |
| 29 | `mwaskom__seaborn-3187` | seaborn | bug_fix | medium | 2 | 8 |
| 30 | `pallets__flask-5014` | flask | bug_fix | easy | 1 | 2 |

## 8. Methodology Summary

1. **Load** SWE-bench Verified (500 tasks, 12 repositories)
2. **Filter** by exclusion criteria (non-viable tasks removed)
3. **Annotate** each task with difficulty (patch size) and type (keyword matching)
4. **Shuffle** candidates per repository using `random.Random(42)`
5. **Stratify** by difficulty within each repository, proportional to global targets
6. **Fill** remaining slots from any difficulty level within the same repository
7. **Output** `selected-tasks.json`, `selection-report.txt`, and this file

