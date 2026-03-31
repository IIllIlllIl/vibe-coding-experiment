# Project Reconstruction Guide

This document explains how to reconstruct and run this project on a different device.

It complements `README.md` by making the hidden prerequisites and external dependencies explicit.

## Goal

Reconstruct a working environment that can:

1. run the experiment framework locally;
2. prepare an experiment directory correctly;
3. build and validate the Docker environment;
4. execute single-plan or multi-plan runs.

---

## What is in GitHub vs. what is not

The repository on GitHub does **not** include everything needed to run experiments end-to-end.

### Included in GitHub

These are tracked and should be available after cloning this repository:

- framework code under `scripts/`
- project documentation under `README.md` and `docs/`
- example config under `.env.example`
- experiment metadata and results summaries under `experiments/exp-001-django-10924/`
- dependency list in `requirements.txt`

### Not included in GitHub

These are intentionally ignored and must be recreated manually:

- `datasets/swe-bench/`
- `experiments/*/repo/`
- `.env`
- local virtual environments such as `.venv/`
- local Claude state under `.claude/`

This behavior is defined in `.gitignore`.

---

## Prerequisites

Install the following on the new device before continuing:

- Python 3.10+ 
- Git
- Docker
- Claude Code CLI (`claude`) installed and available in `PATH`
- Claude Code authenticated locally
- network access to GitHub and Python package registries

## Required accounts / credentials

You need:

- an Anthropic API key for Claude Code workflows
- local Claude authentication already completed

Create the local environment file:

```bash
cp .env.example .env
```

Then edit `.env` and set:

```bash
ANTHROPIC_API_KEY=...
```

Optional:

```bash
OPENAI_API_KEY=...
```

---

## Step 1: Clone this repository

```bash
git clone <this-repo-url>
cd vibe-coding-experiment
```

---

## Step 2: Create a Python environment and install dependencies

It is recommended to use a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Note:
- this repository currently uses `requirements.txt` rather than a fully locked dependency file;
- if exact long-term reproducibility is required, add a lock file in the future.

---

## Step 3: Recreate the missing SWE-bench dependency

This repository expects a local clone of SWE-bench under `datasets/swe-bench/`, but that directory is not tracked in GitHub.

Run:

```bash
git clone https://github.com/swe-bench/SWE-bench.git datasets/swe-bench
```

After cloning, the following should exist:

- `datasets/swe-bench/README.md`
- `datasets/swe-bench/swebench/__init__.py`

---

## Step 4: Verify framework-level setup

Run:

```bash
python scripts/verify-setup.py
```

This checks:

- required directories;
- whether `datasets/swe-bench/` exists;
- whether Python dependencies are installed;
- whether the config template exists;
- whether sample SWE-bench data can be loaded.

If this step fails, fix the reported issue before proceeding.

---

## Step 5: Recreate the experiment input repository

For each experiment, the target repository snapshot under `experiments/<experiment>/repo/` must be created manually.

For the current experiment:

```bash
cd experiments/exp-001-django-10924
git clone https://github.com/django/django.git repo
cd repo
git checkout bceadd2788dc2dad53eba0caae172bd8522fd483
cd ../../..
```

Why this is required:
- the framework reads from `experiments/<experiment>/repo/` when creating each isolated run;
- this directory is ignored by Git and therefore is not present after cloning the framework repository.

## Files that must already exist in the experiment directory

For `experiments/exp-001-django-10924/`, confirm these files exist:

- `task_full.json`
- `base-commit.txt`
- `plan.md` or `plans/plan-XX.md`
- `metadata.json` if used by your workflow

The repository currently already tracks these metadata files.

---

## Step 6: Prepare plan files

### Legacy single-plan mode

Uses:

- `experiments/exp-001-django-10924/plan.md`

### Multi-plan mode

Uses:

- `experiments/exp-001-django-10924/plans/plan-01.md`
- `experiments/exp-001-django-10924/plans/plan-02.md`
- etc.

If you need to initialize the multi-plan structure:

```bash
cd experiments/exp-001-django-10924
mkdir -p plans
cp plan.md plans/plan-01.md
cd ../..
```

Then add additional plan variants manually if needed.

---

## Step 7: Build the reusable Docker validation image

Run:

```bash
python scripts/build-env.py experiments/exp-001-django-10924
```

What this does:

- reads `task_full.json`;
- copies `experiments/exp-001-django-10924/repo/` into a temporary Docker build context;
- builds a reusable validation image;
- writes the image tag to `experiments/exp-001-django-10924/env-image.txt`.

Important:
- Docker must be running locally;
- the build depends on the experiment `repo/` directory being present first.

---

## Step 8: Validate the environment

Run:

```bash
python scripts/check-env.py experiments/exp-001-django-10924 --image swe-env:django-django-10924
```

Expected output behavior:

- `base + test_patch`: `FAIL_TO_PASS` should fail and `PASS_TO_PASS` should pass;
- `base + test_patch + gold_patch`: both should pass.

Expected artifact:

- `experiments/exp-001-django-10924/env-check.json`

Do not start the main experiment run until this validation passes.

---

## Step 9: Run the experiment

### Single-plan mode

Single run:

```bash
python scripts/run-experiment.py experiments/exp-001-django-10924 \
  --validation-image swe-env:django-django-10924
```

Multiple runs:

```bash
python scripts/run-experiment.py experiments/exp-001-django-10924 \
  --validation-image swe-env:django-django-10924 \
  --runs 10
```

Dry run:

```bash
python scripts/run-experiment.py experiments/exp-001-django-10924 --dry-run
```

### Multi-plan mode

Run all plans:

```bash
python scripts/run-multi-plan.py experiments/exp-001-django-10924
```

Run selected plans only:

```bash
python scripts/run-multi-plan.py experiments/exp-001-django-10924 --plans 01 02 03
```

Smoke test:

```bash
python scripts/run-multi-plan.py experiments/exp-001-django-10924 --plans 01 02 --runs 1
```

Dry run:

```bash
python scripts/run-multi-plan.py experiments/exp-001-django-10924 --plans 01 02 --runs 1 --dry-run
```

---

## Step 10: Check reconstruction success

A reconstructed environment is considered usable if the following work:

1. `python scripts/verify-setup.py`
2. `python scripts/build-env.py experiments/exp-001-django-10924`
3. `python scripts/check-env.py experiments/exp-001-django-10924 --image swe-env:django-django-10924`
4. at least one dry run or one real run of `run-experiment.py` or `run-multi-plan.py`

---

## Expected output locations

### Single-plan outputs

- `experiments/<name>/runs/run-NNN/`
- `experiments/<name>/analysis/runs-summary.json`
- `experiments/<name>/analysis/summary.txt`

### Multi-plan outputs

- `experiments/<name>/results/plan-XX/runs/run-NNN/`
- `experiments/<name>/results/plan-XX/analysis/runs-summary.json`
- `experiments/<name>/results/plan-XX/analysis/summary.txt`
- `experiments/<name>/comparative-analysis/comparison-summary.json`
- `experiments/<name>/comparative-analysis/comparison-report.txt`

---

## Common reconstruction failure points

### 1. `datasets/swe-bench/` missing

Symptom:
- `verify-setup.py` fails.

Fix:

```bash
git clone https://github.com/swe-bench/SWE-bench.git datasets/swe-bench
```

### 2. `experiments/.../repo/` missing

Symptom:
- `run-experiment.py` or `build-env.py` fails because the source repository is missing.

Fix:
- clone the target project into the experiment directory;
- checkout the base commit recorded in `base-commit.txt`.

### 3. Docker not running

Symptom:
- image build or validation fails.

Fix:
- start Docker Desktop or the local Docker daemon.

### 4. Claude CLI not installed or not authenticated

Symptom:
- experiment execution fails when invoking `claude`.

Fix:
- install Claude Code CLI;
- complete local authentication;
- confirm `claude` is available in `PATH`.

### 5. `.env` not configured

Symptom:
- Claude-related or API-dependent actions fail.

Fix:

```bash
cp .env.example .env
```

Then fill the required keys.

---

## Reproducibility limitations

This project is reconstructable, but not yet perfectly self-contained.

Current limitations:

1. some required inputs are excluded from GitHub and must be recreated manually;
2. Python dependencies are not fully locked;
3. successful reconstruction depends on external services and local authentication state;
4. Docker image contents are reproducible from scripts, but still rely on network package installs during build.

If stricter reproducibility is needed in the future, consider adding:

- a fully pinned lock file;
- explicit Python version pinning;
- a bootstrap script for all setup steps;
- a dedicated section in `README.md` linking to this document.

---

## Minimal reconstruction checklist

Use this checklist on a fresh device:

- [ ] clone this repository
- [ ] create and activate `.venv`
- [ ] install `requirements.txt`
- [ ] copy `.env.example` to `.env`
- [ ] set `ANTHROPIC_API_KEY`
- [ ] install and authenticate Claude Code CLI
- [ ] clone SWE-bench into `datasets/swe-bench/`
- [ ] clone the target repo into `experiments/exp-001-django-10924/repo/`
- [ ] checkout the required base commit
- [ ] run `python scripts/verify-setup.py`
- [ ] run `python scripts/build-env.py experiments/exp-001-django-10924`
- [ ] run `python scripts/check-env.py experiments/exp-001-django-10924 --image swe-env:django-django-10924`
- [ ] run a dry-run or real experiment command

If all boxes can be checked on a new machine, the project has been successfully reconstructed.
