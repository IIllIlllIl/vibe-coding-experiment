# Vibe Coding Experiment Framework

This project studies **execution variability in Claude Code** when given fixed plans. We aim to understand how deterministic Claude Code's execution is when provided with identical instructions across multiple runs.

## Experiment Methodology

### Fixed Plan Approach
- We use **fixed, detailed plans** derived from SWE-bench tasks as input
- Each plan is executed multiple times with identical conditions
- Each run gets a fresh working copy of the target repository at the base commit
- Validation runs inside a **fixed Docker image** prepared outside the run loop

### Multi-Plan Approach
- A single task can include multiple candidate plans under `plans/plan-XX.md`
- Each plan gets its own isolated result root under `results/plan-XX/`
- After all plans finish, the framework writes a cross-plan comparison under `comparative-analysis/`

### Multi-Task Approach
- Experiments run across **30 representative tasks** selected from SWE-bench Verified (500 tasks, 12 repositories)
- Each task gets 5 manually created plans, each plan executed 5 times
- Batch orchestration handles setup, Docker build, execution, and result aggregation
- Supports resume: skips completed plans and fills missing runs

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

```
vibe-coding-experiment/
├── README.md
├── requirements.txt          # Python dependencies
├── .env.example              # Required environment variables
├── .gitignore
├── scripts/
│   ├── run-experiment.py      # Single-plan runner
│   ├── run-multi-plan.py      # Multi-plan orchestrator (single task)
│   ├── run-batch.py            # Batch runner across multiple tasks
│   ├── build-env.py           # Build Docker validation image
│   ├── check-env.py           # Validate image with test_patch + gold_patch
│   ├── setup-task.py          # Clone repo and set up experiment directory
│   ├── download-verified.py   # Download SWE-bench Verified dataset
│   ├── select-tasks.py        # Select 30 representative tasks
│   ├── get-task-details.py    # Fetch task from SWE-bench dataset
│   ├── list-swe-tasks.py      # List available SWE-bench tasks
│   ├── list-featbench-tasks.py
│   └── verify-setup.py        # Check environment prerequisites
├── datasets/
│   ├── swe-bench-verified/    # SWE-bench Verified dataset
│   │   ├── data.json           # Full dataset (500 tasks)
│   │   ├── metadata.json       # Dataset statistics
│   │   ├── selected-tasks.json # 30 selected tasks with metadata
│   │   ├── selection-report.txt
│   │   └── selection-rationale.md
│   └── swe-bench/             # SWE-bench (vendored)
├── experiments/               # Experiment data
│   ├── exp-001-django-10924/   # Pilot experiment (Django)
│   │   ├── plans/              # Manually created plans
│   │   ├── results/            # Per-plan run outputs
│   │   ├── repo/               # Target repo snapshot
│   │   ├── task_full.json      # Task metadata
│   │   └── ...
│   ├── <instance_id>/          # One directory per SWE-bench task
│   │   ├── plans/              # 5 plan files (manually created)
│   │   ├── results/            # Execution results
│   │   ├── repo/               # Cloned at base_commit
│   │   └── task_full.json
│   └── batch-summary.json      # Batch execution summary
└── docs/
    └── SETUP_COMPLETE.md
```

## Task Selection

From SWE-bench Verified (500 tasks, 12 repos), we select 30 tasks via stratified sampling:

| Repository | Selected | Total Available |
|------------|----------|----------------|
| django | 4 | 231 |
| sympy | 4 | 75 |
| sphinx | 3 | 44 |
| matplotlib | 3 | 34 |
| scikit-learn | 3 | 32 |
| astropy | 2 | 22 |
| xarray | 2 | 22 |
| pytest | 2 | 19 |
| pylint | 2 | 10 |
| requests | 2 | 8 |
| seaborn | 2 | 2 |
| flask | 1 | 1 |
| **Total** | **30** | **500** |

Selection criteria: repo coverage (1-4 each), difficulty stratification (easy/medium/hard), type balance (bug_fix/feature/refactor), fixed random seed (42). See `datasets/swe-bench-verified/selection-rationale.md` for details.

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

### 3. Download Dataset and Select Tasks

```bash
# Download SWE-bench Verified (500 tasks)
python scripts/download-verified.py

# Select 30 representative tasks
python scripts/select-tasks.py --output-dir datasets/swe-bench-verified
```

### 4. Set Up Experiment Directories

```bash
# Set up all 30 tasks (clone repos, create directory structure)
python scripts/setup-task.py --dataset datasets/swe-bench-verified/data.json \
  $(python -c "import json; ids=[t['instance_id'] for t in json.loads(open('datasets/swe-bench-verified/selected-tasks.json').read())['tasks']]; print(' '.join(ids))")

# Or set up specific tasks
python scripts/setup-task.py django__django-11951 sympy__sympy-12481
```

### 5. Create Plans (Manual Step)

For each task, create 5 plan files in `experiments/<instance_id>/plans/`:

```
experiments/django__django-11951/
└── plans/
    ├── plan-01.md
    ├── plan-02.md
    ├── plan-03.md
    ├── plan-04.md
    └── plan-05.md
```

### 6. Build and Validate Docker Images

```bash
# Build for a specific task
python scripts/build-env.py experiments/django__django-11951

# Validate the environment
python scripts/check-env.py experiments/django__django-11951 --image swe-env:django-django-11951
```

### 7. Run Experiments

#### Single task (multi-plan)

```bash
# Run all plans for one task, 5 runs each
python scripts/run-multi-plan.py experiments/django__django-11951 --runs 5
```

#### Batch (all tasks)

```bash
# Dry run to preview what will happen
python scripts/run-batch.py --dry-run --runs 5

# Run all tasks with 5 plans x 5 runs
python scripts/run-batch.py --runs 5

# Run only specific tasks
python scripts/run-batch.py --runs 5 --only django__django-11951 sympy__sympy-12481

# Force rebuild Docker images
python scripts/run-batch.py --runs 5 --rebuild-env
```

### 8. Review Results

After single-plan execution, check:
- `experiments/<name>/analysis/runs-summary.json` — aggregated statistics
- `experiments/<name>/analysis/summary.txt` — human-readable summary

After multi-plan execution, check:
- `experiments/<name>/results/plan-XX/analysis/runs-summary.json` — per-plan stats
- `experiments/<name>/comparative-analysis/comparison-summary.json` — cross-plan comparison

After batch execution, check:
- `experiments/batch-summary.json` — all tasks summary

### Resume Semantics

- `run-experiment.py` rebuilds `runs-summary.json` from everything already present under the target `runs_dir`
- `run-multi-plan.py` skips plans whose `results/plan-XX/analysis/runs-summary.json` already exists
- If a plan is partially complete, the orchestrator detects missing `run-NNN` directories and only runs the missing run numbers
- `run-batch.py` skips tasks with no experiment directory or no plan files
- Each plan snapshot is copied to `results/plan-XX/plan.md` so outputs remain self-contained

## Research Questions

1. **Determinism**: Does Claude Code produce identical results given identical plans?
2. **Variability**: When results differ, what are the nature and magnitude of differences?
3. **Failure Modes**: Are certain types of tasks more prone to variability?
4. **Recovery Patterns**: How does Claude Code recover from errors differently across runs?

## License

MIT License

## Acknowledgments

- [SWE-bench](https://www.swebench.com/) — benchmark for evaluating code generation
- [SWE-bench Verified](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified) — curated subset of SWE-bench
- [FeatBench](https://github.com/TsinghuaSE/FeatBench) — feature implementation benchmark
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) by Anthropic
