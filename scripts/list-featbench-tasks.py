#!/usr/bin/env python3
"""
Script to list all available tasks from the FeatBench dataset.

This script parses the FeatBench dataset and outputs all available tasks
with their task ID, repository, and requirement description.
"""

import os
import json
import sys
from pathlib import Path


def find_featbench_data():
    """Find the FeatBench data directory."""
    # Check common locations
    script_dir = Path(__file__).parent
    possible_paths = [
        script_dir.parent / "datasets" / "featbench" / "raw",
        script_dir.parent / "datasets" / "featbench" / "raw" / "FeatBench",
        Path.cwd() / "datasets" / "featbench" / "raw",
        Path.cwd() / "datasets" / "featbench" / "raw" / "FeatBench",
    ]

    for path in possible_paths:
        if path.exists():
            return path

    return None


def parse_featbench_tasks(data_dir):
    """
    Parse FeatBench tasks from the dataset directory.

    Expected structure:
    data_dir/
        task_id_1/
            task.json or similar config file
        task_id_2/
            task.json or similar config file
        ...
    """
    tasks = []

    # Look for task directories
    if not data_dir.exists():
        print(f"Error: Data directory does not exist: {data_dir}")
        return tasks

    # Iterate through subdirectories
    for task_dir in sorted(data_dir.iterdir()):
        if not task_dir.is_dir():
            continue

        task_id = task_dir.name

        # Look for task configuration files
        config_files = [
            task_dir / "task.json",
            task_dir / "config.json",
            task_dir / "metadata.json",
            task_dir / "task_info.json"
        ]

        task_info = None
        for config_file in config_files:
            if config_file.exists():
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        task_info = json.load(f)
                    break
                except json.JSONDecodeError as e:
                    print(f"Warning: Could not parse {config_file}: {e}")
                    continue

        if task_info:
            tasks.append({
                'task_id': task_id,
                'repository': task_info.get('repository', task_info.get('repo', 'Unknown')),
                'requirement': task_info.get('requirement', task_info.get('description', task_info.get('task', 'No description available'))),
                'base_commit': task_info.get('base_commit', task_info.get('commit', 'Unknown'))
            })
        else:
            # If no config file found, try to extract info from README or other files
            readme_file = task_dir / "README.md"
            if readme_file.exists():
                with open(readme_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Extract first line as title
                    first_line = content.split('\n')[0].strip('# ')
                    tasks.append({
                        'task_id': task_id,
                        'repository': 'Unknown',
                        'requirement': first_line,
                        'base_commit': 'Unknown'
                    })
            else:
                tasks.append({
                    'task_id': task_id,
                    'repository': 'Unknown',
                    'requirement': 'No description available',
                    'base_commit': 'Unknown'
                })

    return tasks


def display_tasks(tasks):
    """Display tasks in a readable format."""
    if not tasks:
        print("No tasks found in the FeatBench dataset.")
        print("\nPlease ensure the dataset is properly cloned to:")
        print("  datasets/featbench/raw/ or datasets/featbench/raw/FeatBench/")
        return

    print(f"\n{'='*80}")
    print(f"FeatBench Dataset - {len(tasks)} Tasks Available")
    print(f"{'='*80}\n")

    for i, task in enumerate(tasks, 1):
        print(f"{i}. Task ID: {task['task_id']}")
        print(f"   Repository: {task['repository']}")
        print(f"   Base Commit: {task['base_commit']}")
        print(f"   Requirement: {task['requirement'][:100]}{'...' if len(task['requirement']) > 100 else ''}")
        print()

    print(f"{'='*80}")
    print(f"Total: {len(tasks)} tasks")
    print(f"{'='*80}\n")


def main():
    """Main function to list FeatBench tasks."""
    print("Searching for FeatBench dataset...")

    data_dir = find_featbench_data()

    if data_dir is None:
        print("\nError: Could not find FeatBench dataset.")
        print("\nExpected locations:")
        print("  - datasets/featbench/raw/")
        print("  - datasets/featbench/raw/FeatBench/")
        print("\nPlease clone the dataset first:")
        print("  git clone https://github.com/TsinghuaSE/FeatBench.git datasets/featbench/raw/")
        sys.exit(1)

    print(f"Found dataset at: {data_dir}")
    print("Parsing tasks...\n")

    tasks = parse_featbench_tasks(data_dir)
    display_tasks(tasks)

    # Optionally save to file
    output_file = data_dir.parent / "task_list.json"
    if tasks:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, indent=2, ensure_ascii=False)
        print(f"Task list saved to: {output_file}")


if __name__ == "__main__":
    main()
