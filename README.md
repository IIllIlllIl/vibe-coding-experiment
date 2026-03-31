# Vibe Coding Experiment Framework

This project studies **execution variability in Claude Code** when given fixed plans. We aim to understand how deterministic Claude Code's execution is when provided with identical instructions across multiple runs.

## Experiment Methodology

### Fixed Plan Approach
- We use **fixed, detailed plans** derived from SWE-bench tasks as input
- Each plan is executed multiple times (n=10) with identical conditions
- Each run gets a fresh working copy of the target repository at the base commit
- Validation runs inside a **fixed Docker image** prepared outside the run loop

### Multi-Plan Approach
- A single task can now include multiple candidate plans under `plans/plan-XX.md`
- Each plan gets its own isolated result root under `results/plan-XX/`
- After all plans finish, the framework writes a cross-plan comparison under `comparative-analysis/`
- This makes it possible to compare both **within-plan variability** and **between-plan variability**

### Controlled Variables
- **Fixed plan**: Identical instructions for each run of the same plan
- **Fixed model settings**: Same Claude Code version, model
- **Isolation**: Each run operates on an independent copy of the repository
- **Permission mode**: `acceptEdits` — allows Claude to write files without prompting
- **Validation environment**: Same Docker image reused across runs

### Measured Variables
- Execution status (success / timeout / no_changes / partial / failed)
- Code changes produced (diff size, files modified)
- Validation correctness (functional score, regression score)
- Duration and token usage

### Run Status Classification

Each run is classified by combining exit code, diff output, and validation results:

| Status | Meaning |
|--------|---------|
| `success` | exit=0, code produced, validation passed |
| `success_timeout` | timed out, but code is correct and validation passed |
| `success_with_error` | exit!=0, but code is correct and validation passed |
| `partial` | code produced, validation not fully passed |
| `no_changes` | exit=0 but no code changes (environment/permission issue) |
| `failed` | no useful output |

## Project Structure

```text
vibe-coding-experiment/
├── README.md
├── requirements.txt          # Python dependencies
├── .env.example              # Required environment variables
├── .gitignore
├── scripts/
│   ├── run-experiment.py     # Single-plan runner (now supports custom plan/output paths)
│   ├── run-multi-plan.py     # Multi-plan orchestrator
│   ├── build-env.py          # Build fixed Docker validation image
│   ├── check-env.py          # Validate image with test_patch + gold_patch
│   ├── get-task-details.py   # Fetch task from SWE-bench dataset
│   ├── list-swe-tasks.py     # List available SWE-bench tasks
│   ├── list-featbench-tasks.py
│   └── verify-setup.py       # Check environment prerequisites
├── datasets/
│   └── swe-bench/            # SWE-bench (vendored)
├── experiments/              # Experiment data
│   └── exp-001-django-10924/
│       ├── plan.md           # Legacy single-plan entrypoint (still supported)
│       ├── plans/            # Multi-plan inputs
│       │   ├── plan-01.md
│       │   ├── plan-02.md
│       │   └── ...
│       ├── task_full.json    # SWE-bench task metadata
│       ├── base-commit.txt   # Git commit to checkout
│       ├── repo/             # Target repo snapshot
│       ├── env-image.txt     # Fixed Docker image tag used for validation
│       ├── env-check.json    # Environment self-check results
│       ├── runs/             # Legacy single-plan run outputs
│       ├── analysis/         # Legacy single-plan aggregated results
│       ├── results/          # Per-plan outputs
│       │   ├── plan-01/
│       │   │   ├── plan.md
│       │   │   ├── runs/
│       │   │   └── analysis/
│       │   └── plan-02/
│       └── comparative-analysis/
│           ├── comparison-summary.json
│           └── comparison-report.txt
└── docs/
    └── SETUP_COMPLETE.md
```

## Setup

### Prerequisites

- Python 3.10+
- Docker
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated (`claude` in PATH)
- Git

### 1. Clone and Install

```bash
git clone <repo-url>
cd vibe-coding-experiment
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY
```

### 3. Prepare an Experiment

Each experiment directory under `experiments/` needs:
- `task_full.json` — SWE-bench task metadata (use `get-task-details.py` to generate)
- `plan.md` — fixed implementation plan for legacy single-plan runs
- `base-commit.txt` — target commit hash
- `repo/` — repository checked out at the target base commit

To fetch a task from SWE-bench:

```bash
python scripts/get-task-details.py django__django-10924
```

Clone the target repository into the experiment directory:

```bash
cd experiments/exp-001-django-10924
git clone https://github.com/django/django.git repo
cd repo && git checkout bceadd2788dc2dad53eba0caae172bd8522fd483
```

For multi-plan experiments, prepare the plan set:

```bash
cd experiments/exp-001-django-10924
mkdir -p plans
cp plan.md plans/plan-01.md
# Then add plan-02.md, plan-03.md, ... manually
```

Notes:
- `plan-01.md` is typically the current baseline plan
- `plan-02.md` and later are alternative plan variants for comparison
- During development, you can temporarily duplicate `plan-01.md` into `plan-02.md` to smoke-test the workflow

### 4. Build and Validate the Docker Environment

Build the reusable validation image once:

```bash
python scripts/build-env.py experiments/exp-001-django-10924
```

This writes the image tag to:
- `experiments/exp-001-django-10924/env-image.txt`

Validate the environment before running Claude:

```bash
python scripts/check-env.py experiments/exp-001-django-10924 --image swe-env:django-django-10924
```

Expected behavior:
- `base + test_patch`: `FAIL_TO_PASS` should fail, `PASS_TO_PASS` should pass
- `base + test_patch + gold_patch`: both should pass

The full check result is saved to:
- `experiments/exp-001-django-10924/env-check.json`

### 5. Run the Experiment

#### Single-plan mode

```bash
# Single run
python scripts/run-experiment.py experiments/exp-001-django-10924 \
  --validation-image swe-env:django-django-10924

# 10 runs starting from run #1
python scripts/run-experiment.py experiments/exp-001-django-10924 \
  --validation-image swe-env:django-django-10924 --runs 10

# 5 runs starting from run #11
python scripts/run-experiment.py experiments/exp-001-django-10924 \
  --validation-image swe-env:django-django-10924 --runs 5 --start 11

# Dry run
python scripts/run-experiment.py experiments/exp-001-django-10924 --dry-run
```

#### Single-plan mode with custom plan/output paths

```bash
python scripts/run-experiment.py experiments/exp-001-django-10924 \
  --plan-file experiments/exp-001-django-10924/plans/plan-01.md \
  --runs-dir experiments/exp-001-django-10924/results/plan-01/runs \
  --analysis-dir experiments/exp-001-django-10924/results/plan-01/analysis \
  --validation-image swe-env:django-django-10924 \
  --runs 10
```

This is the interface used by the multi-plan orchestrator.

#### Multi-plan mode

```bash
# Run all plans found under plans/
python scripts/run-multi-plan.py experiments/exp-001-django-10924

# Run only specific plans
python scripts/run-multi-plan.py experiments/exp-001-django-10924 --plans 01 02 03

# Smoke test with 2 plans × 1 run
python scripts/run-multi-plan.py experiments/exp-001-django-10924 --plans 01 02 --runs 1

# Force rebuild environment
python scripts/run-multi-plan.py experiments/exp-001-django-10924 --rebuild-env

# Dry run
python scripts/run-multi-plan.py experiments/exp-001-django-10924 --plans 01 02 --runs 1 --dry-run
```

Notes:
- `run-experiment.py` no longer builds environments during execution
- Validation runs only inside the fixed Docker image
- If `--validation-image` is omitted, `run-experiment.py` can read `env-image.txt`
- `run-multi-plan.py` checks the Docker image once per invocation, then reuses it for all plans

### 6. Resume Semantics

- `run-experiment.py` now rebuilds `runs-summary.json` from everything already present under the target `runs_dir`
- `run-multi-plan.py` skips plans whose `results/plan-XX/analysis/runs-summary.json` already exists
- If a plan is partially complete, the orchestrator detects missing `run-NNN` directories and only runs the missing run numbers
- Each plan snapshot is copied to `results/plan-XX/plan.md` so outputs remain self-contained

### 7. Review Results

After single-plan execution, check:
- `experiments/<name>/analysis/runs-summary.json` — aggregated statistics and per-run status
- `experiments/<name>/analysis/summary.txt` — human-readable summary
- `experiments/<name>/runs/run-NNN/` — individual run artifacts:
  - `transcript.json` — Claude Code stdout/stderr
  - `final.diff` — code changes produced
  - `validation-results.json` — Docker validation results and correctness scores

After multi-plan execution, check:
- `experiments/<name>/results/plan-XX/analysis/runs-summary.json` — per-plan aggregated statistics
- `experiments/<name>/results/plan-XX/analysis/summary.txt` — per-plan readable summary
- `experiments/<name>/comparative-analysis/comparison-summary.json` — machine-readable cross-plan comparison
- `experiments/<name>/comparative-analysis/comparison-report.txt` — readable cross-plan report

## Verification Status

The new multi-plan workflow has been smoke-tested on `exp-001-django-10924` with:
- `plan-01.md` × 1 run
- `plan-02.md` × 1 run

Verified outputs:
- `experiments/exp-001-django-10924/results/plan-01/analysis/runs-summary.json`
- `experiments/exp-001-django-10924/results/plan-02/analysis/runs-summary.json`
- `experiments/exp-001-django-10924/comparative-analysis/comparison-summary.json`
- `experiments/exp-001-django-10924/comparative-analysis/comparison-report.txt`

## Research Questions

1. **Determinism**: Does Claude Code produce identical results given identical plans?
2. **Variability**: When results differ, what are the nature and magnitude of differences?
3. **Failure Modes**: Are certain types of tasks more prone to variability?
4. **Recovery Patterns**: How does Claude Code recover from errors differently across runs?

## License

MIT License

## Acknowledgments

- [SWE-bench](https://www.swebench.com/) — benchmark for evaluating code generation
- [FeatBench](https://github.com/TsinghuaSE/FeatBench) — feature implementation benchmark
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) by Anthropic
