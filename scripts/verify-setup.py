#!/usr/bin/env python3
"""
Script to verify the experiment framework setup.

This script checks if all necessary components are properly set up and
lists the first 5 available tasks from SWE-bench Lite.
"""

import sys
from pathlib import Path


def check_directory_structure():
    """Verify that all required directories exist."""
    print("="*80)
    print("Checking Directory Structure")
    print("="*80 + "\n")

    required_dirs = [
        "docs",
        "datasets/swe-bench",
        "experiments",
        "scripts",
        "docker",
        "config"
    ]

    all_exist = True
    for dir_path in required_dirs:
        path = Path(dir_path)
        exists = path.exists()
        status = "✓" if exists else "✗"
        print(f"{status} {dir_path}")
        if not exists:
            all_exist = False

    print()
    return all_exist


def check_swebench_repo():
    """Check if SWE-bench repository is cloned."""
    print("="*80)
    print("Checking SWE-bench Repository")
    print("="*80 + "\n")

    repo_path = Path("datasets/swe-bench")
    if not repo_path.exists():
        print("✗ SWE-bench repository not found")
        print("  Run: git clone https://github.com/swe-bench/SWE-bench.git datasets/swe-bench")
        return False

    # Check for key files
    key_files = [
        "datasets/swe-bench/README.md",
        "datasets/swe-bench/swebench/__init__.py"
    ]

    all_exist = True
    for file_path in key_files:
        path = Path(file_path)
        exists = path.exists()
        status = "✓" if exists else "✗"
        print(f"{status} {file_path}")
        if not exists:
            all_exist = False

    print()
    return all_exist


def check_python_dependencies():
    """Check if required Python packages are installed."""
    print("="*80)
    print("Checking Python Dependencies")
    print("="*80 + "\n")

    required_packages = {
        'datasets': 'Hugging Face datasets library',
    }

    # Check swebench separately due to potential compatibility issues
    all_installed = True
    for package, description in required_packages.items():
        try:
            __import__(package)
            print(f"✓ {package} ({description})")
        except ImportError:
            print(f"✗ {package} ({description})")
            print(f"  Install with: pip install {package}")
            all_installed = False

    # Check swebench (may fail on older Python versions)
    try:
        import swebench
        print(f"✓ swebench (SWE-bench evaluation toolkit)")
    except Exception as e:
        print(f"⚠ swebench (SWE-bench evaluation toolkit)")
        print(f"  Note: swebench requires Python 3.10+. Error: {type(e).__name__}")
        print(f"  You can still use the framework without swebench installed.")

    print()
    return all_installed


def list_sample_tasks():
    """List first 5 tasks from SWE-bench Lite."""
    print("="*80)
    print("Sample Tasks from SWE-bench Lite (First 5)")
    print("="*80 + "\n")

    try:
        from datasets import load_dataset

        print("Loading SWE-bench Lite dataset...")
        dataset = load_dataset('princeton-nlp/SWE-bench_Lite', split='test')
        print(f"Total tasks available: {len(dataset)}\n")

        # Iterate over first 5 items
        for idx in range(min(5, len(dataset))):
            instance = dataset[idx]
            # Access using dictionary-style or attribute-style
            instance_id = instance['instance_id'] if isinstance(instance, dict) else instance.instance_id
            repo = instance['repo'] if isinstance(instance, dict) else instance.repo
            problem = instance['problem_statement'] if isinstance(instance, dict) else instance.problem_statement
            base_commit = instance['base_commit'] if isinstance(instance, dict) else instance.base_commit

            print(f"{idx + 1}. Instance ID: {instance_id}")
            print(f"   Repository: {repo}")
            print(f"   Base Commit: {base_commit}")
            problem_preview = problem[:100].replace('\n', ' ')
            print(f"   Problem: {problem_preview}{'...' if len(problem) > 100 else ''}")
            print()

        print("="*80)
        print("✓ Dataset loaded successfully!")
        print("="*80 + "\n")
        return True

    except Exception as e:
        print(f"✗ Error loading dataset: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def check_config_template():
    """Check if experiment configuration template exists."""
    print("="*80)
    print("Checking Configuration Template")
    print("="*80 + "\n")

    config_path = Path("config/experiment-config.json")
    if config_path.exists():
        print("✓ config/experiment-config.json exists")
        print()
        return True
    else:
        print("✗ config/experiment-config.json not found")
        print()
        return False


def main():
    """Main verification function."""
    print("\n" + "="*80)
    print("SWE-bench Lite Experiment Framework - Setup Verification")
    print("="*80 + "\n")

    checks = [
        ("Directory Structure", check_directory_structure),
        ("SWE-bench Repository", check_swebench_repo),
        ("Python Dependencies", check_python_dependencies),
        ("Configuration Template", check_config_template),
        ("Sample Tasks", list_sample_tasks)
    ]

    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"✗ Error during {name} check: {e}\n")
            results.append((name, False))

    # Summary
    print("="*80)
    print("Verification Summary")
    print("="*80 + "\n")

    all_passed = True
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
        if not result:
            all_passed = False

    print("\n" + "="*80)
    if all_passed:
        print("✓ All checks passed! Framework is ready to use.")
        print("\nNext steps:")
        print("1. Run: python scripts/list-swe-tasks.py")
        print("2. Select a task for your first experiment")
        print("3. Create an experiment configuration")
    else:
        print("✗ Some checks failed. Please resolve the issues above.")
        return 1
    print("="*80 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
