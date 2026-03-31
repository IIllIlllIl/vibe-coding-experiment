# Setup Complete - Current Workflow

## What Was Added

### 1. Fixed Docker Validation Workflow ✓
The experiment framework now separates **environment preparation** from **experiment execution**.

Current flow:
1. Build a fixed Docker image once with `scripts/build-env.py`
2. Verify that image with `scripts/check-env.py`
3. Reuse the same image across repeated runs with `scripts/run-experiment.py`
4. Reuse that same validated image across multiple plans with `scripts/run-multi-plan.py`

This makes validation reproducible across:
- different runs within one batch
- different invocations of the run script
- different plans for the same task

### 2. Scripts Available ✓
- **scripts/build-env.py** — build a reusable Docker validation image for an experiment
- **scripts/check-env.py** — run environment self-check using `test_patch` and `gold_patch`
- **scripts/run-experiment.py** — run Claude Code and validate inside the fixed Docker image
- **scripts/run-multi-plan.py** — orchestrate multi-plan execution and comparative analysis
- **scripts/verify-setup.py** — verify general framework setup
- **scripts/list-swe-tasks.py** — list available SWE-bench tasks

### 3. New Runner Capabilities ✓
`run-experiment.py` now supports:
- `--plan-file` — choose which plan file to execute
- `--runs-dir` — choose where `run-NNN/` artifacts are written
- `--analysis-dir` — choose where summaries are written
- summary rebuild from existing `runs/` contents, which enables resume-friendly aggregation

### 4. Experiment Artifacts ✓
For `experiments/exp-001-django-10924/`, the workflow now produces:
- `env-image.txt` — saved Docker image tag
- `env-check.json` — environment self-check result
- `results/plan-XX/runs/run-NNN/validation-results.json` — per-run Docker validation result
- `results/plan-XX/analysis/runs-summary.json` — per-plan aggregated run summary
- `comparative-analysis/comparison-summary.json` — cross-plan comparison summary
- `comparative-analysis/comparison-report.txt` — readable cross-plan report

## Current Directory Structure

```text
vibe-coding-experiment/
├── README.md
├── scripts/
│   ├── build-env.py
│   ├── check-env.py
│   ├── run-experiment.py
│   ├── run-multi-plan.py
│   ├── get-task-details.py
│   ├── list-swe-tasks.py
│   ├── list-featbench-tasks.py
│   └── verify-setup.py
├── docs/
│   └── SETUP_COMPLETE.md
├── datasets/
│   └── swe-bench/
└── experiments/
    └── exp-001-django-10924/
        ├── plan.md
        ├── plans/
        │   ├── plan-01.md
        │   ├── plan-02.md
        │   └── ...
        ├── task_full.json
        ├── base-commit.txt
        ├── repo/
        ├── env-image.txt
        ├── env-check.json
        ├── runs/                  # legacy single-plan output
        ├── analysis/              # legacy single-plan output
        ├── results/
        │   ├── plan-01/
        │   │   ├── plan.md
        │   │   ├── runs/
        │   │   └── analysis/
        │   └── plan-02/
        └── comparative-analysis/
```

## Recommended Execution Steps

### Step 1: Build the validation image

```bash
python scripts/build-env.py experiments/exp-001-django-10924
```

Expected output:
- Docker image built successfully
- image tag written to `experiments/exp-001-django-10924/env-image.txt`

### Step 2: Verify the environment

```bash
python scripts/check-env.py experiments/exp-001-django-10924 --image swe-env:django-django-10924
```

Expected behavior:
- `base + test_patch`: `FAIL_TO_PASS` fails and `PASS_TO_PASS` passes
- `base + test_patch + gold_patch`: both pass

Expected artifact:
- `experiments/exp-001-django-10924/env-check.json`

### Step 3: Prepare the plan set

```bash
cd experiments/exp-001-django-10924
mkdir -p plans
cp plan.md plans/plan-01.md
# Add plan-02.md, plan-03.md, ... manually
```

Notes:
- `plan-01.md` is usually the current baseline plan
- `plan-02.md` can be an alternative manually written plan
- In the current smoke test, `plan-02.md` was temporarily created by copying `plan.md`; replace it with a real alternative before large-scale experiments

### Step 4: Run repeated experiments

#### Single-plan mode

```bash
python scripts/run-experiment.py experiments/exp-001-django-10924 \
  --validation-image swe-env:django-django-10924 --runs 10
```

#### Multi-plan mode

```bash
python scripts/run-multi-plan.py experiments/exp-001-django-10924
```

Useful variants:

```bash
# Only selected plans
python scripts/run-multi-plan.py experiments/exp-001-django-10924 --plans 01 02 03

# Smoke test
python scripts/run-multi-plan.py experiments/exp-001-django-10924 --plans 01 02 --runs 1

# Dry run
python scripts/run-multi-plan.py experiments/exp-001-django-10924 --plans 01 02 --runs 1 --dry-run

# Force rebuild environment first
python scripts/run-multi-plan.py experiments/exp-001-django-10924 --rebuild-env
```

### Step 5: Resume behavior

- If `results/plan-XX/analysis/runs-summary.json` already exists, that plan is skipped
- If a plan has only some `run-NNN/` directories, the runner detects the missing run numbers and only fills those gaps
- `run-experiment.py` rebuilds its summary from the full target `runs_dir`, so summaries stay complete after interrupted executions

## Verification Performed

The new multi-plan workflow has been verified on `exp-001-django-10924` with:
- `python scripts/run-experiment.py --help`
- `python scripts/run-multi-plan.py --help`
- single-plan dry-run with default paths
- single-plan dry-run with custom `--plan-file --runs-dir --analysis-dir`
- multi-plan dry-run with `--plans 01 02 --runs 1`
- real smoke test with `--plans 01 02 --runs 1`

Verified artifacts:
- `experiments/exp-001-django-10924/results/plan-01/analysis/runs-summary.json`
- `experiments/exp-001-django-10924/results/plan-02/analysis/runs-summary.json`
- `experiments/exp-001-django-10924/comparative-analysis/comparison-summary.json`
- `experiments/exp-001-django-10924/comparative-analysis/comparison-report.txt`

## Current Status

For `exp-001-django-10924`:
- ✓ Docker image built
- ✓ Environment self-check passed
- ✓ End-to-end single run passed with Docker validation
- ✓ Multi-plan smoke test passed for `plan-01` and `plan-02`
- ✓ Cross-plan comparison artifacts were generated successfully

The experiment is ready for larger multi-plan runs with the fixed image.
