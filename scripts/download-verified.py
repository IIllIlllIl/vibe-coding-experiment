#!/usr/bin/env python3
"""
Download SWE-bench Verified dataset from Hugging Face.
Usage: python scripts/download-verified.py [--output-dir datasets/swe-bench-verified]
"""

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

try:
    from datasets import load_dataset
except ImportError:
    print("Error: 'datasets' library not found. Install with: pip install datasets")
    sys.exit(1)

DATASET_NAME = "princeton-nlp/SWE-bench_Verified"


def parse_args():
    parser = argparse.ArgumentParser(description="Download SWE-bench Verified dataset")
    parser.add_argument(
        "--output-dir",
        default="datasets/swe-bench-verified",
        help="Output directory (default: datasets/swe-bench-verified)",
    )
    return parser.parse_args()


def extract_repo_short_name(repo_full: str) -> str:
    """Extract short repo name: 'django/django' -> 'django'."""
    return repo_full.split("/")[-1].lower() if "/" in repo_full else repo_full.lower()


def main():
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {DATASET_NAME} from Hugging Face...")
    dataset = load_dataset(DATASET_NAME, split="test")
    total = len(dataset)
    print(f"Downloaded {total} tasks.\n")

    # Collect statistics
    repo_counter: Counter[str] = Counter()
    tasks_data = []

    for item in dataset:
        repo_full = item.get("repo", "unknown")
        repo_short = extract_repo_short_name(repo_full)
        repo_counter[repo_short] += 1

        tasks_data.append({
            "instance_id": item.get("instance_id", ""),
            "repo": repo_full,
            "repo_short": repo_short,
            "base_commit": item.get("base_commit", ""),
            "version": item.get("version", ""),
            "created_at": item.get("created_at", ""),
            "problem_statement": item.get("problem_statement", ""),
            "hints_text": item.get("hints_text", ""),
            "patch": item.get("patch", ""),
            "test_patch": item.get("test_patch", ""),
            "FAIL_TO_PASS": item.get("FAIL_TO_PASS", ""),
            "PASS_TO_PASS": item.get("PASS_TO_PASS", ""),
            "environment_setup_commit": item.get("environment_setup_commit", ""),
        })

    # Save full dataset as JSON
    data_file = output_dir / "data.json"
    data_file.write_text(json.dumps(tasks_data, indent=2, ensure_ascii=False))
    print(f"Saved dataset to: {data_file}")

    # Save metadata
    metadata = {
        "dataset_name": DATASET_NAME,
        "download_date": datetime.now(UTC).isoformat(),
        "total_tasks": total,
        "repository_count": len(repo_counter),
        "repositories": {
            repo: {"count": count} for repo, count in repo_counter.most_common()
        },
    }
    metadata_file = output_dir / "metadata.json"
    metadata_file.write_text(json.dumps(metadata, indent=2))
    print(f"Saved metadata to: {metadata_file}\n")

    # Print statistics
    print("=" * 60)
    print(f"SWE-bench Verified Dataset Statistics")
    print("=" * 60)
    print(f"Total tasks:      {total}")
    print(f"Repositories:     {len(repo_counter)}")
    print()
    print(f"{'Repository':<25} {'Tasks':>6}")
    print("-" * 33)
    for repo, count in repo_counter.most_common():
        print(f"{repo:<25} {count:>6}")
    print("-" * 33)
    print(f"{'TOTAL':<25} {total:>6}")
    print("=" * 60)


if __name__ == "__main__":
    main()
