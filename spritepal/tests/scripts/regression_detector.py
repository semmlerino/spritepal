#!/usr/bin/env python3
"""
Regression Detection System for SpritePal Test Suite

Compares test results before and after fixes to detect regressions and measure improvements.
Provides detailed analysis of what changed and impact assessment.

Usage:
    python regression_detector.py --compare before_fix.json after_fix.json
    python regression_detector.py --baseline --tag "before_type_fixes"
    python regression_detector.py --auto-compare --days 7
    python regression_detector.py --verify-fix "type_annotations" --expected-improvement 50
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


@dataclass
class TestChange:
    """Represents a change in test status between runs."""

    test_name: str
    test_file: str
    before_status: str  # passed, failed, error, skipped, missing
    after_status: str
    before_duration: float
    after_duration: float
    change_type: str  # improvement, regression, new_failure, fixed, new_test, removed_test
    impact_score: float  # 0-1 score of impact severity


@dataclass
class RegressionReport:
    """Comprehensive regression analysis report."""

    comparison_id: str
    before_timestamp: datetime
    after_timestamp: datetime
    before_run_info: dict
    after_run_info: dict

    # Overall statistics
    total_before: int
    total_after: int
    tests_added: int
    tests_removed: int

    # Status changes
    improvements: list[TestChange] = field(default_factory=list)
    regressions: list[TestChange] = field(default_factory=list)
    new_failures: list[TestChange] = field(default_factory=list)
    fixed_tests: list[TestChange] = field(default_factory=list)

    # Performance changes
    performance_improvements: list[TestChange] = field(default_factory=list)
    performance_regressions: list[TestChange] = field(default_factory=list)

    # Category analysis
    category_changes: dict[str, dict[str, int]] = field(default_factory=dict)
    file_impact_analysis: dict[str, dict[str, int]] = field(default_factory=dict)

    # Summary metrics
    net_improvement_score: float = 0.0
    regression_risk_score: float = 0.0
    overall_health_change: float = 0.0


class RegressionDetector:
    """Detects regressions and improvements between test runs."""

    def __init__(self, results_dir: Path):
        self.results_dir = results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Impact scoring weights
        self.IMPACT_WEIGHTS = {
            "critical_test": 3.0,  # Tests marked as critical
            "infrastructure": 2.5,  # Core infrastructure tests
            "integration": 2.0,  # Integration tests
            "unit": 1.0,  # Regular unit tests
            "performance": 0.5,  # Performance tests
            "gui": 0.3,  # GUI tests (often flaky)
        }

        # Test file patterns for categorization
        self.TEST_PATTERNS = {
            "infrastructure": [
                "test_base_manager.py",
                "test_manager_registry.py",
                "test_exceptions.py",
                "test_constants.py",
                "infrastructure/",
                "conftest.py",
            ],
            "critical_test": [
                "test_controller.py",
                "test_extraction_manager.py",
                "test_injection_manager.py",
                "test_session_manager.py",
            ],
            "integration": [
                "integration",
                "workflow",
                "end_to_end",
                "complete_",
            ],
            "performance": [
                "performance",
                "benchmark",
                "cache",
            ],
            "gui": [
                "dialog",
                "widget",
                "ui_components",
                "preview",
                "grid_arrangement",
                "manual_offset",
            ],
        }

    def create_baseline(self, tag: str, description: str = "") -> Path:
        """Create a baseline snapshot of current test state."""
        print(f"Creating baseline: {tag}")

        # Run test suite to get current state
        result_file = self._run_test_suite(f"baseline_{tag}")

        # Create baseline record
        baseline_data = {
            "tag": tag,
            "description": description,
            "created": datetime.now().isoformat(),
            "result_file": str(result_file),
        }

        baseline_file = self.results_dir / f"baseline_{tag}.json"
        with Path(baseline_file).open("w") as f:
            json.dump(baseline_data, f, indent=2)

        print(f"Baseline created: {baseline_file}")
        return baseline_file

    def compare_results(self, before_file: Path, after_file: Path) -> RegressionReport:
        """Compare two test result files and generate regression report."""

        # Load test results
        with Path(before_file).open() as f:
            before_data = json.load(f)

        with Path(after_file).open() as f:
            after_data = json.load(f)

        # Create comparison ID
        comparison_id = hashlib.md5(f"{before_file.name}_{after_file.name}".encode()).hexdigest()[:8]

        # Initialize report
        report = RegressionReport(
            comparison_id=comparison_id,
            before_timestamp=datetime.fromisoformat(before_data.get("timestamp", datetime.now().isoformat())),
            after_timestamp=datetime.fromisoformat(after_data.get("timestamp", datetime.now().isoformat())),
            before_run_info=before_data,
            after_run_info=after_data,
            total_before=before_data.get("total_tests", 0),
            total_after=after_data.get("total_tests", 0),
            tests_added=0,
            tests_removed=0,
        )

        # Analyze changes
        self._analyze_test_changes(before_data, after_data, report)
        self._calculate_impact_scores(report)
        self._analyze_categories(before_data, after_data, report)
        self._calculate_summary_metrics(report)

        return report

    def _run_test_suite(self, run_id: str) -> Path:
        """Run test suite and capture results."""
        print("Running test suite to capture current state...")

        project_root = self.results_dir.parent.parent

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "--tb=short",
            "--quiet",
            "--junitxml=test_results.xml",  # type: ignore[attr-defined]
            "--durations=0",  # Capture all durations
        ]

        start_time = datetime.now()

        try:
            result = subprocess.run(
                cmd,
                check=False,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minute timeout
            )

            duration = (datetime.now() - start_time).total_seconds()

            # Parse results and save
            test_data = {
                "run_id": run_id,
                "timestamp": start_time.isoformat(),
                "duration": duration,
                "command": cmd,
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

            # Try to extract basic metrics from output
            self._extract_basic_metrics(result.stdout + result.stderr, test_data)

            # Save results
            result_file = self.results_dir / f"{run_id}_{start_time.strftime('%Y%m%d_%H%M%S')}.json"
            with Path(result_file).open("w") as f:
                json.dump(test_data, f, indent=2)

            return result_file

        except subprocess.TimeoutExpired:
            # Handle timeout case
            test_data = {
                "run_id": run_id,
                "timestamp": start_time.isoformat(),
                "duration": 1800,
                "timeout": True,
                "total_tests": 0,
                "passed_tests": 0,
                "failed_tests": 1,
                "error_tests": 0,
                "pass_rate": 0.0,
            }

            result_file = self.results_dir / f"{run_id}_timeout.json"
            with Path(result_file).open("w") as f:
                json.dump(test_data, f, indent=2)

            return result_file

    def _extract_basic_metrics(self, output: str, test_data: dict) -> None:
        """Extract basic test metrics from pytest output."""
        import re

        # Parse pytest summary
        passed = failed = errors = skipped = 0

        passed_match = re.search(r"(\d+) passed", output)
        if passed_match:
            passed = int(passed_match.group(1))

        failed_match = re.search(r"(\d+) failed", output)
        if failed_match:
            failed = int(failed_match.group(1))

        error_match = re.search(r"(\d+) error", output)
        if error_match:
            errors = int(error_match.group(1))

        skipped_match = re.search(r"(\d+) skipped", output)
        if skipped_match:
            skipped = int(skipped_match.group(1))

        total = passed + failed + errors + skipped

        test_data.update(
            {
                "total_tests": total,
                "passed_tests": passed,
                "failed_tests": failed,
                "error_tests": errors,
                "skipped_tests": skipped,
                "pass_rate": passed / total if total > 0 else 0.0,
            }
        )

    def _analyze_test_changes(self, before_data: dict, after_data: dict, report: RegressionReport) -> None:
        """Analyze individual test changes between runs."""

        # For now, work with high-level metrics since we don't have detailed per-test data
        # In a real implementation, you'd parse JUnit XML or use pytest-json-report

        before_passed = before_data.get("passed_tests", 0)
        after_passed = after_data.get("passed_tests", 0)
        before_failed = before_data.get("failed_tests", 0)
        after_failed = after_data.get("failed_tests", 0)

        # Calculate net changes
        net_passed_change = after_passed - before_passed
        net_failed_change = after_failed - before_failed

        # Create aggregate change records
        if net_passed_change > 0:
            # Tests were fixed
            change = TestChange(
                test_name="aggregate_improvements",
                test_file="multiple",
                before_status="failed",
                after_status="passed",
                before_duration=0.0,
                after_duration=0.0,
                change_type="fixed",
                impact_score=float(net_passed_change) * 0.1,
            )
            report.fixed_tests.append(change)

        if net_failed_change > 0:
            # New failures appeared
            change = TestChange(
                test_name="aggregate_regressions",
                test_file="multiple",
                before_status="passed",
                after_status="failed",
                before_duration=0.0,
                after_duration=0.0,
                change_type="regression",
                impact_score=float(net_failed_change) * 0.2,
            )
            report.regressions.append(change)

        # Test count changes
        report.tests_added = max(0, after_data.get("total_tests", 0) - before_data.get("total_tests", 0))
        report.tests_removed = max(0, before_data.get("total_tests", 0) - after_data.get("total_tests", 0))

    def _calculate_impact_scores(self, report: RegressionReport) -> None:
        """Calculate impact scores for all changes."""

        # For aggregate changes, impact is already calculated
        # In detailed implementation, you'd categorize each test and score accordingly
        pass

    def _analyze_categories(self, before_data: dict, after_data: dict, report: RegressionReport) -> None:
        """Analyze changes by test categories."""

        # Extract category information if available
        before_categories = before_data.get("failures_by_category", {})
        after_categories = after_data.get("failures_by_category", {})

        # Calculate category changes
        all_categories = set(before_categories.keys()) | set(after_categories.keys())

        for category in all_categories:
            before_count = before_categories.get(category, 0)
            after_count = after_categories.get(category, 0)

            report.category_changes[category] = {
                "before": before_count,
                "after": after_count,
                "change": after_count - before_count,
                "improvement": before_count - after_count,
            }

    def _calculate_summary_metrics(self, report: RegressionReport) -> None:
        """Calculate overall summary metrics."""

        # Net improvement score (positive is better)
        improvements_score = sum(change.impact_score for change in report.fixed_tests)
        regressions_score = sum(change.impact_score for change in report.regressions)
        report.net_improvement_score = improvements_score - regressions_score

        # Regression risk score (0-1, lower is better)
        total_impact = improvements_score + regressions_score
        report.regression_risk_score = regressions_score / total_impact if total_impact > 0 else 0.0

        # Overall health change
        before_health = report.before_run_info.get("pass_rate", 0.0)
        after_health = report.after_run_info.get("pass_rate", 0.0)
        report.overall_health_change = after_health - before_health

    def generate_report_text(self, report: RegressionReport) -> str:
        """Generate human-readable regression report."""

        lines = []
        lines.append("=" * 80)
        lines.append("REGRESSION DETECTION REPORT")
        lines.append("=" * 80)
        lines.append(f"Comparison ID: {report.comparison_id}")
        lines.append(f"Before: {report.before_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"After:  {report.after_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Overall summary
        lines.append("📊 OVERALL SUMMARY")
        lines.append("-" * 40)

        before_passed = report.before_run_info.get("passed_tests", 0)
        after_passed = report.after_run_info.get("passed_tests", 0)
        before_total = report.before_run_info.get("total_tests", 0)
        after_total = report.after_run_info.get("total_tests", 0)

        before_rate = report.before_run_info.get("pass_rate", 0.0)
        after_rate = report.after_run_info.get("pass_rate", 0.0)

        lines.append(f"Tests before:     {before_passed:>6}/{before_total:<6} ({before_rate:>5.1%})")
        lines.append(f"Tests after:      {after_passed:>6}/{after_total:<6} ({after_rate:>5.1%})")

        pass_change = after_passed - before_passed
        rate_change = after_rate - before_rate

        if pass_change > 0:
            lines.append(f"Improvement:      {pass_change:>+6} tests ({rate_change:>+5.1%}) ✅")
        elif pass_change < 0:
            lines.append(f"Regression:       {pass_change:>+6} tests ({rate_change:>+5.1%}) ❌")
        else:
            lines.append(f"No net change:    {pass_change:>+6} tests ({rate_change:>+5.1%}) ➡️")

        if report.tests_added > 0:
            lines.append(f"Tests added:      {report.tests_added:>6}")
        if report.tests_removed > 0:
            lines.append(f"Tests removed:    {report.tests_removed:>6}")

        lines.append("")

        # Health assessment
        if report.overall_health_change > 0.05:
            health_status = "🟢 SIGNIFICANT IMPROVEMENT"
        elif report.overall_health_change > 0.01:
            health_status = "🟡 MINOR IMPROVEMENT"
        elif report.overall_health_change > -0.01:
            health_status = "➡️  NO SIGNIFICANT CHANGE"
        elif report.overall_health_change > -0.05:
            health_status = "🟠 MINOR REGRESSION"
        else:
            health_status = "🔴 SIGNIFICANT REGRESSION"

        lines.append(f"Health Status: {health_status}")
        lines.append("")

        # Category analysis
        if report.category_changes:
            lines.append("🏷️  CATEGORY ANALYSIS")
            lines.append("-" * 40)

            for category, changes in report.category_changes.items():
                before = changes["before"]
                after = changes["after"]
                change = changes["change"]

                if change > 0:
                    trend = f"+{change} ❌"
                elif change < 0:
                    trend = f"{change} ✅"
                else:
                    trend = "±0 ➡️"

                lines.append(f"{category:25} {before:>4} → {after:<4} ({trend})")

            lines.append("")

        # Performance analysis
        before_duration = report.before_run_info.get("total_duration", 0.0)
        after_duration = report.after_run_info.get("total_duration", 0.0)

        if before_duration > 0 and after_duration > 0:
            duration_change = after_duration - before_duration
            duration_percent = duration_change / before_duration * 100

            lines.append("⏱️  PERFORMANCE ANALYSIS")
            lines.append("-" * 40)
            lines.append(f"Duration before:  {before_duration:>8.1f}s")
            lines.append(f"Duration after:   {after_duration:>8.1f}s")

            if duration_change < -10:
                perf_status = f"{duration_change:>+8.1f}s ({duration_percent:>+5.1f}%) 🚀 FASTER"
            elif duration_change < -1:
                perf_status = f"{duration_change:>+8.1f}s ({duration_percent:>+5.1f}%) ✅ SLIGHTLY FASTER"
            elif duration_change < 1:
                perf_status = f"{duration_change:>+8.1f}s ({duration_percent:>+5.1f}%) ➡️  SIMILAR"
            elif duration_change < 10:
                perf_status = f"{duration_change:>+8.1f}s ({duration_percent:>+5.1f}%) 🟡 SLIGHTLY SLOWER"
            else:
                perf_status = f"{duration_change:>+8.1f}s ({duration_percent:>+5.1f}%) ⚠️ SIGNIFICANTLY SLOWER"

            lines.append(f"Change:           {perf_status}")
            lines.append("")

        # Risk assessment
        lines.append("⚠️  RISK ASSESSMENT")
        lines.append("-" * 40)

        risk_factors = []

        if report.overall_health_change < -0.05:
            risk_factors.append("Significant decrease in pass rate")

        if report.tests_removed > 10:
            risk_factors.append(f"{report.tests_removed} tests were removed")

        if len(report.regressions) > 0:
            risk_factors.append(f"{len(report.regressions)} test regressions detected")

        if after_duration > before_duration * 1.5:
            risk_factors.append("Execution time increased by >50%")

        if not risk_factors:
            lines.append("✅ No significant risk factors detected")
        else:
            lines.append("⚠️  Risk factors identified:")
            for i, factor in enumerate(risk_factors, 1):
                lines.append(f"  {i}. {factor}")

        lines.append("")

        # Recommendations
        lines.append("💡 RECOMMENDATIONS")
        lines.append("-" * 40)

        if report.overall_health_change > 0.02:
            lines.append("✅ Good progress! Continue current fix strategy.")

        if len(risk_factors) > 0:
            lines.append("⚠️  Address risk factors before proceeding with more changes.")

        if report.category_changes:
            improving_categories = [
                cat for cat, changes in report.category_changes.items() if changes["improvement"] > 0
            ]
            if improving_categories:
                lines.append(f"✅ Focus on categories showing improvement: {', '.join(improving_categories)}")

        if after_duration > before_duration * 1.2:
            lines.append("⏱️  Investigate performance regression - tests running significantly slower.")

        return "\n".join(lines)

    def find_recent_comparisons(self, days: int = 7) -> list[tuple[Path, Path]]:
        """Find pairs of recent results for auto-comparison."""

        # Get all result files from last N days
        cutoff = datetime.now() - timedelta(days=days)
        recent_files = []

        for file_path in self.results_dir.glob("*.json"):
            if file_path.name.startswith("baseline_"):
                continue

            try:
                # Try to extract timestamp from filename
                parts = file_path.stem.split("_")
                if len(parts) >= 2:
                    date_str = f"{parts[-2]}_{parts[-1]}"
                    timestamp = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                    if timestamp >= cutoff:
                        recent_files.append((timestamp, file_path))
            except (ValueError, IndexError):
                # Skip files with invalid timestamp format
                continue

        # Sort by timestamp
        recent_files.sort(key=lambda x: x[0])

        # Create pairs for comparison
        pairs = []
        for i in range(len(recent_files) - 1):
            _before_time, before_file = recent_files[i]
            _after_time, after_file = recent_files[i + 1]
            pairs.append((before_file, after_file))

        return pairs

    def save_report(self, report: RegressionReport) -> Path:
        """Save regression report to file."""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.results_dir / f"regression_report_{report.comparison_id}_{timestamp}.json"

        # Convert to serializable format
        report_data = {
            "comparison_id": report.comparison_id,
            "before_timestamp": report.before_timestamp.isoformat(),
            "after_timestamp": report.after_timestamp.isoformat(),
            "before_run_info": report.before_run_info,
            "after_run_info": report.after_run_info,
            "total_before": report.total_before,
            "total_after": report.total_after,
            "tests_added": report.tests_added,
            "tests_removed": report.tests_removed,
            "improvements": [
                {
                    "test_name": change.test_name,
                    "test_file": change.test_file,
                    "change_type": change.change_type,
                    "impact_score": change.impact_score,
                }
                for change in report.improvements
            ],
            "regressions": [
                {
                    "test_name": change.test_name,
                    "test_file": change.test_file,
                    "change_type": change.change_type,
                    "impact_score": change.impact_score,
                }
                for change in report.regressions
            ],
            "category_changes": report.category_changes,
            "file_impact_analysis": report.file_impact_analysis,
            "net_improvement_score": report.net_improvement_score,
            "regression_risk_score": report.regression_risk_score,
            "overall_health_change": report.overall_health_change,
        }

        with Path(report_file).open("w") as f:
            json.dump(report_data, f, indent=2)

        return report_file


def main():
    """Main entry point for regression detector."""
    parser = argparse.ArgumentParser(description="Regression Detection System")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"), help="Compare two result files")
    parser.add_argument("--baseline", action="store_true", help="Create a new baseline")
    parser.add_argument("--tag", required=False, help="Tag for baseline (required with --baseline)")
    parser.add_argument("--description", default="", help="Description for baseline")
    parser.add_argument("--auto-compare", action="store_true", help="Auto-compare recent results")
    parser.add_argument("--days", type=int, default=7, help="Days to look back for auto-compare")
    parser.add_argument("--verify-fix", help="Verify specific fix with expected improvement")
    parser.add_argument("--expected-improvement", type=int, default=0, help="Expected number of test improvements")
    parser.add_argument("--save-report", action="store_true", help="Save detailed report to file")

    args = parser.parse_args()

    # Initialize detector
    script_dir = Path(__file__).parent
    results_dir = script_dir / "history"
    detector = RegressionDetector(results_dir)

    # Create baseline
    if args.baseline:
        if not args.tag:
            print("Error: --tag is required with --baseline")
            return

        detector.create_baseline(args.tag, args.description)
        return

    # Compare specific files
    if args.compare:
        before_file = Path(args.compare[0])
        after_file = Path(args.compare[1])

        if not before_file.exists():
            print(f"Error: Before file not found: {before_file}")
            return

        if not after_file.exists():
            print(f"Error: After file not found: {after_file}")
            return

        print(f"Comparing {before_file.name} → {after_file.name}")
        report = detector.compare_results(before_file, after_file)

        print(detector.generate_report_text(report))

        if args.save_report:
            report_file = detector.save_report(report)
            print(f"\nDetailed report saved to: {report_file}")

        return

    # Auto-compare recent results
    if args.auto_compare:
        pairs = detector.find_recent_comparisons(args.days)

        if not pairs:
            print(f"No result pairs found in last {args.days} days")
            return

        print(f"Found {len(pairs)} comparison pairs in last {args.days} days")

        for before_file, after_file in pairs:
            print(f"\n{'=' * 60}")
            print(f"Comparing {before_file.name} → {after_file.name}")
            print(f"{'=' * 60}")

            report = detector.compare_results(before_file, after_file)
            print(detector.generate_report_text(report))

            if args.save_report:
                report_file = detector.save_report(report)
                print(f"Report saved to: {report_file}")

        return

    # Verify specific fix
    if args.verify_fix:
        # This would require creating a before/after snapshot around the fix
        print(f"Fix verification for '{args.verify_fix}' not yet implemented")
        print("Use --baseline before making changes, then --compare after")
        return

    # Default: show usage
    print("No action specified. Use --help for usage information.")
    print("\nQuick examples:")
    print("  Create baseline:    python regression_detector.py --baseline --tag 'before_fixes'")
    print("  Compare files:      python regression_detector.py --compare before.json after.json")
    print("  Auto-compare:       python regression_detector.py --auto-compare")


if __name__ == "__main__":
    main()
