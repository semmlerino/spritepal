#!/usr/bin/env python3
from __future__ import annotations

"""
Unified Manual Offset Dialog Performance Validation Runner

This script runs comprehensive performance validation of the unified manual offset dialog
against the established orchestration targets:
- ✅ Startup < 300ms
- ✅ Memory < 4MB
- ✅ Preview @ 60 FPS

Usage:
    python scripts/run_performance_validation.py [--verbose] [--benchmark] [--profile]

Options:
    --verbose    Show detailed performance metrics
    --benchmark  Run with pytest-benchmark for precise measurements
    --profile    Enable detailed CPU/memory profiling
    --export     Export results to JSON for analysis
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from ui.dialogs.manual_offset_dialog import (
    UnifiedManualOffsetDialog,
)

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Qt setup for headless testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Qt imports with proper handling
try:
    from PySide6.QtWidgets import QApplication, QWidget
    QT_AVAILABLE = True
except ImportError:
    # Fallback for testing without Qt
    QT_AVAILABLE = False
    from unittest.mock import Mock
    QApplication = QWidget = Mock

# Performance validation imports
try:
    from tests.test_unified_manual_offset_performance import (
        MemoryProfiler,
        PerformanceReportGenerator,
        PerformanceTargets,
        PreviewPerformanceBenchmark,
        ServiceAdapterOverheadAnalyzer,
        StartupBenchmark,
    )
except ImportError as e:
    print(f"❌ Error importing performance tests: {e}")
    print("Please run from the spritepal root directory")
    sys.exit(1)

def _create_dialog(parent=None) -> UnifiedManualOffsetDialog:
    """Create UnifiedManualOffsetDialog with injected dependencies."""
    from core.di_container import inject
    from core.protocols.manager_protocols import (
        ApplicationStateManager,
        ExtractionManagerProtocol,
    )
    from core.services.rom_cache import ROMCache

    return UnifiedManualOffsetDialog(
        parent,
        rom_cache=inject(ROMCache),
        settings_manager=inject(ApplicationStateManager),
        extraction_manager=inject(ExtractionManagerProtocol),
    )


class PerformanceValidationRunner:
    """Standalone performance validation runner."""

    def __init__(self, verbose: bool = False, profile: bool = False):
        self.verbose = verbose
        self.profile = profile
        self.app = None
        self.results = {}
        self._managers_initialized = False

    def setup_qt(self):
        """Setup Qt application for testing."""
        if QApplication.instance() is None:
            self.app = QApplication([])
        else:
            self.app = QApplication.instance()

        print("🔧 Qt application initialized for headless testing")

    def run_startup_validation(self) -> dict[str, Any]:
        """Run startup performance validation."""
        print("\n📊 Running Startup Performance Validation...")
        print("-" * 50)

        try:
            # Test unified dialog startup

            with patch("ui.dialogs.manual_offset_unified.get_preview_generator") as mock_prev, \
                 patch("ui.dialogs.manual_offset_unified.get_error_handler") as mock_err:

                mock_prev.return_value = Mock()
                mock_err.return_value = Mock()

                # Initialize managers if not done
                if not self._managers_initialized:
                    from core.managers import initialize_managers
                    initialize_managers()
                    self._managers_initialized = True

                def setup_dialog(dialog_class, parent):
                    # Use _create_dialog to inject dependencies
                    dialog = _create_dialog(parent)
                    dialog.setup_ui()
                    return dialog

                startup_metrics = StartupBenchmark.measure_dialog_startup(
                    UnifiedManualOffsetDialog, setup_dialog
                )

            # Evaluate results
            startup_time_ms = startup_metrics.get("total_startup_time_ms", 999)
            target_met = startup_time_ms < PerformanceTargets.STARTUP_TIME_MS

            print(f"  Startup Time: {startup_time_ms:.1f}ms (target: <{PerformanceTargets.STARTUP_TIME_MS}ms)")
            print(f"  Target Met: {'✅ YES' if target_met else '❌ NO'}")

            if self.verbose:
                print(f"  Initialization: {startup_metrics.get('initialization_time_ms', 0):.1f}ms")
                print(f"  Components: {startup_metrics.get('component_count', 0)}")
                print(f"  Signals: {startup_metrics.get('signal_count', 0)}")
                print(f"  Timers: {startup_metrics.get('timer_count', 0)}")

            return {
                "metrics": startup_metrics,
                "target_met": target_met,
                "performance_score": 100 if target_met else max(0, 100 - (startup_time_ms - PerformanceTargets.STARTUP_TIME_MS) / 10)
            }

        except Exception as e:
            print(f"  ❌ Error during startup validation: {e}")
            return {"metrics": {"error": str(e)}, "target_met": False, "performance_score": 0}

    def run_memory_validation(self) -> dict[str, Any]:
        """Run memory usage validation."""
        print("\n🧠 Running Memory Usage Validation...")
        print("-" * 50)

        try:
            profiler = MemoryProfiler()
            profiler.start_profiling()

            with patch("ui.dialogs.manual_offset_unified.get_preview_generator") as mock_prev, \
                 patch("ui.dialogs.manual_offset_unified.get_error_handler") as mock_err:

                mock_prev.return_value = Mock()
                mock_err.return_value = Mock()

                # Initialize managers if not done
                if not self._managers_initialized:
                    from core.managers import initialize_managers
                    initialize_managers()
                    self._managers_initialized = True

                # Create and use dialog
                parent = QWidget()
                dialog = _create_dialog(parent)
                dialog.setup_ui()
                dialog.set_rom_data("test.smc", 0x400000)

                # Simulate usage patterns
                for i in range(20):
                    if hasattr(dialog, "_on_offset_changed"):
                        dialog._on_offset_changed(0x200000 + i * 0x1000)

                    if hasattr(dialog, "_update_preview"):
                        dialog._update_preview()

                # Cleanup
                dialog.deleteLater()
                parent.deleteLater()

            memory_metrics = profiler.stop_profiling()

            # Evaluate results
            memory_mb = memory_metrics.get("memory_diff_mb", 999)
            target_met = memory_mb < PerformanceTargets.MEMORY_LIMIT_MB

            print(f"  Memory Usage: {memory_mb:.1f}MB (target: <{PerformanceTargets.MEMORY_LIMIT_MB}MB)")
            print(f"  Target Met: {'✅ YES' if target_met else '❌ NO'}")

            if self.verbose:
                print(f"  Initial Memory: {memory_metrics.get('initial_memory_mb', 0):.1f}MB")
                print(f"  Peak Traced: {memory_metrics.get('tracemalloc_peak_mb', 0):.1f}MB")

            return {
                "metrics": memory_metrics,
                "target_met": target_met,
                "performance_score": 100 if target_met else max(0, 100 - (memory_mb - PerformanceTargets.MEMORY_LIMIT_MB) * 25)
            }

        except Exception as e:
            print(f"  ❌ Error during memory validation: {e}")
            return {"metrics": {"error": str(e)}, "target_met": False, "performance_score": 0}

    def run_preview_validation(self) -> dict[str, Any]:
        """Run preview performance validation."""
        print("\n🖼️  Running Preview Performance Validation...")
        print("-" * 50)

        try:
            with patch("ui.dialogs.manual_offset_unified.get_preview_generator") as mock_prev, \
                 patch("ui.dialogs.manual_offset_unified.get_error_handler") as mock_err:

                mock_prev.return_value = Mock()
                mock_err.return_value = Mock()

                # Initialize managers if not done
                if not self._managers_initialized:
                    from core.managers import initialize_managers
                    initialize_managers()
                    self._managers_initialized = True

                # Create dialog
                parent = QWidget()
                dialog = _create_dialog(parent)
                dialog.setup_ui()
                dialog.set_rom_data("test.smc", 0x400000)

                # Measure preview performance
                preview_metrics = PreviewPerformanceBenchmark.measure_preview_performance(
                    dialog, iterations=30
                )

                # Cleanup
                dialog.deleteLater()
                parent.deleteLater()

            # Evaluate results
            avg_time_ms = preview_metrics.get("avg_time_ms", 999)
            fps_equivalent = preview_metrics.get("fps_equivalent", 0)
            target_met = preview_metrics.get("meets_target", False)

            print(f"  Preview Time: {avg_time_ms:.1f}ms (target: <{PerformanceTargets.PREVIEW_TIME_MS:.1f}ms)")
            print(f"  FPS Equivalent: {fps_equivalent:.1f} FPS (target: {PerformanceTargets.PREVIEW_FPS_TARGET} FPS)")
            print(f"  Target Met: {'✅ YES' if target_met else '❌ NO'}")

            if self.verbose:
                print(f"  Min/Max Time: {preview_metrics.get('min_time_ms', 0):.1f}/{preview_metrics.get('max_time_ms', 0):.1f}ms")
                print(f"  Total Iterations: {preview_metrics.get('iterations', 0)}")

            return {
                "metrics": preview_metrics,
                "target_met": target_met,
                "performance_score": 100 if target_met else max(0, 100 - (avg_time_ms - PerformanceTargets.PREVIEW_TIME_MS) * 5)
            }

        except Exception as e:
            print(f"  ❌ Error during preview validation: {e}")
            return {"metrics": {"error": str(e)}, "target_met": False, "performance_score": 0}

    def run_adapter_validation(self) -> dict[str, Any]:
        """Run service adapter overhead validation."""
        print("\n🔌 Running Service Adapter Overhead Analysis...")
        print("-" * 50)

        try:
            adapter_metrics = ServiceAdapterOverheadAnalyzer.measure_adapter_overhead()

            # Evaluate results
            creation_time_ms = adapter_metrics.get("adapter_creation_time_ms", 999)
            overhead_reasonable = creation_time_ms < 50  # 50ms threshold

            print(f"  Adapter Creation: {creation_time_ms:.1f}ms (threshold: <50ms)")
            print(f"  Overhead Acceptable: {'✅ YES' if overhead_reasonable else '❌ NO'}")

            if self.verbose:
                print(f"  Preview Overhead: {adapter_metrics.get('preview_adapter_overhead_ms', 0):.3f}ms per call")
                print(f"  Validation Overhead: {adapter_metrics.get('validation_adapter_overhead_ms', 0):.3f}ms per call")

            return {
                "metrics": adapter_metrics,
                "target_met": overhead_reasonable,
                "performance_score": 100 if overhead_reasonable else max(0, 100 - creation_time_ms)
            }

        except Exception as e:
            print(f"  ❌ Error during adapter validation: {e}")
            return {"metrics": {"error": str(e)}, "target_met": False, "performance_score": 0}

    def run_comprehensive_validation(self) -> dict[str, Any]:
        """Run comprehensive performance validation."""
        print("🚀 UNIFIED MANUAL OFFSET DIALOG PERFORMANCE VALIDATION")
        print("=" * 60)

        # Run all validations
        startup_results = self.run_startup_validation()
        memory_results = self.run_memory_validation()
        preview_results = self.run_preview_validation()
        adapter_results = self.run_adapter_validation()

        # Compile comprehensive report
        all_targets_met = all([
            startup_results["target_met"],
            memory_results["target_met"],
            preview_results["target_met"]
        ])

        overall_score = (
            startup_results["performance_score"] * 0.3 +
            memory_results["performance_score"] * 0.3 +
            preview_results["performance_score"] * 0.4
        )

        report = PerformanceReportGenerator.generate_validation_report(
            startup_results["metrics"],
            memory_results["metrics"],
            preview_results["metrics"],
            adapter_results["metrics"]
        )

        # Print summary
        print("\n📋 PERFORMANCE VALIDATION SUMMARY")
        print("=" * 60)
        print(f"Overall Performance Score: {overall_score:.1f}/100")
        print(f"All Critical Targets Met: {'✅ YES' if all_targets_met else '❌ NO'}")
        print()
        print("TARGET VALIDATION RESULTS:")
        print(f"  ✓ Startup < {PerformanceTargets.STARTUP_TIME_MS}ms: {'✅ PASS' if startup_results['target_met'] else '❌ FAIL'}")
        print(f"  ✓ Memory < {PerformanceTargets.MEMORY_LIMIT_MB}MB: {'✅ PASS' if memory_results['target_met'] else '❌ FAIL'}")
        print(f"  ✓ Preview @ {PerformanceTargets.PREVIEW_FPS_TARGET} FPS: {'✅ PASS' if preview_results['target_met'] else '❌ FAIL'}")
        print(f"  ✓ Adapter Overhead: {'✅ PASS' if adapter_results['target_met'] else '⚠️  WARNING'}")

        if report.get("bottlenecks"):
            print("\n⚠️  BOTTLENECKS IDENTIFIED:")
            for bottleneck in report["bottlenecks"]:
                print(f"  • {bottleneck}")

        if report.get("recommendations"):
            print("\n💡 OPTIMIZATION RECOMMENDATIONS:")
            for rec in report["recommendations"]:
                print(f"  • {rec}")

        # Final assessment
        print("\n🎯 FINAL ASSESSMENT:")
        if all_targets_met and overall_score >= 90:
            print("  🟢 EXCELLENT - All performance targets exceeded")
        elif all_targets_met and overall_score >= 80:
            print("  🟡 GOOD - All performance targets met with room for improvement")
        elif overall_score >= 70:
            print("  🟠 ACCEPTABLE - Some targets missed but performance adequate")
        else:
            print("  🔴 NEEDS OPTIMIZATION - Performance below acceptable thresholds")

        print("=" * 60)

        # Store complete results
        self.results = {
            "timestamp": time.time(),
            "overall_score": overall_score,
            "all_targets_met": all_targets_met,
            "startup": startup_results,
            "memory": memory_results,
            "preview": preview_results,
            "adapters": adapter_results,
            "comprehensive_report": report
        }

        return self.results

    def export_results(self, filepath: str):
        """Export validation results to JSON."""
        if not self.results:
            print("❌ No results to export. Run validation first.")
            return

        try:
            filepath_obj = Path(filepath)
            with filepath_obj.open("w") as f:
                json.dump(self.results, f, indent=2, default=str)
            print(f"📊 Results exported to: {filepath}")
        except Exception as e:
            print(f"❌ Failed to export results: {e}")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Unified Manual Offset Dialog Performance Validation")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed metrics")
    parser.add_argument("--benchmark", "-b", action="store_true", help="Run pytest-benchmark (more precise)")
    parser.add_argument("--profile", "-p", action="store_true", help="Enable detailed profiling")
    parser.add_argument("--export", "-e", type=str, help="Export results to JSON file")

    args = parser.parse_args()

    if args.benchmark:
        # Run with pytest-benchmark for more precise measurements
        cmd = [
            sys.executable, "-m", "pytest",
            "tests/test_unified_manual_offset_performance.py",
            "-v", "--tb=short", "--benchmark-only"
        ]
        result = subprocess.run(cmd, check=False, cwd=project_root)
        sys.exit(result.returncode)

    # Run standalone validation
    runner = PerformanceValidationRunner(verbose=args.verbose, profile=args.profile)
    runner.setup_qt()

    try:
        results = runner.run_comprehensive_validation()

        if args.export:
            runner.export_results(args.export)

        # Exit with appropriate code
        if results["all_targets_met"]:
            sys.exit(0)
        else:
            print("\n⚠️  Some performance targets not met. See recommendations above.")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n⏹️  Validation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Validation failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
