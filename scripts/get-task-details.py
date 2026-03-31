#!/usr/bin/env python3
"""
Script to retrieve and display full details for a specific SWE-bench task.
"""

import sys
import json
from datasets import load_dataset


def get_task_details(instance_id):
    """Retrieve full details for a specific task instance."""
    print(f"Loading SWE-bench Lite dataset...")
    dataset = load_dataset('princeton-nlp/SWE-bench_Lite', split='test')

    # Find the task
    task = None
    for item in dataset:
        if item['instance_id'] == instance_id:
            task = item
            break

    if not task:
        print(f"Error: Task {instance_id} not found in dataset")
        sys.exit(1)

    return task


def display_task_details(task):
    """Display full task details."""
    print("\n" + "="*80)
    print(f"Task Details: {task['instance_id']}")
    print("="*80 + "\n")

    print(f"Repository: {task['repo']}")
    print(f"Base Commit: {task['base_commit']}")
    print(f"Version: {task.get('version', 'N/A')}")
    print(f"Created At: {task.get('created_at', 'N/A')}")
    print()

    print("-" * 80)
    print("PROBLEM STATEMENT")
    print("-" * 80)
    print(task['problem_statement'])
    print()

    print("-" * 80)
    print("HINTS TEXT (if available)")
    print("-" * 80)
    hints = task.get('hints_text', '')
    if hints:
        print(hints)
    else:
        print("(No hints provided)")
    print()

    print("-" * 80)
    print("TEST PATCH")
    print("-" * 80)
    print(task.get('test_patch', '(No test patch)'))
    print()

    print("-" * 80)
    print("PATCH (Gold)")
    print("-" * 80)
    print(task.get('patch', '(No patch)'))
    print()

    print("="*80)


def save_task_to_json(task, output_file):
    """Save task details to JSON file."""
    # Convert task to dict if needed
    task_dict = dict(task)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(task_dict, f, indent=2, ensure_ascii=False)

    print(f"\nTask details saved to: {output_file}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python get-task-details.py <instance_id>")
        print("Example: python get-task-details.py django__django-10924")
        sys.exit(1)

    instance_id = sys.argv[1]
    task = get_task_details(instance_id)
    display_task_details(task)

    # Save to JSON if output file specified
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
        save_task_to_json(task, output_file)


if __name__ == "__main__":
    main()
