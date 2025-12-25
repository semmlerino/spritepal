#!/usr/bin/env python3
from __future__ import annotations

"""
Type checking script for SpritePal tests.

Run this script to validate type safety improvements in the test suite.
"""

import subprocess
import sys
from pathlib import Path


def run_basedpyright():
    """Run basedpyright on the test files."""
    print("🔍 Running basedpyright type checking on tests...")

    try:
        result = subprocess.run([
            sys.executable, "-m", "basedpyright",
            "tests/",
            "--stats"
        ], capture_output=True, text=True, cwd=Path(__file__).parent)

        print("📊 Type checking results:")
        print(result.stdout)

        if result.stderr:
            print("⚠️  Warnings/Errors:")
            print(result.stderr)

        return result.returncode == 0

    except FileNotFoundError:
        print("❌ basedpyright not found. Install with: pip install basedpyright")
        return False

def run_mypy():
    """Run mypy as fallback type checker."""
    print("🔍 Running mypy type checking on tests...")

    try:
        result = subprocess.run([
            sys.executable, "-m", "mypy",
            "tests/test_type_safety_example.py",
            "tests/conftest.py",
            "--ignore-missing-imports",
            "--show-error-codes"
        ], capture_output=True, text=True, cwd=Path(__file__).parent)

        print("📊 MyPy results:")
        print(result.stdout)

        if result.stderr:
            print("⚠️  Warnings/Errors:")
            print(result.stderr)

        return result.returncode == 0

    except FileNotFoundError:
        print("❌ mypy not found. Install with: pip install mypy")
        return False

def validate_syntax():
    """Validate Python syntax of key test files."""
    print("🔍 Validating Python syntax...")

    test_files = [
        "tests/conftest.py",
        "tests/test_type_safety_example.py",
        "tests/test_worker_base.py",
    ]

    for file_path in test_files:
        try:
            result = subprocess.run([
                sys.executable, "-m", "py_compile", file_path
            ], capture_output=True, text=True, cwd=Path(__file__).parent)

            if result.returncode == 0:
                print(f"✅ {file_path}")
            else:
                print(f"❌ {file_path}: {result.stderr}")
                return False

        except Exception as e:
            print(f"❌ {file_path}: {e}")
            return False

    return True

def run_import_tests():
    """Test that improved imports work correctly."""
    print("🔍 Testing imports...")

    import_tests = [
        "import tests.conftest",
        "import tests.test_type_safety_example",
    ]

    for import_test in import_tests:
        try:
            result = subprocess.run([
                sys.executable, "-c", import_test
            ], capture_output=True, text=True, cwd=Path(__file__).parent)

            if result.returncode == 0:
                print(f"✅ {import_test}")
            else:
                print(f"❌ {import_test}: {result.stderr}")
                return False

        except Exception as e:
            print(f"❌ {import_test}: {e}")
            return False

    return True

def main():
    """Run all type safety validations."""
    print("🚀 SpritePal Test Type Safety Validation")
    print("=" * 50)

    all_passed = True

    # Step 1: Syntax validation
    all_passed &= validate_syntax()
    print()

    # Step 2: Import validation
    all_passed &= run_import_tests()
    print()

    # Step 3: Type checking (try basedpyright first, fallback to mypy)
    type_check_passed = run_basedpyright()
    if not type_check_passed:
        print("🔄 Falling back to mypy...")
        type_check_passed = run_mypy()

    all_passed &= type_check_passed
    print()

    # Summary
    if all_passed:
        print("🎉 All type safety validations passed!")
        print("\nNext steps:")
        print("- Run: pytest tests/test_type_safety_example.py")
        print("- Apply patterns to more test files")
        print("- Consider adding to CI/CD pipeline")
    else:
        print("❌ Some validations failed. Check output above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
