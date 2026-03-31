#!/usr/bin/env python3
"""
Script to list all available tasks from SWE-bench Lite dataset.

This script loads the SWE-bench Lite dataset from Hugging Face and displays
all available tasks with their instance ID, repository, and problem statement.
"""

import sys
import json
import argparse
from pathlib import Path

try:
    from datasets import load_dataset
except ImportError:
    print("Error: 'datasets' library not found.")
    print("Please install it with: pip install datasets")
    sys.exit(1)


def load_swebench_lite():
    """Load SWE-bench Lite dataset from Hugging Face."""
    print("Loading SWE-bench Lite dataset from Hugging Face...")
    try:
        dataset = load_dataset('princeton-nlp/SWE-bench_Lite', split='test')
        print(f"Successfully loaded {len(dataset)} tasks\n")
        return dataset
    except Exception as e:
        print(f"Error loading dataset: {e}")
        print("\nPlease ensure you have internet access and the datasets library is installed.")
        print("You may also need to authenticate with Hugging Face if accessing gated datasets.")
        sys.exit(1)


def display_tasks(dataset, repo_filter=None, limit=None, verbose=False):
    """Display tasks in a readable format with optional filtering."""
    tasks_to_show = []

    # Filter and collect tasks
    for idx, instance in enumerate(dataset):
        instance_id = instance.get('instance_id', 'Unknown')
        repo = instance.get('repo', 'Unknown')
        problem = instance.get('problem_statement', 'No description available')
        base_commit = instance.get('base_commit', 'Unknown')

        # Apply repository filter if provided
        if repo_filter and repo_filter.lower() not in repo.lower():
            continue

        tasks_to_show.append({
            'instance_id': instance_id,
            'repo': repo,
            'problem': problem,
            'base_commit': base_commit
        })

    # Apply limit
    if limit:
        tasks_to_show = tasks_to_show[:limit]

    # Display tasks
    print(f"{'='*80}")
    print(f"SWE-bench Lite - {len(tasks_to_show)} Tasks")
    if repo_filter:
        print(f"Filtered by repository: {repo_filter}")
    print(f"{'='*80}\n")

    for i, task in enumerate(tasks_to_show, 1):
        print(f"{i}. Instance ID: {task['instance_id']}")
        print(f"   Repository: {task['repo']}")
        print(f"   Base Commit: {task['base_commit']}")

        if verbose:
            # Show full problem statement in verbose mode
            print(f"   Problem Statement:")
            for line in task['problem'].split('\n')[:20]:  # Limit to first 20 lines
                print(f"     {line}")
            if len(task['problem'].split('\n')) > 20:
                print(f"     ... (truncated, use --verbose to see full statement)")
        else:
            # Show truncated version
            problem_preview = task['problem'][:150].replace('\n', ' ')
            print(f"   Problem: {problem_preview}{'...' if len(task['problem']) > 150 else ''}")
        print()

    print(f"{'='*80}")
    print(f"Total displayed: {len(tasks_to_show)} / {len(dataset)} tasks")
    print(f"{'='*80}\n")


def save_tasks_to_json(dataset, output_file, repo_filter=None):
    """Save task list to a JSON file."""
    tasks = []
    for instance in dataset:
        instance_id = instance.get('instance_id', 'Unknown')
        repo = instance.get('repo', 'Unknown')

        # Apply repository filter if provided
        if repo_filter and repo_filter.lower() not in repo.lower():
            continue

        tasks.append({
            'instance_id': instance_id,
            'repo': repo,
            'base_commit': instance.get('base_commit', 'Unknown'),
            'problem_statement': instance.get('problem_statement', ''),
            'version': instance.get('version', ''),
            'created_at': instance.get('created_at', '')
        })

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)

    print(f"Task list saved to: {output_file}")
    print(f"Total tasks saved: {len(tasks)}")


def list_unique_repos(dataset):
    """List all unique repositories in the dataset."""
    repos = set()
    for instance in dataset:
        repo = instance.get('repo', 'Unknown')
        repos.add(repo)

    print("\n" + "="*80)
    print("Unique Repositories in SWE-bench Lite")
    print("="*80 + "\n")

    for i, repo in enumerate(sorted(repos), 1):
        print(f"{i:2d}. {repo}")

    print("\n" + "="*80)
    print(f"Total: {len(repos)} repositories")
    print("="*80 + "\n")


def main():
    """Main function to list SWE-bench Lite tasks."""
    parser = argparse.ArgumentParser(
        description='List tasks from SWE-bench Lite dataset'
    )
    parser.add_argument(
        '--repo',
        type=str,
        help='Filter tasks by repository name (case-insensitive substring match)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of tasks to display'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show full problem statements'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Save task list to JSON file'
    )
    parser.add_argument(
        '--list-repos',
        action='store_true',
        help='List all unique repositories in the dataset'
    )

    args = parser.parse_args()

    # Load dataset
    dataset = load_swebench_lite()

    # List repositories if requested
    if args.list_repos:
        list_unique_repos(dataset)
        return

    # Display tasks
    display_tasks(dataset, repo_filter=args.repo, limit=args.limit, verbose=args.verbose)

    # Save to file if requested
    if args.output:
        save_tasks_to_json(dataset, args.output, repo_filter=args.repo)


if __name__ == "__main__":
    main()
