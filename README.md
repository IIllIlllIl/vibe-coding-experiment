# Vibe Coding Experiment Framework

> **Project Status: Research Prototype**
> This code supports the "Fixed-Plan Claude Code Execution Variability" experiment. It is **not** production-grade software: there are no unit tests, no logging framework, and dependency versions are loosely pinned. Known limitations are listed in the [Known Issues](#known-issues) section below.

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
- **Permission mode**: configurable (`acceptEdits` by default; `bypassPermissions` for Docker execution)
- **Validation environment**: Same Docker image reused across runs
- **Unified image**: Official SWE-bench instance image extended with Node.js + Claude CLI (single image for both generation and validation)

### Measured Variables
- Execution status (success / timeout / no_changes / partial / failed)
- Code changes produced (diff size, files modified)
- Validation correctness (functional score, regression score)
- Duration (extracted from `transcript.json` `duration_ms`, not file mtime)
- Token usage: `input_tokens`, `output_tokens`, `cache_read_input_tokens` (reported separately due to different pricing)

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

### Validation Pipeline

Each run's output is validated using the official SWE-bench `run_instance()` function inside a Docker container:

1. **Capture Claude's diff**: After Claude Code finishes, all changes (including new untracked files) are captured via `git add -A && git diff --cached` to produce `final.diff`.
2. **Official evaluation**: `run_instance()` applies the model patch (`final.diff`), runs `eval.sh` (which applies `test_patch`, executes the test suite, then reverts `test_patch`), and grades results using official repo-specific parsers.
3. **Report conversion**: The official `report.json` is converted to our `validation-results.json` schema, preserving `correctness.{functional, regression, overall}` scores and per-test pass/fail status.

## Project Structure

```
vibe-coding-experiment/
├── README.md
├── requirements.txt          # Python dependencies
├── .env.example              # Required environment variables
├── .gitignore
├── scripts/
│   ├── run-experiment.py      # Single-plan runner (Docker execution, --revalidate)
│   ├── run-multi-plan.py      # Multi-plan orchestrator (single task)
│   ├── run-batch.py            # Batch runner across multiple tasks
│   ├── build-env.py           # Build unified Docker image (official SWE-bench base + Claude CLI)
│   ├── check-env.py           # Validate image with smoke test
│   ├── setup-task.py          # Clone repo and set up experiment directory
│   ├── download-verified.py   # Download SWE-bench Verified dataset
│   ├── select-tasks.py        # Select 30 representative tasks
│   ├── get-task-details.py    # Fetch task from SWE-bench dataset
│   ├── list-swe-tasks.py      # List available SWE-bench tasks
│   ├── list-featbench-tasks.py
│   ├── make-plan-prompts.py   # Batch-generate plan prompts for tasks
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
│   ├── django__django-11951/  # SWE-bench task (naming: <repo>__<repo>-<issue>)
│   │   ├── plans/              # 5 plan files (manually created)
│   │   │   ├── plan-01.md
│   │   │   ├── ...
│   │   │   └── plan-05.md
│   │   ├── results/            # Current experiment results
│   │   │   ├── plan-XX/
│   │   │   │   ├── plan.md          # Snapshot of plan used
│   │   │   │   ├── analysis/        # Aggregated run statistics
│   │   │   │   │   ├── runs-summary.json
│   │   │   │   │   └── summary.txt
│   │   │   │   └── runs/
│   │   │   │       └── run-NNN/
│   │   │   │           ├── final.diff              # Claude's changes (incl. new files)
│   │   │   │           ├── transcript.json         # Full Claude Code session (has duration_ms)
│   │   │   │           ├── changed-files.txt       # List of modified files
│   │   │   │           ├── commit-info.txt         # Base commit hash
│   │   │   │           ├── run-meta.json           # Execution metadata (start/end time, exit_code)
│   │   │   │           └── validation-results.json # Test results + diff_exclusions
│   │   ├── results-v1-host/   # Archived: earlier experiment round
│   │   │   └── plan-XX/       # (same structure as results/)
│   │   ├── comparative-analysis/  # Cross-plan comparison
│   │   │   ├── comparison-summary.json
│   │   │   └── comparison-report.txt
│   │   ├── repo/               # Target repo snapshot (gitignored)
│   │   ├── task_full.json      # SWE-bench task metadata
│   │   ├── base-commit.txt     # Base commit hash
│   │   ├── env-image.txt       # Docker image tag
│   │   └── plan-prompt.md      # Prompt template for plan generation
│   ├── pytest-dev__pytest-7490/   # (same structure)
│   ├── exp-001-django-10924/      # Pilot experiment (legacy naming)
│   └── batch-summary.json         # Batch execution summary
└── docs/
    ├── SETUP_COMPLETE.md
    └── RECONSTRUCTION_GUIDE.md
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
# Build unified image for a specific task (official SWE-bench base + Claude CLI)
python scripts/build-env.py experiments/django__django-11951 --use-official-base

# Force rebuild all layers
python scripts/build-env.py experiments/django__django-11951 --use-official-base --rebuild

# Validate the environment (smoke test: image exists + package importable)
python scripts/check-env.py experiments/django__django-11951 --image claude-swe-env:django-django-11951
```

A single unified Docker image serves both Claude Code execution and test validation:

| Image | Tag format | Purpose | Built by |
|-------|-----------|---------|----------|
| **Unified image** | `claude-swe-env:<task>` | Claude Code execution + official SWE-bench validation | `build-env.py --use-official-base` |

The unified image is built using the official SWE-bench 3-tier hierarchy (base → env → instance), then layers Node.js + Claude CLI on top. It is also tagged with the official image name (`sweb.eval.arm64.<task>:latest`) so `run_instance()` finds it without rebuilding.

The env check verifies:
- Docker image exists (auto-builds if missing)
- Main package is importable inside the container (smoke test)

### 7. Run Experiments

Claude Code runs inside a Docker container using the unified image. The API key (`ANTHROPIC_API_KEY`) is passed via a temporary env file (not exposed in `ps`). Resource limits can be set with `--docker-cpus` and `--docker-memory`.

#### Single task (multi-plan)

```bash
# Run all plans for one task, 5 runs each
python scripts/run-multi-plan.py experiments/django__django-11951 --runs 5

# Run with resource limits
python scripts/run-multi-plan.py experiments/django__django-11951 --runs 5 \
  --claude-permission-mode bypassPermissions --docker-cpus 2 --docker-memory 4g
```

#### Batch (all tasks)

```bash
# Dry run to preview what will happen
python scripts/run-batch.py --dry-run --runs 5

# Run all tasks with 5 plans x 5 runs
python scripts/run-batch.py --runs 5

# Run with resource limits
python scripts/run-batch.py --runs 5 \
  --claude-permission-mode bypassPermissions \
  --docker-cpus 2 --docker-memory 4g

# Run only specific tasks
python scripts/run-batch.py --runs 5 --only django__django-11951 sympy__sympy-12481

# Force rebuild Docker images
python scripts/run-batch.py --runs 5 --rebuild-env
```

#### CLI Reference

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--claude-permission-mode` | any valid mode | `acceptEdits` | Permission mode for Claude Code |
| `--docker-cpus` | e.g. `2` | none | CPU limit for container |
| `--docker-memory` | e.g. `4g` | none | Memory limit for container |
| `--revalidate` | flag | off | Re-run validation for existing runs and rebuild summary (does NOT re-run Claude) |
| `--keep-work` | flag | off | Keep `work/` and `validation/` directories after each run |

These flags are available in `run-experiment.py`, `run-multi-plan.py`, and `run-batch.py`.

### 8. Review Results

After single-plan execution, check:
- `experiments/<name>/analysis/runs-summary.json` — aggregated statistics
- `experiments/<name>/analysis/summary.txt` — human-readable summary

After multi-plan execution, check:
- `experiments/<name>/results/plan-XX/analysis/runs-summary.json` — per-plan stats
- `experiments/<name>/comparative-analysis/comparison-summary.json` — cross-plan comparison

After batch execution, check:
- `experiments/batch-summary.json` — all tasks summary

### 9. Revalidate Existing Runs

If the validation pipeline is updated, you can re-run validation for all existing runs without re-running Claude:

```bash
# Revalidate all plans for one task
for plan in plan-01 plan-02 plan-03 plan-04 plan-05; do
  python scripts/run-experiment.py experiments/django__django-11951 \
    --revalidate \
    --validation-image claude-swe-env:django-django-11951 \
    --runs-dir experiments/django__django-11951/results/$plan/runs \
    --analysis-dir experiments/django__django-11951/results/$plan/analysis
done

# Rebuild summaries only (no Docker validation)
python scripts/run-experiment.py experiments/django__django-11951 \
  --runs 0 --plan-file experiments/django__django-11951/plans/plan-01.md \
  --runs-dir experiments/django__django-11951/results/plan-01/runs \
  --analysis-dir experiments/django__django-11951/results/plan-01/analysis \
  --validation-image claude-swe-env:django-django-11951
```

### Resume Semantics

- `run-experiment.py` rebuilds `runs-summary.json` from everything already present under the target `runs_dir`
- `run-multi-plan.py` skips plans whose `results/plan-XX/analysis/runs-summary.json` already exists
- If a plan is partially complete, the orchestrator detects missing `run-NNN` directories and only runs the missing run numbers
- `run-batch.py` skips tasks with no experiment directory or no plan files
- Each plan snapshot is copied to `results/plan-XX/plan.md` so outputs remain self-contained

### Data Versions

Archived results are kept alongside the current `results/` directory with a descriptive suffix:

| Directory | Mode | Tasks | Plans x Runs | Date |
|-----------|------|-------|-------------|------|
| `results/` (batch 2) | Docker, `bypassPermissions` | sympy\_\_sympy-12481, scikit-learn\_\_scikit-learn-14053, pylint-dev\_\_pylint-4970 | 5 plans x 5 runs each | 2026-04-08 |
| `results/` (batch 1) | host, `acceptEdits` | django\_\_django-11951, pytest-dev\_\_pytest-7490 | 5 plans x 5 runs each | 2026-04-02 |
| `results/` (pilot) | host, `acceptEdits` | exp-001-django-10924 | 6 plans x 10 runs | 2026-03-30 |
| `results-v1-host/` | host, `acceptEdits` | django\_\_django-11951, pytest-dev\_\_pytest-7490 | 5 plans x 5 runs each | 2026-04-01 |

Note: batch 1 and batch 2 `results/` directories coexist within their respective experiment directories. The pilot experiment uses the legacy naming convention (`exp-001-django-10924`).

To start a new experiment round, archive the current `results/` directory and delete the original so the resume mechanism starts fresh.

### Bug Fix History

**2026-04-03** — Critical data extraction bugs fixed in `scripts/run-experiment.py`:

| Bug | Impact | Fix |
|-----|--------|-----|
| `filter_diff_excluding_paths` missing trailing `\n` | `git apply` always failed → all `claude_patch=false` | Added `+ "\n"` to return value |
| `collect_results` ran `git reset HEAD` before `--name-only` | `changed_files_count` always 0 | Reordered; added fallback parsing from `final.diff` |
| Duration used file mtime instead of `transcript.json` `duration_ms` | Times off by 10-100x | Extract `duration_ms` from transcript; priority: `run-meta.json` > transcript > mtime |
| `start_time`/`end_time` not persisted | Lost on rebuild | Write `run-meta.json` after each run |
| Duration displayed as integer | Lost precision | Changed to `.1f` format |

All historical runs were re-validated using `--revalidate` mode. Summary data was rebuilt from fixed artifacts. No `final.diff` or `transcript.json` files were modified.

**2026-04-04** — SKIPPED test status parsing fix in `scripts/run-experiment.py`:

| Bug | Impact | Fix |
|-----|--------|-----|
| `parse_pytest_output` regex missing `SKIPPED` status | SKIPPED tests reported as `NOT_FOUND` → false `pass_to_pass` failures | Added `SKIPPED` to regex; added `skipped_set` tracking; `evaluate_expectations` accepts `SKIPPED` for pass_to_pass |

Also affected `scripts/check-env.py`: `evaluate_expectations` now treats `SKIPPED` as acceptable for `pass_to_pass` tests.

**2026-04-07** — Migrated to official SWE-bench `run_instance()` validation:

| Change | Details |
|--------|---------|
| **Unified Docker image** | Replaced dual-image architecture (`swe-env` + `claude-executor`) with single unified image built from official SWE-bench 3-tier hierarchy + Node.js + Claude CLI |
| **Official validation** | Replaced custom validation pipeline (`run_tests_in_docker`, manual `git apply`, diff filtering) with official `run_instance()` from `swebench.harness` |
| **Removed host mode** | Claude Code now always runs inside Docker container (`--execution-mode` flag removed) |
| **Mount point** | Changed from `/workspace` to `/testbed` (matches official SWE-bench images) |
| **`--use-official-base`** | New `build-env.py` flag to build from official SWE-bench base images |
| **`check-env.py`** | Simplified to image existence check + package import smoke test |

Previous dual-image architecture and custom validation pipeline are available on the `main` branch in git history (pre-commit `ed8e299`).

## Environment Notes

### Non-reproducible Tasks

| Task | Issue |
|------|-------|
| matplotlib__matplotlib-24870 | `test_contour_addlines[png]` image comparison fails in Docker (RMS 0.146). Replaced with `pylint-dev__pylint-4970`. |

### Tasks That Failed Env Setup

| Task | Issue |
|------|-------|
| sphinx-doc__sphinx-9258 | pytest collected 0 tests (likely missing test dependencies in Docker slim image) |
| pallets__flask-5014 | `werkzeug.__version__` not found in newer werkzeug; version incompatibility |
| sympy__sympy-24443 | `fail_to_pass` test already passes without gold patch (task data quality issue) |

### Known Issues

| Issue | Status | Impact |
|-------|--------|--------|
| `matplotlib__matplotlib-24870` env not reproducible | Replaced with `pylint-dev__pylint-4970` | One fewer task in dataset |
| `--revalidate` overwrites `validation-results.json` without backup | Open — use `git checkout` to recover originals | Risk of data loss if revalidation introduces bugs |
| Hardcoded constants scattered across scripts (`CLAUDE_CODE_VERSION` in `build-env.py`, repo quotas in `select-tasks.py`) | Open | Changes require editing source files |
| Dependency versions not locked (`requirements.txt` uses `>=` minimums) | Open | Future dependency updates may break scripts |
| `config/experiment-config.json` exists but is not read by any script | Open | Config template is unused |
| `transcript.json` and `validation-results.json` contain original host paths (`/Users/...`) | By design — raw session data | Paths are observational, not consumed by scripts |
| `env-image.txt` tags inconsistent: older experiments use `swe-env:`, newer use `claude-swe-env:` | Open | Does not affect re-running experiments with `--use-official-base` |

### Security Warning

`--claude-permission-mode bypassPermissions` allows Claude Code to execute arbitrary commands without confirmation. Claude runs inside a Docker container with project dependencies, but the container has network access. Use `acceptEdits` (default) to retain manual approval of file edits.

The code does **not** use `--allowedTools` to restrict Claude's available tools. If finer-grained control is needed, patch the `claude` command invocation in `run-experiment.py` to add tool restrictions.

### --revalidate Overwrite

The `--revalidate` flag re-runs validation for existing runs and **overwrites** `validation-results.json` without backup. The original file can be recovered via `git checkout` if needed. Other run artifacts (`transcript.json`, `final.diff`, `changed-files.txt`) are never modified by revalidation.

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
