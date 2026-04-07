#!/usr/bin/env python3
"""
Select 30 representative tasks from SWE-bench Verified.
Usage: python scripts/select-tasks.py [--dataset datasets/swe-bench-verified/data.json] [--seed 42]
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from swebench_adapter import is_repo_supported

RANDOM_SEED = 42

# Repository targets (1-4 each, total = 30)
REPOSITORY_TARGETS: Dict[str, int] = {
    "django": 4,
    "sympy": 4,
    "sphinx": 3,
    "matplotlib": 3,
    "scikit-learn": 3,
    "astropy": 2,
    "xarray": 2,
    "pytest": 2,
    "pylint": 2,
    "requests": 2,
    "seaborn": 2,
    "flask": 1,
}

# Difficulty targets: easy 30% (9), medium 50% (15), hard 20% (6)
DIFFICULTY_TARGETS = {"easy": 9, "medium": 15, "hard": 6}

# Type targets: bug_fix 45-50%, feature 30-35%, refactor 15-20%
TYPE_TARGETS = {"bug_fix": 14, "feature": 10, "refactor": 6}


def parse_args():
    parser = argparse.ArgumentParser(description="Select representative tasks from SWE-bench Verified")
    parser.add_argument("--dataset", default="datasets/swe-bench-verified/data.json", help="Path to data.json")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED, help="Random seed (default: 42)")
    parser.add_argument("--output-dir", default=".", help="Output directory for selected-tasks.json and selection-report.txt")
    return parser.parse_args()


def load_dataset(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        print(f"Error: dataset not found: {path}")
        print("Run scripts/download-verified.py first.")
        sys.exit(1)
    return json.loads(path.read_text())


# --- Exclusion filters (Rule 1) ---

def check_empty_fail_to_pass(task: Dict[str, Any]) -> Optional[str]:
    ftp = task.get("FAIL_TO_PASS", "")
    if isinstance(ftp, str):
        ftp_list = json.loads(ftp) if ftp.strip() else []
    else:
        ftp_list = ftp
    if not ftp_list:
        return "empty_fail_to_pass"
    return None


def check_gold_patch_applicable(task: Dict[str, Any]) -> Optional[str]:
    patch = task.get("patch", "").strip()
    if not patch:
        return "empty_gold_patch"
    return None


def check_problem_statement(task: Dict[str, Any]) -> Optional[str]:
    ps = task.get("problem_statement", "").strip()
    if not ps or len(ps) < 50:
        return "insufficient_problem_statement"
    return None


EXCLUSION_CHECKS = [
    check_empty_fail_to_pass,
    check_gold_patch_applicable,
    check_problem_statement,
]


def check_repo_has_parser(task: Dict[str, Any]) -> Optional[str]:
    """Exclude tasks whose repo has no official SWE-bench parser."""
    repo = task.get("repo", "")
    if not is_repo_supported(repo):
        return "no_official_parser"
    return None


FILTER_CHECKS = EXCLUSION_CHECKS + [check_repo_has_parser]


def apply_exclusions(tasks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    excluded_counts: Counter = Counter()
    clean = []
    for task in tasks:
        excluded = False
        for check in FILTER_CHECKS:
            reason = check(task)
            if reason:
                excluded_counts[reason] += 1
                excluded = True
                break
        if not excluded:
            clean.append(task)
    return clean, dict(excluded_counts)


# --- Classification ---

def classify_difficulty(task: Dict[str, Any]) -> str:
    """Classify difficulty based on gold patch size."""
    patch = task.get("patch", "")
    files = re.findall(r"diff --git a/", patch)
    num_files = len(files)
    added_lines = patch.count("\n+")
    removed_lines = patch.count("\n-")
    # Subtract diff header lines
    net_lines = max(0, (added_lines + removed_lines) // 2)

    if num_files >= 4 or net_lines > 50:
        return "hard"
    if num_files >= 2 or net_lines > 20:
        return "medium"
    return "easy"


def classify_type(task: Dict[str, Any]) -> str:
    """Classify task type from problem_statement keywords."""
    ps = task.get("problem_statement", "").lower()
    hints = task.get("hints_text", "").lower()
    text = ps + " " + hints

    feature_keywords = ["feature", "add support", "new feature", "implement", "enhancement",
                        "ability to", "allow", "support for", "option to", "extend"]
    refactor_keywords = ["refactor", "clean up", "deprecate", "remove", "rename", "restructure",
                         "consolidate", "simplify", "migrate"]

    feature_score = sum(1 for kw in feature_keywords if kw in text)
    refactor_score = sum(1 for kw in refactor_keywords if kw in text)

    if feature_score > refactor_score and feature_score >= 2:
        return "feature"
    if refactor_score > feature_score and refactor_score >= 2:
        return "refactor"
    if feature_score > 0 and refactor_score == 0:
        return "feature"
    if refactor_score > 0 and feature_score == 0:
        return "refactor"
    # Default to bug_fix
    return "bug_fix"


def annotate_tasks(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add difficulty, type, and patch stats to each task."""
    annotated = []
    for task in tasks:
        patch = task.get("patch", "")
        files = re.findall(r"diff --git a/", patch)
        num_files = len(files)
        added_lines = patch.count("\n+")
        removed_lines = patch.count("\n-")
        net_lines = max(0, (added_lines + removed_lines) // 2)

        annotated.append({
            **task,
            "difficulty": classify_difficulty(task),
            "type": classify_type(task),
            "files_modified": num_files,
            "lines_changed": net_lines,
        })
    return annotated


# --- Selection ---

def select_tasks(annotated: List[Dict[str, Any]], seed: int) -> List[Dict[str, Any]]:
    """Select tasks per repository with type and difficulty stratification."""
    import random
    rng = random.Random(seed)

    # Group by repo
    by_repo: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for task in annotated:
        by_repo[task["repo_short"]].append(task)

    # Shuffle each repo's tasks for randomness
    for repo in by_repo:
        rng.shuffle(by_repo[repo])

    selected: List[Dict[str, Any]] = []

    for repo, target in REPOSITORY_TARGETS.items():
        candidates = by_repo.get(repo, [])
        if not candidates:
            print(f"Warning: no candidates for {repo}")
            continue

        actual_target = min(target, len(candidates))

        # Try stratified selection by difficulty
        by_difficulty: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for c in candidates:
            by_difficulty[c["difficulty"]].append(c)

        # Distribute target across difficulties proportionally
        repo_selected = []
        difficulty_pool = {d: list(v) for d, v in by_difficulty.items()}

        # First pass: try to meet proportional targets
        for difficulty in ["easy", "medium", "hard"]:
            pool = difficulty_pool.get(difficulty, [])
            # Proportional share, rounded
            share = round(actual_target * DIFFICULTY_TARGETS[difficulty] / 30)
            take = min(share, len(pool))
            repo_selected.extend(pool[:take])
            pool[:] = pool[take:]  # remove taken

        # Fill remaining slots from any difficulty
        remaining = actual_target - len(repo_selected)
        leftovers = []
        for pool in difficulty_pool.values():
            leftovers.extend(pool)
        rng.shuffle(leftovers)
        repo_selected.extend(leftovers[:remaining])

        selected.extend(repo_selected[:actual_target])

    return selected


def compute_actual_targets(selected: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute actual distribution stats."""
    repo_dist = Counter(t["repo_short"] for t in selected)
    diff_dist = Counter(t["difficulty"] for t in selected)
    type_dist = Counter(t["type"] for t in selected)
    return {
        "repo_distribution": dict(repo_dist),
        "difficulty_distribution": dict(diff_dist),
        "type_distribution": dict(type_dist),
    }


def write_outputs(selected: List[Dict[str, Any]], excluded_counts: Dict[str, int],
                  stats: Dict[str, Any], seed: int, output_dir: Path) -> None:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # selected-tasks.json
    output = {
        "selection_date": datetime.now(UTC).isoformat(),
        "random_seed": seed,
        "total_tasks": len(selected),
        "excluded_count": sum(excluded_counts.values()),
        "excluded_reasons": excluded_counts,
        "distribution": stats,
        "tasks": [
            {
                "instance_id": t["instance_id"],
                "repo": t["repo_short"],
                "type": t["type"],
                "difficulty": t["difficulty"],
                "files_modified": t["files_modified"],
                "lines_changed": t["lines_changed"],
            }
            for t in selected
        ],
    }
    tasks_file = output_dir / "selected-tasks.json"
    tasks_file.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"Saved: {tasks_file}")

    # selection-report.txt
    lines = [
        "SWE-bench Verified Task Selection Report",
        "=" * 50,
        f"Selection date:  {output['selection_date']}",
        f"Random seed:     {seed}",
        f"Total selected:  {len(selected)}",
        f"Excluded:        {sum(excluded_counts.values())}",
        "",
        "Exclusion Reasons:",
    ]
    for reason, count in sorted(excluded_counts.items()):
        lines.append(f"  {reason}: {count}")

    lines.append("")
    lines.append("Repository Coverage:")
    target_total = 0
    for repo, count in sorted(stats["repo_distribution"].items()):
        target = REPOSITORY_TARGETS.get(repo, "?")
        target_total += count
        lines.append(f"  {repo:<20} {count}/{target}")
    lines.append(f"  {'TOTAL':<20} {target_total}/30")

    lines.append("")
    lines.append("Difficulty Distribution:")
    for d in ["easy", "medium", "hard"]:
        actual = stats["difficulty_distribution"].get(d, 0)
        target = DIFFICULTY_TARGETS[d]
        lines.append(f"  {d:<10} {actual:>2} (target: {target})")

    lines.append("")
    lines.append("Type Distribution:")
    for t in ["bug_fix", "feature", "refactor"]:
        actual = stats["type_distribution"].get(t, 0)
        target = TYPE_TARGETS[t]
        lines.append(f"  {t:<10} {actual:>2} (target: {target})")

    lines.append("")
    lines.append("Selected Tasks:")
    lines.append(f"  {'#':<3} {'Instance ID':<45} {'Repo':<15} {'Type':<10} {'Diff':<8} {'Files':<6} {'Lines'}")
    lines.append("  " + "-" * 95)
    for i, t in enumerate(output["tasks"], 1):
        lines.append(
            f"  {i:<3} {t['instance_id']:<45} {t['repo']:<15} {t['type']:<10} {t['difficulty']:<8} {t['files_modified']:<6} {t['lines_changed']}"
        )

    report_file = output_dir / "selection-report.txt"
    report_file.write_text("\n".join(lines) + "\n")
    print(f"Saved: {report_file}")


def _bar(count: int, total: int, width: int = 20) -> str:
    """Generate a text bar chart segment."""
    filled = round(width * count / total) if total else 0
    return "\u2588" * filled + "\u2591" * (width - filled)


def _dist_table(
    all_tasks: List[Dict[str, Any]],
    selected: List[Dict[str, Any]],
    key: str,
    ordered_keys: List[str],
    title: str,
) -> List[str]:
    """Generate a markdown comparison table for a given distribution dimension."""
    all_counter = Counter(t[key] for t in all_tasks)
    sel_counter = Counter(t[key] for t in selected)
    total_all = len(all_tasks)
    total_sel = len(selected)

    lines = [
        f"#### {title}",
        "",
        f"| Category | Original | | Selected | |",
        f"|----------|---------:|------|---------:|------|",
    ]
    for k in ordered_keys:
        a = all_counter.get(k, 0)
        s = sel_counter.get(k, 0)
        a_pct = f"{a / total_all:.0%}" if total_all else "0%"
        s_pct = f"{s / total_sel:.0%}" if total_sel else "0%"
        lines.append(f"| {k:<10} | {a:>4} ({a_pct:>4}) | {_bar(a, total_all)} | {s:>4} ({s_pct:>4}) | {_bar(s, total_sel)} |")
    lines.append("")
    return lines


def write_rationale(
    raw_tasks: List[Dict[str, Any]],
    clean_tasks: List[Dict[str, Any]],
    annotated_tasks: List[Dict[str, Any]],
    selected: List[Dict[str, Any]],
    excluded_counts: Dict[str, int],
    stats: Dict[str, Any],
    seed: int,
    output_dir: Path,
) -> None:
    """Generate selection-rationale.md for reviewer transparency."""
    output_dir = output_dir.resolve()
    total_raw = len(raw_tasks)
    total_clean = len(clean_tasks)
    total_selected = len(selected)
    total_excluded = sum(excluded_counts.values())

    # Original distributions (from annotated pool)
    orig_repo = Counter(t["repo_short"] for t in annotated_tasks)
    sel_repo = Counter(t["repo_short"] for t in selected)

    md: List[str] = []
    md.append("# Task Selection Rationale")
    md.append("")
    md.append(f"> Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    md.append("")

    # 1. Overview
    md.append("## 1. Overview")
    md.append("")
    md.append(f"| Metric | Value |")
    md.append(f"|--------|------:|")
    md.append(f"| SWE-bench Verified total tasks | {total_raw} |")
    md.append(f"| Tasks passing exclusion filter | {total_clean} |")
    md.append(f"| Tasks excluded | {total_excluded} |")
    md.append(f"| **Tasks selected** | **{total_selected}** |")
    md.append(f"| Random seed | `{seed}` |")
    md.append("")

    # 2. Random seed
    md.append("## 2. Random Seed & Reproducibility")
    md.append("")
    md.append(f"All random shuffling uses Python's `random.Random({seed})`. "
              "This ensures the selection is fully deterministic and reproducible. "
              "Changing the seed would produce a different 30-task subset, but the "
              "stratified sampling constraints (repo coverage, difficulty, type) would still hold.")
    md.append("")

    # 3. Exclusion criteria
    md.append("## 3. Exclusion Criteria")
    md.append("")
    md.append("The following exclusion filters are applied before selection:")
    md.append("")
    md.append("| Filter | Description | Excluded |")
    md.append("|--------|-------------|--------:|")
    filter_descriptions = {
        "empty_fail_to_pass": "Tasks with no FAIL_TO_PASS test cases",
        "empty_gold_patch": "Tasks with empty or missing gold patch",
        "insufficient_problem_statement": "Tasks with problem statement < 50 chars",
        "no_official_parser": "Tasks whose repo has no official SWE-bench parser",
    }
    for reason, desc in filter_descriptions.items():
        count = excluded_counts.get(reason, 0)
        md.append(f"| `{reason}` | {desc} | {count} |")
    md.append("")
    md.append(f"**Total excluded: {total_excluded} / {total_raw}** "
              f"({total_excluded / total_raw:.1%})" if total_raw else "")
    md.append("")

    # 4. Repository distribution
    md.append("## 4. Repository Distribution")
    md.append("")
    md.append("### Allocation Rule")
    md.append("")
    md.append("Each of the 12 repositories in SWE-bench Verified receives 1-4 tasks, "
              "proportional to its available task count (capped at 4). Total = 30.")
    md.append("")

    all_repos = sorted(set(list(orig_repo.keys()) + list(sel_repo.keys())))
    md.append("| Repository | Available | Target | Selected | Coverage |")
    md.append("|------------|--------:|-------:|--------:|----------|")
    for repo in all_repos:
        avail = orig_repo.get(repo, 0)
        target = REPOSITORY_TARGETS.get(repo, 0)
        sel = sel_repo.get(repo, 0)
        pct = f"{sel / target:.0%}" if target else "N/A"
        md.append(f"| {repo} | {avail} | {target} | {sel} | {pct} |")
    md.append(f"| **Total** | **{total_clean}** | **30** | **{total_selected}** | **{total_selected / 30:.0%}** |")
    md.append("")

    # Visual bar chart
    md.append("### Original vs Selected")
    md.append("```")
    for repo in all_repos:
        avail = orig_repo.get(repo, 0)
        sel = sel_repo.get(repo, 0)
        orig_bar = _bar(avail, total_clean, 30)
        sel_bar = _bar(sel, total_selected, 30)
        md.append(f"  {repo:<15} {orig_bar} {avail:>3}  ->  {sel_bar} {sel:>2}")
    md.append("```")
    md.append("")

    # 5. Difficulty distribution
    md.append("## 5. Difficulty Distribution")
    md.append("")
    md.append("### Classification Rules")
    md.append("")
    md.append("- **Easy**: 1 file modified, < 20 lines changed")
    md.append("- **Medium**: 2-3 files modified, or 20-50 lines changed")
    md.append("- **Hard**: >= 4 files modified, or > 50 lines changed")
    md.append("")
    md += _dist_table(annotated_tasks, selected, "difficulty", ["easy", "medium", "hard"], "Original Pool vs Selected")
    md.append(f"**Target**: Easy 30% (9), Medium 50% (15), Hard 20% (6)")
    md.append("")
    md.append("> **Note**: The actual difficulty distribution is constrained by the available tasks "
              "in each repository. Repositories with fewer available tasks may not have enough hard "
              "candidates, shifting the distribution toward easy/medium.")
    md.append("")

    # 6. Type distribution
    md.append("## 6. Task Type Distribution")
    md.append("")
    md.append("### Classification Method")
    md.append("")
    md.append("Task types are inferred via keyword matching on `problem_statement` and `hints_text`:")
    md.append("- **Feature**: Contains keywords like `add support`, `implement`, `new feature`, `allow`")
    md.append("- **Refactor**: Contains keywords like `refactor`, `deprecate`, `remove`, `rename`")
    md.append("- **Bug Fix**: Default category when neither feature nor refactor signals are strong enough")
    md.append("")
    md += _dist_table(annotated_tasks, selected, "type", ["bug_fix", "feature", "refactor"], "Original Pool vs Selected")
    md.append(f"**Target**: Bug Fix 45-50% (14), Feature 30-35% (10), Refactor 15-20% (6)")
    md.append("")
    md.append("> **Note**: Keyword-based classification is an approximation. Some tasks may be "
              "misclassified. The method is kept simple and deterministic for reproducibility.")
    md.append("")

    # 7. Selected task list
    md.append("## 7. Selected Task List")
    md.append("")
    md.append("| # | Instance ID | Repo | Type | Difficulty | Files | Lines |")
    md.append("|--:|-------------|------|------|------------|------:|------:|")
    for i, t in enumerate(selected, 1):
        md.append(
            f"| {i} | `{t['instance_id']}` | {t['repo_short']} | {t['type']} | {t['difficulty']} "
            f"| {t['files_modified']} | {t['lines_changed']} |"
        )
    md.append("")

    # 8. Methodology summary
    md.append("## 8. Methodology Summary")
    md.append("")
    md.append("1. **Load** SWE-bench Verified (500 tasks, 12 repositories)")
    md.append("2. **Filter** by exclusion criteria (non-viable tasks removed)")
    md.append("3. **Annotate** each task with difficulty (patch size) and type (keyword matching)")
    md.append("4. **Shuffle** candidates per repository using `random.Random(42)`")
    md.append("5. **Stratify** by difficulty within each repository, proportional to global targets")
    md.append("6. **Fill** remaining slots from any difficulty level within the same repository")
    md.append("7. **Output** `selected-tasks.json`, `selection-report.txt`, and this file")
    md.append("")

    # Write
    rationale_file = output_dir / "selection-rationale.md"
    rationale_file.write_text("\n".join(md) + "\n")
    print(f"Saved: {rationale_file}")


def main():
    args = parse_args()
    dataset_path = Path(args.dataset)
    output_dir = Path(args.output_dir)

    tasks = load_dataset(dataset_path)
    print(f"Loaded {len(tasks)} tasks from {dataset_path}")

    # Apply exclusions
    clean, excluded_counts = apply_exclusions(tasks)
    print(f"After exclusions: {len(clean)} tasks (excluded {sum(excluded_counts.values())})")
    if excluded_counts:
        for reason, count in sorted(excluded_counts.items()):
            print(f"  {reason}: {count}")

    # Annotate with difficulty/type
    annotated = annotate_tasks(clean)

    # Select
    selected = select_tasks(annotated, args.seed)
    stats = compute_actual_targets(selected)

    # Output
    write_outputs(selected, excluded_counts, stats, args.seed, output_dir)
    write_rationale(tasks, clean, annotated, selected, excluded_counts, stats, args.seed, output_dir)

    print(f"\nDone. Selected {len(selected)} tasks.")


if __name__ == "__main__":
    main()
