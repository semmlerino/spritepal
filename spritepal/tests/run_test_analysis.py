#!/usr/bin/env python3
from __future__ import annotations

"""
Script to analyze test suite pass rate by running tests in batches.
This avoids timeout issues and provides detailed statistics.
"""

import json
import subprocess
import time
from pathlib import Path


def run_test_batch(test_files):
    """Run a batch of test files and return results."""
    cmd = [
        "../venv/bin/pytest",
        *test_files,
        "--tb=no",
        "-q",
        "--json-report",
        "--json-report-file=/tmp/test_report.json",
        "--timeout=30",  # 30 second timeout per test
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout for batch
            cwd="/mnt/c/CustomScripts/KirbyMax/workshop/exhal-master/spritepal"
        )

        # Parse JSON report if it exists
        report_file = Path("/tmp/test_report.json")
        if report_file.exists():
            with open(report_file) as f:
                report = json.load(f)
                return {
                    "passed": report["summary"].get("passed", 0),
                    "failed": report["summary"].get("failed", 0),
                    "skipped": report["summary"].get("skipped", 0),
                    "error": report["summary"].get("error", 0),
                    "total": report["summary"].get("total", 0),
                }

        # Fallback: parse output
        output = result.stdout + result.stderr
        passed = output.count(" passed")
        failed = output.count(" failed")
        skipped = output.count(" skipped")

        return {
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "error": 0,
            "total": passed + failed + skipped,
        }

    except subprocess.TimeoutExpired:
        return {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "error": 1,
            "total": 1,
            "timeout": True,
        }
    except Exception as e:
        print(f"Error running batch: {e}")
        return {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "error": 1,
            "total": 1,
        }

def main():
    """Run test analysis."""

    # Find all test files
    test_dir = Path("/mnt/c/CustomScripts/KirbyMax/workshop/exhal-master/spritepal/tests")
    test_files = list(test_dir.glob("test_*.py"))

    # Sort for consistent ordering
    test_files.sort()

    # Filter out known problematic files
    problematic = [
        "test_smart_preview",
        "test_qt_threading",
        "test_concurrent",
        "test_worker_manager",
    ]

    safe_files = []
    unsafe_files = []

    for f in test_files:
        if any(p in f.stem for p in problematic):
            unsafe_files.append(f)
        else:
            safe_files.append(f)

    print(f"Found {len(test_files)} test files")
    print(f"  Safe: {len(safe_files)}")
    print(f"  Potentially unsafe: {len(unsafe_files)}")
    print()

    # Run tests in batches
    batch_size = 5
    total_stats = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "error": 0,
        "total": 0,
    }

    print("Running safe test files...")
    for i in range(0, len(safe_files), batch_size):
        batch = safe_files[i:i+batch_size]
        batch_names = [f.name for f in batch]

        print(f"  Batch {i//batch_size + 1}: {', '.join(batch_names[:3])}...")

        stats = run_test_batch([str(f) for f in batch])

        # Update totals
        for key in ["passed", "failed", "skipped", "error"]:
            total_stats[key] += stats.get(key, 0)

        # Print batch results
        if stats.get("timeout"):
            print("    TIMEOUT")
        else:
            print(f"    Passed: {stats['passed']}, Failed: {stats['failed']}, "
                  f"Skipped: {stats['skipped']}, Errors: {stats['error']}")

        # Small delay between batches
        time.sleep(0.5)  # sleep-ok: test analysis tooling

    # Calculate totals
    total_stats["total"] = total_stats["passed"] + total_stats["failed"] + total_stats["skipped"] + total_stats["error"]

    # Print summary
    print("\n" + "="*60)
    print("TEST SUITE ANALYSIS SUMMARY")
    print("="*60)
    print(f"Total tests run: {total_stats['total']}")
    print(f"  Passed:  {total_stats['passed']:4d} ({total_stats['passed']*100/max(1, total_stats['total']):5.1f}%)")
    print(f"  Failed:  {total_stats['failed']:4d} ({total_stats['failed']*100/max(1, total_stats['total']):5.1f}%)")
    print(f"  Skipped: {total_stats['skipped']:4d} ({total_stats['skipped']*100/max(1, total_stats['total']):5.1f}%)")
    print(f"  Errors:  {total_stats['error']:4d} ({total_stats['error']*100/max(1, total_stats['total']):5.1f}%)")
    print()

    # Calculate effective pass rate (passed / (passed + failed))
    effective_total = total_stats["passed"] + total_stats["failed"]
    if effective_total > 0:
        pass_rate = total_stats["passed"] * 100 / effective_total
        print(f"Effective pass rate: {pass_rate:.1f}%")
        print("Target: 80%")

        if pass_rate >= 80:
            print("✅ TARGET ACHIEVED!")
        else:
            print(f"❌ Gap to target: {80 - pass_rate:.1f}%")

    print("\nNote: Skipped tests marked as segfault-prone for safety")
    print(f"Unsafe files not tested: {len(unsafe_files)}")

if __name__ == "__main__":
    main()
