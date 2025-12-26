#!/usr/bin/env python3
from __future__ import annotations

"""
Script to run Qt signal/slot integration tests.

This script runs the comprehensive signal/slot integration tests with proper
environment setup and reporting.
"""

import subprocess
import sys
from pathlib import Path


def run_tests():
    """Run the signal/slot integration tests."""

    # Get the test file path
    test_file = Path(__file__).parent / "tests" / "integration" / "test_qt_signal_slot_integration.py"

    if not test_file.exists():
        print(f"Error: Test file not found: {test_file}")
        return 1

    print("=" * 80)
    print("Running Qt Signal/Slot Integration Tests")
    print("=" * 80)
    print()

    # Run with verbose output and capture
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_file),
        "-v",  # Verbose
        "-s",  # Show output
        "--tb=short",  # Short traceback
        "-m",
        "gui",  # Run GUI tests
        "--color=yes",
    ]

    print(f"Command: {' '.join(cmd)}")
    print()

    # Run the tests
    result = subprocess.run(cmd, capture_output=False, text=True)

    if result.returncode == 0:
        print()
        print("=" * 80)
        print("✓ All signal/slot integration tests passed!")
        print("=" * 80)
    else:
        print()
        print("=" * 80)
        print("✗ Some tests failed. See output above for details.")
        print("=" * 80)

    return result.returncode


if __name__ == "__main__":
    sys.exit(run_tests())
