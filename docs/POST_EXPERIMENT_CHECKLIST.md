# Post-Experiment Checklist

Complete these items after all experiment runs finish, before the final push to GitHub.

## 1. Data Cleanup

- [ ] **Remove hardcoded absolute paths from `batch-summary.json`**
  - Contains `/Users/taoran.wang/...` in `exp_dir` fields
  - Replace with relative paths (`experiments/<instance_id>`) or remove `exp_dir` field

- [ ] **Check and clean hardcoded paths in `results/*/analysis/summary.txt`**
  - Scikit-learn and sympy results contain `/Users/taoran.wang/...` in summary text
  - Regenerate summaries or remove absolute paths

- [ ] **Decide on `transcript.json` storage**
  - `scikit-learn__scikit-learn-14053/results/` is 246 MB (mostly transcripts)
  - Options: (a) add `**/transcript.json` to `.gitignore`, (b) compress, (c) use Git LFS, (d) keep as-is
  - Recommendation: gitignore `transcript.json` and provide a separate download link if needed

## 2. Experiment Completeness

For each task, verify 5 plans x 5 runs are complete:

- [ ] `django__django-11951` — complete (5 plans, 5 results, comparative analysis)
- [ ] `pytest-dev__pytest-7490` — complete (5 plans, 5 results, comparative analysis)
- [ ] `sympy__sympy-12481` — check if all 5 plans x 5 runs finished
- [ ] `scikit-learn__scikit-learn-14053` — plan-05 was missing analysis; verify complete
- [ ] `pylint-dev__pylint-4970` — had no `results/` directory; verify results were generated
- [ ] `matplotlib__matplotlib-24870` — skipped (non-reproducible in Docker)
- [ ] `pallets__flask-5014` — skipped (env setup failed)
- [ ] `sphinx-doc__sphinx-9258` — skipped (env setup failed)
- [ ] `sympy__sympy-24443` — skipped (task data quality issue)
- [ ] `exp-001-django-10924` — legacy pilot; decide whether to keep or archive

## 3. Consistency Fixes

- [ ] **Update `batch-summary.json`** — regenerate after all runs complete
  - Should reflect final experiment status, not `execution_failed` for all tasks
  - Remove or relativize `exp_dir` paths

- [ ] **Docker image tag consistency**
  - Old experiments: `swe-env:<task>` in `env-image.txt`
  - New experiments: `claude-swe-env:<task>` in `env-image.txt`
  - Either: (a) rebuild old tasks with `--use-official-base`, or (b) add a note in README explaining the difference

- [ ] **Remove or annotate `config/experiment-config.json`**
  - README notes it is unused by any script
  - Add a comment inside the file or remove it

- [ ] **Remove or annotate `docker/` directory**
  - Directory is empty (placeholder)
  - Remove if not needed, or add a README inside explaining its purpose

## 4. Documentation Updates

- [ ] **Update README.md data versions table**
  - Add new experiment round (sympy, scikit-learn, pylint) with date and mode
  - Update `results/` description to cover all tasks

- [ ] **Update README.md known issues**
  - Remove resolved issues
  - Add any new issues discovered during the experiment run

- [ ] **Verify README.md instructions match actual scripts**
  - All command examples should work on a fresh clone
  - Check that `--use-official-base` flag examples are correct

- [ ] **Update SETUP_COMPLETE.md or remove it**
  - Currently references only `exp-001-django-10924` and the old dual-image architecture
  - Either update or remove (RECONSTRUCTION_GUIDE.md now covers the same ground)

## 5. Repository Hygiene

- [ ] **Stage all untracked files**
  - `experiments/*/plans/` — plan files for new tasks
  - `experiments/*/results/` — experiment results
  - `experiments/*/comparative-analysis/` — comparison reports
  - `experiments/*/claude-executor-image.txt` — executor image tags
  - `experiments/*/plan-prompt.md` — plan generation prompts

- [ ] **Verify `.gitignore` is correct**
  - `logs/` is now gitignored (added pre-push)
  - `experiments/*/repo/` remains gitignored
  - `experiments/*/results-v1-host/` remains gitignored
  - No sensitive files (`.env`, API keys) are staged

- [ ] **Check total repo size**
  - Current ~2.4 GB (including `repo/` directories which are gitignored)
  - After gitignore, the tracked size should be manageable
  - `scikit-learn` results (246 MB) may need special handling (see item 1)

## 6. Final Verification

- [ ] **Clone test**: on the same or another machine, clone to a temp directory and verify:
  ```bash
  git clone <repo-url> /tmp/test-clone
  cd /tmp/test-clone
  ls scripts/         # all scripts present
  ls experiments/     # all experiment dirs present
  cat README.md       # instructions are clear
  ```

- [ ] **File integrity**: verify no corrupted JSON or truncated files
  ```bash
  find experiments/ -name "*.json" -exec python3 -c "import json,sys; json.load(open(sys.argv[1]))" {} \;
  ```

- [ ] **No secrets in git history**
  ```bash
  git log --all --full-history -- "*.env" ".env.*"
  # Should show nothing (or only .env.example)
  ```
