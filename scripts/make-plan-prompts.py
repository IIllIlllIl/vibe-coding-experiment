#!/usr/bin/env python3
"""
Batch-generate plan prompts for all selected tasks.

For each task that has an experiment directory, generates a plan-prompt.md file
containing the /plan prompt with problem statement and the next plan file path.

Usage:
    python scripts/make-plan-prompts.py
    python scripts/make-plan-prompts.py --only django__django-11951 pytest-dev__pytest-7490
"""

import argparse
import json
import re
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Generate plan prompts for tasks")
    parser.add_argument(
        "--tasks",
        default="datasets/swe-bench-verified/selected-tasks.json",
        help="Path to selected-tasks.json",
    )
    parser.add_argument(
        "--experiments-dir",
        default="experiments",
        help="Root experiments directory",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        help="Only generate for specific instance_ids",
    )
    return parser.parse_args()


def get_next_plan_number(plans_dir: Path) -> int:
    """Determine the next plan number from existing plan-*.md files."""
    if not plans_dir.exists():
        return 1
    existing = []
    for f in plans_dir.glob("plan-*.md"):
        match = re.fullmatch(r"plan-(\d+)", f.stem)
        if match:
            existing.append(int(match.group(1)))
    return max(existing) + 1 if existing else 1


def load_selected_tasks(path: Path):
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data.get("tasks", [])


def main():
    args = parse_args()
    tasks_path = Path(args.tasks).resolve()
    experiments_dir = Path(args.experiments_dir).resolve()

    selected_tasks = load_selected_tasks(tasks_path)
    if not selected_tasks:
        print(f"No tasks found in {tasks_path}")
        return

    if args.only:
        only_set = set(args.only)
        selected_tasks = [t for t in selected_tasks if t["instance_id"] in only_set]

    generated = 0
    skipped = 0

    for task in selected_tasks:
        instance_id = task["instance_id"]
        exp_dir = experiments_dir / instance_id

        task_file = exp_dir / "task_full.json"
        if not task_file.exists():
            print(f"  SKIP {instance_id}: no task_full.json (run setup-task.py)")
            skipped += 1
            continue

        task_data = json.loads(task_file.read_text())
        problem_statement = task_data.get("problem_statement", "").strip()
        if not problem_statement:
            print(f"  SKIP {instance_id}: empty problem_statement")
            skipped += 1
            continue

        plans_dir = exp_dir / "plans"
        next_num = get_next_plan_number(plans_dir)
        plan_file = f"../plans/plan-{next_num:02d}.md"

        prompt_content = (
            f"/plan {problem_statement}\n"
            f"\n"
            f"Save this plan to {plan_file}"
        )

        # Use relative path from experiments_dir for portability
        rel_exp_dir = exp_dir.relative_to(experiments_dir)
        prompt_file = exp_dir / "plan-prompt.md"
        prompt_file.write_text(prompt_content)

        print(f"  OK   {instance_id}: next plan #{next_num:02d} -> {rel_exp_dir}/plan-prompt.md")
        generated += 1

    print(f"\nGenerated {generated} prompts, skipped {skipped} tasks")


if __name__ == "__main__":
    main()
