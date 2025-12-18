#!/usr/bin/env python3
from __future__ import annotations

"""
Dialog-Specific Memory Leak Profiler

This script provides focused memory leak profiling for individual dialogs,
allowing detailed analysis of specific components with customizable test parameters.

Usage:
    python scripts/profile_dialog_leaks.py --dialog ManualOffsetDialog --cycles 20
    python scripts/profile_dialog_leaks.py --dialog AdvancedSearchDialog --verbose
    python scripts/profile_dialog_leaks.py --list-dialogs
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from memory_leak_profiler import MemoryLeakProfiler
from PySide6.QtWidgets import QApplication, QDialog

# Dialog registry - maps dialog names to import info
DIALOG_REGISTRY = {
    "ManualOffsetDialog": {
        "module": "ui.dialogs.manual_offset_dialog",
        "class": "ManualOffsetDialog",
        "description": "Manual ROM offset browsing and preview dialog"
    },
    "AdvancedSearchDialog": {
        "module": "ui.dialogs.advanced_search_dialog",
        "class": "AdvancedSearchDialog",
        "description": "Advanced sprite search with filters and history"
    },
    "SettingsDialog": {
        "module": "ui.dialogs.settings_dialog",
        "class": "SettingsDialog",
        "description": "Application settings and preferences"
    },
    "GridArrangementDialog": {
        "module": "ui.grid_arrangement_dialog",
        "class": "GridArrangementDialog",
        "description": "Grid-based sprite arrangement editor"
    },
    "RowArrangementDialog": {
        "module": "ui.row_arrangement_dialog",
        "class": "RowArrangementDialog",
        "description": "Row-based sprite arrangement editor"
    },
    "UserErrorDialog": {
        "module": "ui.dialogs.user_error_dialog",
        "class": "UserErrorDialog",
        "description": "User-friendly error display dialog"
    }
}

def list_available_dialogs():
    """List all available dialogs for testing."""
    print("Available Dialogs for Memory Leak Testing:")
    print("=" * 50)

    for dialog_name, info in DIALOG_REGISTRY.items():
        print(f"{dialog_name}")
        print(f"  Description: {info['description']}")
        print(f"  Module: {info['module']}")
        print()

def load_dialog_class(dialog_name: str) -> type[QDialog]:
    """Dynamically load a dialog class."""
    if dialog_name not in DIALOG_REGISTRY:
        raise ValueError(f"Unknown dialog: {dialog_name}")

    info = DIALOG_REGISTRY[dialog_name]

    try:
        module = __import__(info["module"], fromlist=[info["class"]])
        return getattr(module, info["class"])
    except ImportError as e:
        raise ImportError(f"Failed to import {dialog_name}: {e}")
    except AttributeError as e:
        raise AttributeError(f"Class {info['class']} not found in {info['module']}: {e}")

def run_detailed_dialog_analysis(profiler: MemoryLeakProfiler, dialog_name: str,
                                dialog_class: type[QDialog], cycles: int,
                                verbose: bool = False) -> dict[str, Any]:
    """Run detailed analysis of a specific dialog."""
    print(f"Running detailed analysis of {dialog_name}")
    print(f"Test cycles: {cycles}")
    print(f"Verbose output: {verbose}")
    print("-" * 50)

    # Take pre-test snapshot
    pre_test_snapshot = profiler.take_memory_snapshot(f"{dialog_name}_pre_test")
    print(f"Pre-test memory: {pre_test_snapshot.process_memory_mb:.2f} MB")

    # Track individual cycles for detailed analysis
    cycle_snapshots = []
    dialog_instances = []

    print(f"\nRunning {cycles} open/close cycles...")

    for cycle in range(cycles):
        if verbose:
            print(f"  Cycle {cycle + 1}/{cycles}")

        cycle_start_time = time.time()

        # Take snapshot before creating dialog
        pre_cycle_snapshot = profiler.take_memory_snapshot(f"{dialog_name}_pre_cycle_{cycle}")

        try:
            # Create dialog
            dialog = dialog_class()
            dialog_instances.append(id(dialog))

            # Track all objects in dialog hierarchy
            profiler.qt_tracker.track_object(dialog)
            for child in dialog.findChildren(QDialog):
                profiler.qt_tracker.track_object(child)

            # Show dialog briefly
            dialog.show()
            QApplication.processEvents()

            # Simulate user interaction
            if verbose:
                print("    Dialog created and shown")

            time.sleep(0.1)  # Brief interaction time

            # Close dialog
            dialog.close()
            dialog.deleteLater()
            QApplication.processEvents()

            # Take snapshot after dialog cleanup
            post_cycle_snapshot = profiler.take_memory_snapshot(f"{dialog_name}_post_cycle_{cycle}")

            cycle_time = time.time() - cycle_start_time
            cycle_memory_delta = post_cycle_snapshot.memory_delta_mb(pre_cycle_snapshot)

            cycle_snapshots.append({
                "cycle": cycle + 1,
                "pre_snapshot": pre_cycle_snapshot,
                "post_snapshot": post_cycle_snapshot,
                "memory_delta_mb": cycle_memory_delta,
                "cycle_time": cycle_time
            })

            if verbose:
                print(f"    Cycle completed in {cycle_time:.3f}s, "
                      f"memory delta: {cycle_memory_delta:.3f} MB")

        except Exception as e:
            print(f"    ERROR in cycle {cycle + 1}: {e}")
            continue

        # Brief pause between cycles
        time.sleep(0.05)

    # Take post-test snapshot
    profiler.take_memory_snapshot(f"{dialog_name}_post_test")

    # Force garbage collection and wait
    import gc
    for i in range(3):
        gc.collect()
    time.sleep(1)
    QApplication.processEvents()

    # Take final snapshot after cleanup
    final_snapshot = profiler.take_memory_snapshot(f"{dialog_name}_final")

    # Analysis
    print(f"\nAnalysis Results for {dialog_name}")
    print("=" * 50)

    total_memory_delta = final_snapshot.memory_delta_mb(pre_test_snapshot)
    per_cycle_delta = total_memory_delta / cycles if cycles > 0 else 0

    print(f"Total memory delta: {total_memory_delta:.3f} MB")
    print(f"Per-cycle memory delta: {per_cycle_delta * 1000:.1f} KB")
    print(f"Pre-test memory: {pre_test_snapshot.process_memory_mb:.2f} MB")
    print(f"Final memory: {final_snapshot.process_memory_mb:.2f} MB")

    # Object analysis
    object_deltas = final_snapshot.object_deltas(pre_test_snapshot)
    leaked_objects = {k: v for k, v in object_deltas.items() if v > 0}

    if leaked_objects:
        print("\nObjects potentially leaked:")
        for obj_type, count in sorted(leaked_objects.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {obj_type}: +{count}")
    else:
        print("\nNo objects leaked detected.")

    # Cycle-by-cycle analysis
    if verbose and cycle_snapshots:
        print("\nCycle-by-cycle breakdown:")
        print("Cycle | Time (s) | Memory (KB) | Cumulative (KB)")
        print("-" * 50)

        cumulative_memory = 0
        for cycle_data in cycle_snapshots:
            cycle_memory_kb = cycle_data["memory_delta_mb"] * 1000
            cumulative_memory += cycle_memory_kb

            print(f"{cycle_data['cycle']:5d} | "
                  f"{cycle_data['cycle_time']:8.3f} | "
                  f"{cycle_memory_kb:11.1f} | "
                  f"{cumulative_memory:14.1f}")

    # Qt object analysis
    qt_objects = profiler.qt_tracker.get_live_objects()
    orphaned_objects = profiler.qt_tracker.get_orphaned_objects()

    print("\nQt Object Status:")
    print(f"Live Qt objects: {sum(qt_objects.values())}")

    if orphaned_objects:
        print("Orphaned objects (no parent, age > 30s):")
        for obj_type, age in orphaned_objects[:5]:
            print(f"  {obj_type}: {age:.1f}s old")

    # Memory allocation hotspots
    if hasattr(final_snapshot, "tracemalloc_top") and final_snapshot.tracemalloc_top:
        print("\nTop memory allocations:")
        for i, allocation in enumerate(final_snapshot.tracemalloc_top[:5], 1):
            print(f"  {i}. {allocation}")

    # Leak severity assessment
    severity = "none"
    if per_cycle_delta > 0.02:  # > 20KB per cycle
        severity = "severe"
    elif per_cycle_delta > 0.005:  # > 5KB per cycle
        severity = "moderate"
    elif per_cycle_delta > 0.001:  # > 1KB per cycle
        severity = "minor"

    print(f"\nLeak Severity: {severity}")

    # Recommendations
    print("\nRecommendations:")
    if severity == "severe":
        print("🔴 CRITICAL: Severe memory leak detected!")
        print("  - Immediate action required")
        print("  - Check dialog cleanup and signal disconnection")
        print("  - Verify all child objects are properly destroyed")
    elif severity == "moderate":
        print("🟡 WARNING: Moderate memory leak detected")
        print("  - Should be addressed before release")
        print("  - Review object lifecycle management")
    elif severity == "minor":
        print("🟠 MINOR: Small memory leak detected")
        print("  - Monitor for growth over time")
        print("  - Consider optimization when convenient")
    else:
        print("✅ GOOD: No significant memory leak detected")
        print("  - Continue current practices")

    return {
        "total_memory_delta_mb": total_memory_delta,
        "per_cycle_delta_kb": per_cycle_delta * 1000,
        "leaked_objects": leaked_objects,
        "severity": severity,
        "cycles_completed": cycles
    }

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Profile memory leaks in specific dialogs")
    parser.add_argument("--dialog", help="Dialog name to test")
    parser.add_argument("--cycles", type=int, default=10,
                       help="Number of open/close cycles (default: 10)")
    parser.add_argument("--verbose", action="store_true",
                       help="Enable verbose output")
    parser.add_argument("--list-dialogs", action="store_true",
                       help="List available dialogs")
    parser.add_argument("--output", help="Output file for detailed results")

    args = parser.parse_args()

    if args.list_dialogs:
        list_available_dialogs()
        return 0

    if not args.dialog:
        print("Error: --dialog parameter required")
        print("Use --list-dialogs to see available options")
        return 1

    print("SpritePal Dialog Memory Leak Profiler")
    print("=" * 40)
    print(f"Target dialog: {args.dialog}")

    # Set up Qt application
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # Set up headless mode if needed
    if os.environ.get("DISPLAY") is None and sys.platform.startswith("linux"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    # Load dialog class
    try:
        dialog_class = load_dialog_class(args.dialog)
        print(f"Dialog class loaded: {dialog_class.__name__}")
    except Exception as e:
        print(f"Error loading dialog: {e}")
        return 1

    # Create profiler
    profiler = MemoryLeakProfiler()

    # Establish baseline
    baseline = profiler.establish_baseline()
    print(f"Baseline memory: {baseline.process_memory_mb:.2f} MB")

    # Run detailed analysis
    try:
        results = run_detailed_dialog_analysis(
            profiler, args.dialog, dialog_class, args.cycles, args.verbose
        )

        # Save results if output file specified
        if args.output and results:
            with open(args.output, "w") as f:
                f.write(f"Dialog Memory Leak Analysis: {args.dialog}\n")
                f.write("=" * 50 + "\n")
                f.write(f"Cycles: {results['cycles_completed']}\n")
                f.write(f"Total memory delta: {results['total_memory_delta_mb']:.3f} MB\n")
                f.write(f"Per-cycle delta: {results['per_cycle_delta_kb']:.1f} KB\n")
                f.write(f"Severity: {results['severity']}\n\n")

                if results["leaked_objects"]:
                    f.write("Leaked objects:\n")
                    f.writelines(f"  {obj_type}: +{count}\n" for obj_type, count in results["leaked_objects"].items())

            print(f"\nResults saved to: {args.output}")

        # Return appropriate exit code
        if results and results["severity"] == "severe":
            return 2
        if results and results["severity"] in ["moderate", "minor"]:
            return 1
        return 0

    except Exception as e:
        print(f"Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
