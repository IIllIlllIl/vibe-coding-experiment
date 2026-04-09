# Project Reconstruction Guide

This document explains how to reconstruct and run this project on a different device.

It complements `README.md` by making the hidden prerequisites and external dependencies explicit.

## Goal

Reconstruct a working environment that can:

1. run the experiment framework locally;
2. download datasets and set up experiment directories;
3. build and validate Docker environments;
4. execute multi-plan runs for individual tasks or batch runs across all tasks.

---

## What is in GitHub vs. what is not

The repository on GitHub does **not** include everything needed to run experiments end-to-end.

### Included in GitHub

These are tracked and should be available after cloning this repository:

- framework code under `scripts/`
- project documentation under `README.md` and `docs/`
- example config under `.env.example`
- SWE-bench Verified dataset under `datasets/swe-bench-verified/` (7.8 MB, includes `selected-tasks.json`)
- experiment metadata (`task_full.json`, `base-commit.txt`, `plans/`, `env-image.txt`)
- experiment results under `experiments/*/results/`
- comparative analysis under `experiments/*/comparative-analysis/`
- dependency list in `requirements.txt`

### Not included in GitHub

These are intentionally ignored and must be recreated or obtained separately:

- `datasets/swe-bench/` — vendored SWE-bench source (61 MB)
- `experiments/*/repo/` — target repository snapshots (~2.2 GB total)
- `.env` — API keys
- `logs/` — runtime logs
- `experiments/*/results-v1-host/` — archived earlier experiment rounds
- local virtual environments (`.venv/`)
- local Claude state (`.claude/`)

This behavior is defined in `.gitignore`.

---

## Prerequisites

Install the following on the new device before continuing:

- **Python 3.10+**
- **Git**
- **Docker** (Docker Desktop, Colima, or other Docker daemon)
- **Network access** to GitHub, PyPI, and Docker Hub

## Required accounts / credentials

You need:

- an Anthropic API key for Claude Code workflows

Create the local environment file:

```bash
cp .env.example .env
```

Then edit `.env` and set:

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

Optional:

```bash
OPENAI_API_KEY=...       # for swebench inference
DOCKER_HOST=unix:///...  # if using Colima on macOS
```

---

## Step 1: Clone this repository

```bash
git clone <this-repo-url>
cd vibe-coding-experiment
```

---

## Step 2: Create a Python environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Note:
- dependencies are loosely pinned (`>=` minimums); for exact reproducibility, generate a lock file (`pip freeze > requirements-lock.txt`) on the source machine.

---

## Step 3: Recreate the SWE-bench dependency

The framework imports from a local clone of SWE-bench under `datasets/swe-bench/`.

```bash
git clone https://github.com/swe-bench/SWE-bench.git datasets/swe-bench
```

After cloning, the following should exist:

- `datasets/swe-bench/README.md`
- `datasets/swe-bench/swebench/__init__.py`

Note: the SWE-bench Verified dataset (`datasets/swe-bench-verified/`) is already tracked in Git and does not need to be downloaded again.

---

## Step 4: Verify framework-level setup

```bash
python scripts/verify-setup.py
```

This checks:
- required directories exist
- `datasets/swe-bench/` is present
- Python dependencies are installed
- sample SWE-bench data can be loaded

Fix any reported issues before proceeding.

---

## Step 5: Set up experiment directories

Each experiment needs a target repository snapshot under `experiments/<instance_id>/repo/`. The `setup-task.py` script automates this:

```bash
# Set up all 30 selected tasks (clone repos, create directory structure)
python scripts/setup-task.py --dataset datasets/swe-bench-verified/data.json \
  $(python -c "import json; ids=[t['instance_id'] for t in json.loads(open('datasets/swe-bench-verified/selected-tasks.json').read())['tasks']]; print(' '.join(ids))")

# Or set up specific tasks only
python scripts/setup-task.py django__django-11951 sympy__sympy-12481
```

For each task, this creates:
- `experiments/<instance_id>/repo/` — target repository at the base commit
- `experiments/<instance_id>/task_full.json` — SWE-bench task metadata
- `experiments/<instance_id>/base-commit.txt` — base commit hash

If you only want to review existing results (not re-run experiments), you can skip this step.

---

## Step 6: Prepare plan files

Each task requires 5 plan files under `experiments/<instance_id>/plans/`:

```
experiments/django__django-11951/
└── plans/
    ├── plan-01.md
    ├── plan-02.md
    ├── plan-03.md
    ├── plan-04.md
    └── plan-05.md
```

Plans are manually created. To generate plan prompts (templates for plan creation):

```bash
python scripts/make-plan-prompts.py
```

This writes a `plan-prompt.md` into each experiment directory that lacks one.

---

## Step 7: Build the unified Docker image

The framework uses a single unified Docker image per task that serves both Claude Code execution and official SWE-bench validation. It is built from the official SWE-bench 3-tier hierarchy (base → env → instance) with Node.js + Claude CLI layered on top.

```bash
# Build for a specific task
python scripts/build-env.py experiments/django__django-11951 --use-official-base

# Force rebuild all layers
python scripts/build-env.py experiments/django__django-11951 --use-official-base --rebuild
```

This writes the image tag to `experiments/<instance_id>/env-image.txt`.

Important:
- Docker must be running locally
- the build depends on the experiment `repo/` directory being present (Step 5)
- the build pulls large base images from Docker Hub (~1-5 GB each); allow time and disk space

---

## Step 8: Validate the environment

```bash
python scripts/check-env.py experiments/django__django-11951
```

This verifies:
- the Docker image exists (auto-builds if `--use-official-base` is set and image is missing)
- the target package is importable inside the container (smoke test)

Do not start the main experiment run until this validation passes.

---

## Step 9: Run experiments

### Single task (multi-plan)

```bash
# Run all plans for one task, 5 runs each
python scripts/run-multi-plan.py experiments/django__django-11951 --runs 5

# Run with resource limits
python scripts/run-multi-plan.py experiments/django__django-11951 --runs 5 \
  --claude-permission-mode bypassPermissions --docker-cpus 2 --docker-memory 4g

# Smoke test (1 run, selected plans)
python scripts/run-multi-plan.py experiments/django__django-11951 --plans 01 02 --runs 1

# Dry run
python scripts/run-multi-plan.py experiments/django__django-11951 --dry-run
```

### Batch (all tasks)

```bash
# Dry run to preview
python scripts/run-batch.py --dry-run --runs 5

# Run all tasks
python scripts/run-batch.py --runs 5

# Run specific tasks only
python scripts/run-batch.py --runs 5 --only django__django-11951 sympy__sympy-12481

# Force rebuild Docker images
python scripts/run-batch.py --runs 5 --rebuild-env
```

Claude Code runs inside the Docker container. The API key is passed via a temporary env file (not exposed in process listings).

---

## Step 10: Check reconstruction success

A reconstructed environment is considered usable if the following all succeed:

1. `python scripts/verify-setup.py` — passes
2. `python scripts/build-env.py experiments/<task> --use-official-base` — image builds
3. `python scripts/check-env.py experiments/<task>` — validation passes
4. at least one dry run of `run-multi-plan.py` completes without error

---

## Expected output locations

### Per-task (multi-plan)

- `experiments/<name>/results/plan-XX/runs/run-NNN/` — per-run artifacts (diff, transcript, validation)
- `experiments/<name>/results/plan-XX/analysis/runs-summary.json` — per-plan aggregated stats
- `experiments/<name>/comparative-analysis/comparison-summary.json` — cross-plan comparison

### Batch

- `experiments/batch-summary.json` — all tasks summary

---

## Common reconstruction failure points

### 1. `datasets/swe-bench/` missing

Symptom: `verify-setup.py` fails; import errors from `swebench` module.

Fix:

```bash
git clone https://github.com/swe-bench/SWE-bench.git datasets/swe-bench
```

### 2. `experiments/.../repo/` missing

Symptom: `build-env.py` or `run-experiment.py` fails because the source repository is missing.

Fix: run `setup-task.py` (Step 5) to clone and checkout the correct base commit.

### 3. Docker not running

Symptom: image build or validation fails with connection errors.

Fix: start Docker Desktop or the local Docker daemon. If using Colima:

```bash
colima start
export DOCKER_HOST=unix://$HOME/.colima/default/docker.sock
```

### 4. Docker image tag mismatch

Symptom: script reports image not found.

Fix: check `env-image.txt` in the experiment directory. Older experiments use `swe-env:` prefix; newer ones use `claude-swe-env:`. The `--use-official-base` flag builds the new unified image.

### 5. `.env` not configured

Symptom: Claude-related or API-dependent actions fail.

Fix:

```bash
cp .env.example .env
# Edit and set ANTHROPIC_API_KEY
```

### 6. Python version incompatibility

Symptom: import errors or syntax errors in scripts.

Fix: ensure Python 3.10+ is active (`python3 --version`).

---

## Reproducibility limitations

This project is reconstructable, but not perfectly self-contained:

1. some required inputs (`repo/`, `datasets/swe-bench/`) are excluded from GitHub and must be recreated manually;
2. Python dependencies are not fully locked (`>=` minimums, no lock file);
3. successful reconstruction depends on external services (Docker Hub, PyPI, GitHub);
4. Docker image contents are reproducible from scripts, but rely on network package installs during build;
5. Claude Code execution is inherently non-deterministic — re-running the same plan produces different results (that is the research question);
6. experiment results include `transcript.json` files that can be large (hundreds of MB total across all tasks).

For stricter reproducibility, consider adding:
- a fully pinned lock file (`pip freeze > requirements-lock.txt`);
- explicit Python version pinning;
- a bootstrap script (`setup.sh`) for all setup steps;

---

## Minimal reconstruction checklist

Use this checklist on a fresh device:

- [ ] clone this repository
- [ ] create and activate `.venv`
- [ ] install `requirements.txt`
- [ ] copy `.env.example` to `.env`
- [ ] set `ANTHROPIC_API_KEY` in `.env`
- [ ] clone SWE-bench into `datasets/swe-bench/`
- [ ] run `python scripts/verify-setup.py` — passes
- [ ] run `python scripts/setup-task.py <instance_id>` for desired tasks
- [ ] create plan files in `experiments/<instance_id>/plans/`
- [ ] run `python scripts/build-env.py experiments/<instance_id> --use-official-base`
- [ ] run `python scripts/check-env.py experiments/<instance_id>` — passes
- [ ] run a dry-run: `python scripts/run-multi-plan.py experiments/<instance_id> --dry-run`
- [ ] run the actual experiment

If all boxes can be checked on a new machine, the project has been successfully reconstructed.
