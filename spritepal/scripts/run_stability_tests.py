#!/usr/bin/env python3
from __future__ import annotations

"""
Stability Test Runner

Script to run Phase 1 stability tests with proper reporting and validation.
Provides detailed output about which fixes are being validated.
"""

import subprocess
import sys
from pathlib import Path


def run_stability_tests():
    """Run the Phase 1 stability test suite with reporting."""

    print("=" * 70)
    print("PHASE 1 STABILITY TEST SUITE")
    print("=" * 70)
    print()

    print("Validating Phase 1 fixes:")
    print("  ✓ WorkerManager safe cancellation (no terminate())")
    print("  ✓ Circular reference prevention")
    print("  ✓ TOCTOU race condition fixes")
    print("  ✓ QTimer parent relationship fixes")
    print("  ✓ Thread safety improvements")
    print("  ✓ Memory leak prevention")
    print()

    # Path to the test file
    test_file = Path(__file__).parent.parent / "tests" / "test_phase1_stability_fixes.py"

    if not test_file.exists():
        print(f"❌ ERROR: Test file not found: {test_file}")
        return 1

    print(f"Running tests from: {test_file}")
    print("-" * 70)

    # Run the tests
    cmd = [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short", "--color=yes"]

    try:
        result = subprocess.run(cmd, check=False, cwd=test_file.parent.parent)

        print("-" * 70)
        if result.returncode == 0:
            print("✅ ALL STABILITY TESTS PASSED")
            print("Phase 1 fixes are working correctly!")
        else:
            print("❌ SOME TESTS FAILED")
            print("Please check the output above for details.")
            print("This may indicate regressions in Phase 1 fixes.")

        return result.returncode

    except KeyboardInterrupt:
        print("\n❌ Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ ERROR running tests: {e}")
        return 1


def run_quick_validation():
    """Run a quick validation of critical fixes."""

    print("=" * 70)
    print("QUICK STABILITY VALIDATION")
    print("=" * 70)
    print()

    test_file = Path(__file__).parent.parent / "tests" / "test_phase1_stability_fixes.py"

    if not test_file.exists():
        print(f"❌ ERROR: Test file not found: {test_file}")
        return 1

    # Run just the most critical tests
    critical_tests = [
        "TestWorkerCancellationStability::test_no_terminate_calls_in_codebase",
        "TestWorkerCancellationStability::test_worker_manager_safe_patterns",
        "TestTOCTOURaceConditionStability::test_manager_registry_thread_safety",
        "TestCircularReferenceStability::test_weak_reference_patterns",
    ]

    for test in critical_tests:
        print(f"Running: {test.split('::')[-1]}...")

        cmd = [sys.executable, "-m", "pytest", f"{test_file}::{test}", "-q"]

        result = subprocess.run(cmd, check=False, cwd=test_file.parent.parent, capture_output=True)

        if result.returncode == 0:
            print("  ✅ PASSED")
        else:
            print("  ❌ FAILED")
            return 1

    print()
    print("✅ ALL CRITICAL STABILITY TESTS PASSED")
    return 0


def main():
    """Main entry point."""

    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        return run_quick_validation()
    return run_stability_tests()


if __name__ == "__main__":
    sys.exit(main())
