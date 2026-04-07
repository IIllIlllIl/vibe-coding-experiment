#!/usr/bin/env python3
"""
Set up experiment directory for a single SWE-bench task.
Usage: python scripts/setup-task.py <instance_id> [--dataset datasets/swe-bench-verified/data.json] [--experiments-dir experiments]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


def parse_args():
    parser = argparse.ArgumentParser(description="Set up experiment directory for a SWE-bench task")
    parser.add_argument("instance_ids", nargs="+", help="One or more instance IDs (e.g. django__django-10924)")
    parser.add_argument("--dataset", default="datasets/swe-bench-verified/data.json", help="Path to data.json")
    parser.add_argument("--experiments-dir", default="experiments", help="Root experiments directory")
    parser.add_argument("--skip-existing", action="store_true", help="Skip tasks that already have a directory")
    return parser.parse_args()


def load_dataset(path: Path) -> Dict[str, Dict[str, Any]]:
    """Load dataset and index by instance_id."""
    if not path.exists():
        print(f"Error: dataset not found: {path}")
        print("Run scripts/download-verified.py first.")
        sys.exit(1)
    tasks = json.loads(path.read_text())
    return {t["instance_id"]: t for t in tasks}


def repo_clone_url(repo: str) -> str:
    """Convert 'django/django' to clone URL."""
    return f"https://github.com/{repo}.git"


def setup_single_task(
    instance_id: str,
    task: Dict[str, Any],
    experiments_dir: Path,
    skip_existing: bool,
) -> Path:
    """Create experiment directory with repo clone, task data, and directory structure."""
    exp_dir = experiments_dir / instance_id

    if exp_dir.exists():
        if skip_existing:
            print(f"  SKIP (exists): {exp_dir}")
            return exp_dir
        print(f"  WARNING: {exp_dir} already exists, refreshing task data only")
    else:
        exp_dir.mkdir(parents=True)

    # 1. Save task_full.json
    task_file = exp_dir / "task_full.json"
    task_file.write_text(json.dumps(task, indent=2, ensure_ascii=False))
    print(f"  task_full.json -> {task_file}")

    # 2. Save base-commit.txt
    base_commit = task.get("base_commit", "")
    (exp_dir / "base-commit.txt").write_text(base_commit + "\n")

    # 3. Save metadata.json
    metadata = {
        "instance_id": instance_id,
        "repo": task.get("repo", ""),
        "base_commit": base_commit,
        "version": task.get("version", ""),
        "created_at": task.get("created_at", ""),
    }
    (exp_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    # 4. Clone repository at base_commit
    repo_dir = exp_dir / "repo"
    repo_full = task.get("repo", "")
    clone_url = repo_clone_url(repo_full)

    if not repo_dir.exists():
        print(f"  Cloning {repo_full}...")
        try:
            subprocess.run(
                ["git", "clone", "--quiet", clone_url, str(repo_dir)],
                check=True,
            )
        except subprocess.CalledProcessError:
            # F18: Clean up incomplete clone on failure
            if repo_dir.exists():
                import shutil
                shutil.rmtree(repo_dir, ignore_errors=True)
            raise
    else:
        print(f"  repo/ already exists, fetching...")

    # Checkout base_commit
    if base_commit:
        print(f"  Checking out {base_commit[:12]}...")
        subprocess.run(
            ["git", "fetch", "--quiet", "origin"],
            cwd=repo_dir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", "--quiet", base_commit],
            cwd=repo_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "clean", "-fdq"],
            cwd=repo_dir,
            capture_output=True,
        )

    # 5. Create directory structure
    for subdir in ["plans", "results"]:
        (exp_dir / subdir).mkdir(exist_ok=True)

    print(f"  Done: {exp_dir}")
    return exp_dir


def main():
    args = parse_args()
    dataset_path = Path(args.dataset)
    experiments_dir = Path(args.experiments_dir)

    tasks_by_id = load_dataset(dataset_path)
    print(f"Loaded {len(tasks_by_id)} tasks from {dataset_path}")

    not_found = [iid for iid in args.instance_ids if iid not in tasks_by_id]
    if not_found:
        print(f"Error: tasks not found in dataset: {', '.join(not_found)}")
        sys.exit(1)

    print(f"Setting up {len(args.instance_ids)} task(s)...\n")

    results: List[Dict[str, str]] = []
    for instance_id in args.instance_ids:
        task = tasks_by_id[instance_id]
        print(f"[{instance_id}]")
        exp_dir = setup_single_task(instance_id, task, experiments_dir, args.skip_existing)
        results.append({"instance_id": instance_id, "path": str(exp_dir)})

    print(f"\n{'='*50}")
    print(f"Set up {len(results)} experiment(s):")
    for r in results:
        print(f"  {r['instance_id']}  ->  {r['path']}")


if __name__ == "__main__":
    main()
