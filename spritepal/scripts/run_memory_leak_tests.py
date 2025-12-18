#!/usr/bin/env python3
from __future__ import annotations

"""
Run Memory Leak Tests

This script runs comprehensive memory leak detection tests for SpritePal,
generating detailed reports with concrete metrics for measuring improvements.

Usage:
    python scripts/run_memory_leak_tests.py
    python scripts/run_memory_leak_tests.py --rom path/to/rom.sfc --cycles 20
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from memory_leak_profiler import MemoryLeakProfiler
from PySide6.QtWidgets import QApplication


def setup_test_environment():
    """Set up the test environment for leak detection."""
    # Ensure we have a Qt application
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # Set up headless mode if no display
    if os.environ.get("DISPLAY") is None and sys.platform.startswith("linux"):
        print("No display detected, setting up headless mode...")
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    return app

def run_baseline_measurements(profiler: MemoryLeakProfiler, output_dir: Path):
    """Run baseline memory measurements."""
    print("Running baseline measurements...")

    # Establish baseline
    baseline = profiler.establish_baseline()

    # Save baseline metrics
    baseline_file = output_dir / "baseline_metrics.txt"
    with open(baseline_file, "w") as f:
        f.write("SpritePal Baseline Memory Metrics\n")
        f.write("=" * 40 + "\n")
        f.write(f"Timestamp: {baseline.timestamp}\n")
        f.write(f"Process Memory: {baseline.process_memory_mb:.2f} MB\n")
        f.write(f"Thread Count: {baseline.thread_count}\n")
        f.write(f"Python Objects: {sum(baseline.python_objects.values())}\n")
        f.write(f"Qt Objects: {sum(baseline.qt_objects.values())}\n")
        f.write("\nTop Python Objects:\n")

        f.writelines(f"  {obj_type}: {count}\n" for obj_type, count in sorted(baseline.python_objects.items(),
                                    key=lambda x: x[1], reverse=True)[:20])

        f.write("\nQt Objects:\n")
        f.writelines(f"  {obj_type}: {count}\n" for obj_type, count in sorted(baseline.qt_objects.items(),
                                    key=lambda x: x[1], reverse=True))

        f.write("\nGC Stats:\n")
        f.writelines(f"  {gen}: {count}\n" for gen, count in baseline.gc_stats.items())

    print(f"Baseline metrics saved to: {baseline_file}")
    return baseline

def run_dialog_leak_tests(profiler: MemoryLeakProfiler, cycles: int, output_dir: Path):
    """Run memory leak tests for all dialogs."""
    print(f"Running dialog leak tests ({cycles} cycles each)...")

    dialog_tests = [
        ("ManualOffsetDialog", "ui.dialogs.manual_offset_dialog", "ManualOffsetDialog"),
        ("AdvancedSearchDialog", "ui.dialogs.advanced_search_dialog", "AdvancedSearchDialog"),
        ("SettingsDialog", "ui.dialogs.settings_dialog", "SettingsDialog"),
        ("GridArrangementDialog", "ui.grid_arrangement_dialog", "GridArrangementDialog"),
        ("RowArrangementDialog", "ui.row_arrangement_dialog", "RowArrangementDialog"),
    ]

    results = {}

    for dialog_name, module_path, class_name in dialog_tests:
        print(f"\nTesting {dialog_name}...")

        try:
            # Dynamic import to avoid circular dependencies
            module = __import__(module_path, fromlist=[class_name])
            dialog_class = getattr(module, class_name)

            # Run leak test
            result = profiler.profile_dialog_lifecycle(
                dialog_name, dialog_class, cycles=cycles
            )
            results[dialog_name] = result

            # Save individual results
            result_file = output_dir / f"{dialog_name}_leak_test.txt"
            with open(result_file, "w") as f:
                f.write(f"{dialog_name} Memory Leak Test Results\n")
                f.write("=" * 50 + "\n")
                f.write(f"Cycles: {result.cycles_completed}\n")
                f.write(f"Memory Leaked: {result.memory_leaked_mb:.3f} MB\n")
                f.write(f"Per Cycle: {result.memory_leaked_per_cycle_mb * 1000:.1f} KB\n")
                f.write(f"Severity: {result.leak_severity}\n")
                f.write(f"Leak Detected: {result.leak_detected}\n\n")

                f.write("Object Deltas:\n")
                for obj_type, delta in sorted(result.objects_leaked.items(),
                                            key=lambda x: abs(x[1]), reverse=True):
                    if delta != 0:
                        f.write(f"  {obj_type}: {delta:+d}\n")

                if result.leak_details:
                    f.write("\nLeak Details:\n")
                    f.writelines(f"  {key}: {value}\n" for key, value in result.leak_details.items())

            print(f"  Result: {result.leak_severity} ({result.memory_leaked_mb:.3f} MB)")

        except Exception as e:
            print(f"  Failed to test {dialog_name}: {e}")
            results[dialog_name] = None

    return results

def run_worker_leak_tests(profiler: MemoryLeakProfiler, operations: int, output_dir: Path):
    """Run memory leak tests for worker threads."""
    print(f"Running worker leak tests ({operations} operations each)...")

    worker_tests = [
        ("PreviewWorker", "ui.rom_extraction.workers.preview_worker", "SpritePreviewWorker"),
        ("SearchWorker", "ui.rom_extraction.workers.search_worker", "SpriteSearchWorker"),
        ("ScanWorker", "ui.rom_extraction.workers.scan_worker", "SpriteScanWorker"),
    ]

    results = {}

    for worker_name, module_path, class_name in worker_tests:
        print(f"\nTesting {worker_name}...")

        try:
            # Dynamic import
            module = __import__(module_path, fromlist=[class_name])
            worker_class = getattr(module, class_name)

            # Create worker factory
            def worker_factory():
                return worker_class()

            # Run leak test
            result = profiler.profile_worker_operations(
                worker_name, worker_factory, operations=operations
            )
            results[worker_name] = result

            # Save individual results
            result_file = output_dir / f"{worker_name}_leak_test.txt"
            with open(result_file, "w") as f:
                f.write(f"{worker_name} Memory Leak Test Results\n")
                f.write("=" * 50 + "\n")
                f.write(f"Operations: {result.cycles_completed}\n")
                f.write(f"Memory Leaked: {result.memory_leaked_mb:.3f} MB\n")
                f.write(f"Per Operation: {result.memory_leaked_per_cycle_mb * 1000:.1f} KB\n")
                f.write(f"Severity: {result.leak_severity}\n")

                leaked_workers = result.leak_details.get("leaked_workers", 0)
                f.write(f"Leaked Workers: {leaked_workers}\n\n")

                f.write("Object Deltas:\n")
                for obj_type, delta in sorted(result.objects_leaked.items(),
                                            key=lambda x: abs(x[1]), reverse=True):
                    if delta != 0:
                        f.write(f"  {obj_type}: {delta:+d}\n")

            leaked_workers = result.leak_details.get("leaked_workers", 0)
            print(f"  Result: {result.leak_severity} ({result.memory_leaked_mb:.3f} MB, "
                  f"{leaked_workers} leaked workers)")

        except Exception as e:
            print(f"  Failed to test {worker_name}: {e}")
            results[worker_name] = None

    return results

def generate_summary_report(profiler: MemoryLeakProfiler, output_dir: Path):
    """Generate summary report with key metrics."""
    summary_file = output_dir / "memory_leak_summary.txt"

    with open(summary_file, "w") as f:
        f.write("SpritePal Memory Leak Test Summary\n")
        f.write("=" * 50 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Test results summary
        total_tests = len(profiler.test_results)  # type: ignore[attr-defined]
        leaked_tests = sum(1 for r in profiler.test_results.values() if r.leak_detected)  # type: ignore[attr-defined]
        severe_leaks = sum(1 for r in profiler.test_results.values() if r.leak_severity == "severe")  # type: ignore[attr-defined]

        f.write(f"Total Tests: {total_tests}\n")
        f.write(f"Tests with Leaks: {leaked_tests}\n")
        f.write(f"Severe Leaks: {severe_leaks}\n\n")

        # Key metrics for tracking
        f.write("KEY METRICS FOR LEAK TRACKING\n")
        f.write("-" * 30 + "\n")

        for test_name, result in sorted(profiler.test_results.items()):  # type: ignore[attr-defined]
            per_cycle_kb = result.memory_leaked_per_cycle_mb * 1000
            f.write(f"{test_name}:\n")
            f.write(f"  Memory per cycle: {per_cycle_kb:.1f} KB\n")
            f.write(f"  Total objects leaked: {sum(abs(v) for v in result.objects_leaked.values())}\n")
            f.write(f"  Severity: {result.leak_severity}\n")

            # Specific object types with largest leaks
            top_leaked = sorted(result.objects_leaked.items(),
                              key=lambda x: abs(x[1]), reverse=True)[:3]
            if any(abs(count) > 0 for _, count in top_leaked):
                f.write("  Top leaked objects:\n")
                for obj_type, count in top_leaked:
                    if abs(count) > 0:
                        f.write(f"    {obj_type}: {count:+d}\n")
            f.write("\n")

        # Critical findings
        f.write("CRITICAL FINDINGS\n")
        f.write("-" * 20 + "\n")

        critical_issues = []
        for test_name, result in profiler.test_results.items():  # type: ignore[attr-defined]
            per_cycle_kb = result.memory_leaked_per_cycle_mb * 1000

            if result.leak_severity == "severe":
                critical_issues.append(f"SEVERE: {test_name} leaks {per_cycle_kb:.1f}KB per cycle")
            elif per_cycle_kb > 100:  # More than 100KB per cycle
                critical_issues.append(f"HIGH: {test_name} leaks {per_cycle_kb:.1f}KB per cycle")

        if critical_issues:
            f.writelines(f"⚠️  {issue}\n" for issue in critical_issues)
        else:
            f.write("✅ No critical memory leaks detected\n")

        f.write("\n")

        # Recommendations
        f.write("RECOMMENDATIONS\n")
        f.write("-" * 15 + "\n")

        if severe_leaks > 0:
            f.write("1. IMMEDIATE ACTION REQUIRED - Severe leaks detected\n")
            f.write("2. Focus on dialog cleanup and proper object destruction\n")
            f.write("3. Verify signal disconnection on dialog close\n")
        elif leaked_tests > 0:
            f.write("1. Address detected leaks before release\n")
            f.write("2. Monitor leak growth with repeated testing\n")
            f.write("3. Focus on Qt object lifecycle management\n")
        else:
            f.write("1. Continue monitoring with regular leak tests\n")
            f.write("2. Maintain current good practices\n")

        f.write("\n")
        f.write("4. Use this baseline for regression testing\n")
        f.write("5. Re-run tests after implementing fixes to verify improvements\n")

    print(f"Summary report saved to: {summary_file}")

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Run comprehensive memory leak tests")
    parser.add_argument("--rom", help="Path to ROM file for extraction testing")
    parser.add_argument("--cycles", type=int, default=10,
                       help="Number of cycles for dialog tests (default: 10)")
    parser.add_argument("--operations", type=int, default=20,
                       help="Number of operations for worker tests (default: 20)")
    parser.add_argument("--output-dir", type=Path, default="memory_leak_results",
                       help="Output directory for results (default: memory_leak_results)")
    parser.add_argument("--baseline-only", action="store_true",
                       help="Only run baseline measurements")

    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(exist_ok=True)

    print("SpritePal Memory Leak Testing Suite")
    print("=" * 40)
    print(f"Output directory: {args.output_dir}")
    print(f"Dialog test cycles: {args.cycles}")
    print(f"Worker test operations: {args.operations}")
    print()

    # Set up test environment
    setup_test_environment()

    # Create profiler
    profiler = MemoryLeakProfiler()

    # Run baseline measurements
    run_baseline_measurements(profiler, args.output_dir)

    if args.baseline_only:
        print("Baseline-only mode complete.")
        return 0

    # Run dialog leak tests
    run_dialog_leak_tests(profiler, args.cycles, args.output_dir)

    # Run worker leak tests
    run_worker_leak_tests(profiler, args.operations, args.output_dir)

    # Run extraction tests if ROM provided
    if args.rom and os.path.exists(args.rom):
        print(f"\nRunning extraction leak tests with ROM: {args.rom}")
        try:
            profiler.profile_extraction_operations(args.rom, operations=10)
        except Exception as e:
            print(f"Extraction tests failed: {e}")

    # Generate comprehensive report
    print("\nGenerating comprehensive leak report...")
    full_report = profiler.generate_leak_report()

    report_file = args.output_dir / "comprehensive_leak_report.txt"
    with open(report_file, "w") as f:
        f.write(full_report)

    print(f"Comprehensive report saved to: {report_file}")

    # Generate summary report
    generate_summary_report(profiler, args.output_dir)

    print("\n" + "=" * 50)
    print("MEMORY LEAK TEST SUMMARY")
    print("=" * 50)

    # Count results
    total_tests = len(profiler.test_results)  # type: ignore[attr-defined]
    leaked_tests = sum(1 for r in profiler.test_results.values() if r.leak_detected)  # type: ignore[attr-defined]
    severe_leaks = sum(1 for r in profiler.test_results.values() if r.leak_severity == "severe")  # type: ignore[attr-defined]

    print(f"Tests completed: {total_tests}")
    print(f"Tests with leaks: {leaked_tests}")
    print(f"Severe leaks: {severe_leaks}")

    if severe_leaks > 0:
        print("\n🔴 CRITICAL: Severe memory leaks detected!")
        print("   Review the comprehensive report and fix immediately.")
    elif leaked_tests > 0:
        print("\n🟡 WARNING: Memory leaks detected")
        print("   Address these issues before release.")
    else:
        print("\n✅ SUCCESS: No significant memory leaks detected!")

    print(f"\nAll results saved to: {args.output_dir}/")

    return severe_leaks  # Return non-zero exit code if severe leaks found

if __name__ == "__main__":
    sys.exit(main())
