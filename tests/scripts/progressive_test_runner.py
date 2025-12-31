#!/usr/bin/env python3
"""
Progressive Test Runner for SpritePal

Runs tests in carefully designed stages to quickly identify and isolate issues.
This allows for efficient debugging and verification of fixes.

Usage:
    python progressive_test_runner.py
    python progressive_test_runner.py --stage smoke
    python progressive_test_runner.py --continue-on-failure
    python progressive_test_runner.py --verify-fixes
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class StageResult:
    """Results from running a single test stage."""

    name: str
    start_time: datetime
    duration: float
    total_tests: int
    passed: int
    failed: int
    errors: int
    skipped: int
    pass_rate: float
    command_used: list[str]
    output: str
    critical_failures: list[str]
    should_continue: bool


class ProgressiveTestRunner:
    """Orchestrates progressive test execution with intelligent stopping."""

    # Test stages in order of execution
    STAGES = [
        {
            "name": "infrastructure",
            "description": "Core infrastructure and imports",
            "tests": [
                "tests/test_constants.py",
                "tests/test_exceptions.py",
                "tests/infrastructure/test_mock_factory.py",
            ],
            "failure_threshold": 0.05,  # Stop if >5% fail
            "critical": True,
        },
        {
            "name": "unit_core",
            "description": "Core business logic units",
            "tests": [
                "tests/test_base_manager.py",
                "tests/test_manager_registry.py",
                "tests/test_session_manager.py",
                "tests/test_settings_manager.py",
            ],
            "failure_threshold": 0.10,  # Stop if >10% fail
            "critical": True,
        },
        {
            "name": "hal_compression",
            "description": "HAL compression functionality",
            "tests": [
                "tests/test_hal_compression.py",
            ],
            "failure_threshold": 0.20,  # HAL can be flaky
            "critical": False,
        },
        {
            "name": "workers_basic",
            "description": "Worker thread infrastructure",
            "tests": [
                "tests/test_worker_base.py",
                "tests/test_worker_extraction.py",
                "tests/test_worker_specialized.py",
            ],
            "failure_threshold": 0.15,
            "critical": False,
        },
        {
            "name": "extraction_core",
            "description": "Sprite extraction algorithms",
            "tests": [
                "tests/test_extractor.py",
                "tests/test_sprite_finder.py",
                "tests/test_extraction_manager.py",
            ],
            "failure_threshold": 0.15,
            "critical": False,
        },
        {
            "name": "injection_core",
            "description": "Sprite injection algorithms",
            "tests": [
                "tests/test_injector.py",
                "tests/test_injection_manager.py",
                "tests/test_rom_injection.py",
            ],
            "failure_threshold": 0.15,
            "critical": False,
        },
        {
            "name": "ui_basic",
            "description": "Basic UI components",
            "tests": [
                "tests/test_collapsible_group_box.py",
                "tests/test_sprite_preview_widget.py",
                "tests/test_error_handler.py",
            ],
            "failure_threshold": 0.20,  # UI can be more flaky
            "critical": False,
        },
        {
            "name": "integration_light",
            "description": "Lightweight integration tests",
            "tests": [
                "tests/test_controller.py",
                "tests/test_rom_cache.py",
                "tests/test_validation.py",
            ],
            "failure_threshold": 0.25,
            "critical": False,
        },
        {
            "name": "gui_dialogs",
            "description": "Dialog GUI components",
            "tests": [
                "tests/test_grid_arrangement_dialog_mock.py",
                "tests/test_manual_offset_dialog_singleton.py",
                "tests/test_settings_dialog_integration.py",
            ],
            "failure_threshold": 0.30,  # GUI tests can be very flaky
            "critical": False,
        },
        {
            "name": "integration_heavy",
            "description": "Complex integration scenarios",
            "tests": [
                "tests/test_complete_user_workflow_integration.py",
                "tests/test_drag_drop_integration.py",
                "tests/test_concurrent_operations.py",
            ],
            "failure_threshold": 0.40,
            "critical": False,
        },
        {
            "name": "performance",
            "description": "Performance and benchmarking tests",
            "tests": [
                "tests/test_performance_benchmarks.py",
                "tests/test_rom_cache_ui_integration.py",
            ],
            "failure_threshold": 0.50,  # Performance tests can be environment dependent
            "critical": False,
        },
        {
            "name": "full_remaining",
            "description": "All remaining tests",
            "tests": ["tests/"],
            "failure_threshold": 1.00,  # Run everything regardless
            "critical": False,
        },
    ]

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.results: list[StageResult] = []
        self.total_start_time = datetime.now()

    def run_all_stages(
        self, continue_on_failure: bool = False, max_stage: str | None = None, start_stage: str | None = None
    ) -> list[StageResult]:
        """Run all test stages progressively."""

        print("🚀 Starting Progressive Test Run")
        print("=" * 60)
        print(f"Start time: {self.total_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Project root: {self.project_root}")
        print()

        # Filter stages based on start/max stage
        stages_to_run = self._filter_stages(start_stage, max_stage)

        for i, stage_config in enumerate(stages_to_run, 1):
            stage_name = stage_config["name"]

            print(f"📋 Stage {i}/{len(stages_to_run)}: {stage_name}")
            print(f"   Description: {stage_config['description']}")
            print(f"   Critical: {'Yes' if stage_config['critical'] else 'No'}")

            # Run the stage
            result = self.run_stage(stage_config)
            self.results.append(result)

            # Print immediate results
            self._print_stage_summary(result)

            # Check if we should continue
            if not result.should_continue and not continue_on_failure:
                print("\n⚠️  High failure rate detected - stopping progressive run")
                print(f"   Failed stage: {stage_name}")
                print(f"   Pass rate: {result.pass_rate:.1%}")
                print(f"   Threshold: {stage_config['failure_threshold']:.1%}")
                break

            print()  # Blank line between stages

        # Print final summary
        self._print_final_summary()

        return self.results

    def _filter_stages(self, start_stage: str | None, max_stage: str | None) -> list[dict]:
        """Filter stages based on start and max stage parameters."""
        stages = self.STAGES[:]

        # Find start index
        start_idx = 0
        if start_stage:
            for i, stage in enumerate(stages):
                if stage["name"] == start_stage:
                    start_idx = i
                    break
            else:
                print(f"Warning: Start stage '{start_stage}' not found")

        # Find max index
        max_idx = len(stages)
        if max_stage:
            for i, stage in enumerate(stages):
                if stage["name"] == max_stage:
                    max_idx = i + 1
                    break
            else:
                print(f"Warning: Max stage '{max_stage}' not found")

        return stages[start_idx:max_idx]

    def run_stage(self, stage_config: dict) -> StageResult:
        """Run a single test stage."""
        stage_name = stage_config["name"]
        tests = stage_config["tests"]

        start_time = datetime.now()

        # Build pytest command
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "--tb=short",
            "--quiet",
            "--disable-warnings",
            "--timeout=120",  # 2 minute timeout per test
        ] + tests

        # Run the tests
        try:
            result = subprocess.run(
                cmd,
                check=False,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout for entire stage
            )

            duration = (datetime.now() - start_time).total_seconds()

            # Parse output
            return self._parse_stage_output(stage_name, start_time, duration, cmd, result, stage_config)

        except subprocess.TimeoutExpired:
            duration = 600  # Max timeout
            return StageResult(
                name=stage_name,
                start_time=start_time,
                duration=duration,
                total_tests=0,
                passed=0,
                failed=1,
                errors=1,
                skipped=0,
                pass_rate=0.0,
                command_used=cmd,
                output=f"Stage timed out after {duration}s",
                critical_failures=[f"Stage timeout: {stage_name}"],
                should_continue=False,
            )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return StageResult(
                name=stage_name,
                start_time=start_time,
                duration=duration,
                total_tests=0,
                passed=0,
                failed=1,
                errors=1,
                skipped=0,
                pass_rate=0.0,
                command_used=cmd,
                output=f"Exception: {e}",
                critical_failures=[f"Stage exception: {e}"],
                should_continue=False,
            )

    def _parse_stage_output(
        self,
        stage_name: str,
        start_time: datetime,
        duration: float,
        cmd: list[str],
        result: subprocess.CompletedProcess,
        stage_config: dict,
    ) -> StageResult:
        """Parse pytest output to extract test results."""

        output = result.stdout + result.stderr

        # Initialize counters
        total_tests = 0
        passed = 0
        failed = 0
        errors = 0
        skipped = 0

        # Parse pytest summary line
        # Examples: "5 passed, 2 failed, 1 skipped in 10.2s"
        import re

        # Look for final summary
        summary_patterns = [
            (r"(\d+) passed", "passed"),
            (r"(\d+) failed", "failed"),
            (r"(\d+) error", "errors"),
            (r"(\d+) skipped", "skipped"),
        ]

        for pattern, result_type in summary_patterns:
            matches = re.findall(pattern, output, re.IGNORECASE)
            if matches:
                count = int(matches[-1])  # Take last match
                if result_type == "passed":
                    passed = count
                elif result_type == "failed":
                    failed = count
                elif result_type == "errors":
                    errors = count
                elif result_type == "skipped":
                    skipped = count

        total_tests = passed + failed + errors + skipped

        # Calculate pass rate
        pass_rate = passed / total_tests if total_tests > 0 else 0.0

        # Extract critical failures (imports, syntax errors, etc.)
        critical_failures = []

        # Look for import errors
        if "ImportError" in output or "ModuleNotFoundError" in output:
            critical_failures.append("Import errors detected")

        # Look for syntax errors
        if "SyntaxError" in output:
            critical_failures.append("Syntax errors detected")

        # Look for fixture errors
        if "fixture" in output.lower() and "error" in output.lower():
            critical_failures.append("Fixture configuration errors")

        # Determine if we should continue
        failure_rate = (failed + errors) / total_tests if total_tests > 0 else 1.0
        threshold = stage_config["failure_threshold"]
        should_continue = failure_rate <= threshold or not stage_config["critical"]

        return StageResult(
            name=stage_name,
            start_time=start_time,
            duration=duration,
            total_tests=total_tests,
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            pass_rate=pass_rate,
            command_used=cmd,
            output=output,
            critical_failures=critical_failures,
            should_continue=should_continue,
        )

    def _print_stage_summary(self, result: StageResult):
        """Print summary for a single stage."""
        status_icon = "✅" if result.pass_rate >= 0.9 else "⚠️" if result.pass_rate >= 0.7 else "❌"

        print(f"   Result: {status_icon} {result.passed}/{result.total_tests} passed ({result.pass_rate:.1%})")
        print(f"   Duration: {result.duration:.1f}s")

        if result.failed > 0:
            print(f"   Failed: {result.failed}")
        if result.errors > 0:
            print(f"   Errors: {result.errors}")
        if result.critical_failures:
            print(f"   Critical issues: {', '.join(result.critical_failures)}")

    def _print_final_summary(self):
        """Print comprehensive summary of all stages."""
        total_duration = (datetime.now() - self.total_start_time).total_seconds()

        print("\n" + "=" * 60)
        print("📊 PROGRESSIVE TEST RUN SUMMARY")
        print("=" * 60)
        print(f"Total duration: {total_duration:.1f}s")
        print(f"Stages completed: {len(self.results)}")
        print()

        # Stage-by-stage summary
        print("Stage Results:")
        print("-" * 40)

        total_tests_all = 0
        total_passed_all = 0

        for result in self.results:
            status_icon = "✅" if result.pass_rate >= 0.9 else "⚠️" if result.pass_rate >= 0.7 else "❌"
            print(
                f"{status_icon} {result.name:20} {result.passed:>4}/{result.total_tests:<4} ({result.pass_rate:>5.1%}) {result.duration:>6.1f}s"
            )

            total_tests_all += result.total_tests
            total_passed_all += result.passed

        # Overall statistics
        overall_pass_rate = total_passed_all / total_tests_all if total_tests_all > 0 else 0.0

        print("-" * 40)
        print(
            f"{'Overall':20} {total_passed_all:>4}/{total_tests_all:<4} ({overall_pass_rate:>5.1%}) {total_duration:>6.1f}s"
        )
        print()

        # Health assessment
        if overall_pass_rate >= 0.95:
            health_status = "🟢 EXCELLENT - Test suite is healthy"
        elif overall_pass_rate >= 0.85:
            health_status = "🟡 GOOD - Minor issues to address"
        elif overall_pass_rate >= 0.70:
            health_status = "🟠 NEEDS IMPROVEMENT - Significant issues present"
        else:
            health_status = "🔴 CRITICAL - Major fixes needed"

        print(f"Health Status: {health_status}")

        # Identify problem areas
        problem_stages = [r for r in self.results if r.pass_rate < 0.8]
        if problem_stages:
            print("\nProblem Areas:")
            for result in problem_stages:
                print(f"  • {result.name}: {result.pass_rate:.1%} pass rate")
                for issue in result.critical_failures:
                    print(f"    - {issue}")

        # Next steps
        print("\nRecommended Next Steps:")

        if any(r.pass_rate < 0.5 for r in self.results):
            print("  1. Focus on stages with <50% pass rate first")

        critical_issues = []
        for result in self.results:
            critical_issues.extend(result.critical_failures)

        if "Import errors detected" in critical_issues:
            print("  2. Fix import errors (blocks other tests)")

        if "Fixture configuration errors" in critical_issues:
            print("  3. Fix fixture issues (affects multiple tests)")

        if any("timeout" in issue.lower() for issue in critical_issues):
            print("  4. Address timeout issues (may indicate deadlocks)")

        if not critical_issues and overall_pass_rate < 0.9:
            print("  2. Run detailed analysis on failing tests")
            print("  3. Focus on most affected test files")

        print()

    def save_results(self, filepath: Path | None = None) -> Path:
        """Save results to JSON file."""
        if filepath is None:
            timestamp = self.total_start_time.strftime("%Y%m%d_%H%M%S")
            filepath = self.project_root / "tests" / "scripts" / f"progressive_results_{timestamp}.json"

        # Convert results to serializable format
        data = {
            "start_time": self.total_start_time.isoformat(),
            "total_duration": (datetime.now() - self.total_start_time).total_seconds(),
            "stages": [],
        }

        for result in self.results:
            stage_data = {
                "name": result.name,
                "start_time": result.start_time.isoformat(),
                "duration": result.duration,
                "total_tests": result.total_tests,
                "passed": result.passed,
                "failed": result.failed,
                "errors": result.errors,
                "skipped": result.skipped,
                "pass_rate": result.pass_rate,
                "command_used": result.command_used,
                "critical_failures": result.critical_failures,
                "should_continue": result.should_continue,
                # Don't save full output to keep file size manageable
            }
            data["stages"].append(stage_data)

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with Path(filepath).open("w") as f:
            json.dump(data, f, indent=2)

        return filepath


def main():
    """Main entry point for progressive test runner."""
    parser = argparse.ArgumentParser(description="Progressive Test Runner for SpritePal")
    parser.add_argument("--stage", help="Run only specified stage")
    parser.add_argument("--start-stage", help="Start from specified stage")
    parser.add_argument("--max-stage", help="Stop at specified stage")
    parser.add_argument(
        "--continue-on-failure", action="store_true", help="Continue even if failure threshold exceeded"
    )
    parser.add_argument("--verify-fixes", action="store_true", help="Run in fix verification mode (lower thresholds)")
    parser.add_argument("--save-results", action="store_true", help="Save results to JSON file")
    parser.add_argument("--list-stages", action="store_true", help="List available stages")

    args = parser.parse_args()

    # Initialize runner
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    runner = ProgressiveTestRunner(project_root)

    # List stages if requested
    if args.list_stages:
        print("Available test stages:")
        print("-" * 40)
        for i, stage in enumerate(runner.STAGES, 1):
            critical_mark = " (CRITICAL)" if stage["critical"] else ""
            print(f"{i:2}. {stage['name']:20} - {stage['description']}{critical_mark}")
            print(f"    Tests: {len(stage['tests'])} files")
            print(f"    Failure threshold: {stage['failure_threshold']:.0%}")
            print()
        return

    # Run single stage if requested
    if args.stage:
        stage_config = None
        for stage in runner.STAGES:
            if stage["name"] == args.stage:
                stage_config = stage
                break

        if not stage_config:
            print(f"Error: Stage '{args.stage}' not found")
            print("Use --list-stages to see available stages")
            return

        print(f"Running single stage: {args.stage}")
        result = runner.run_stage(stage_config)
        runner.results = [result]
        runner._print_stage_summary(result)

    else:
        # Run progressive stages
        runner.run_all_stages(
            continue_on_failure=args.continue_on_failure, max_stage=args.max_stage, start_stage=args.start_stage
        )

    # Save results if requested
    if args.save_results:
        filepath = runner.save_results()
        print(f"Results saved to: {filepath}")


if __name__ == "__main__":
    main()
