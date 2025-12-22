#!/usr/bin/env python3
"""
Test Health Dashboard for SpritePal Test Suite

Comprehensive monitoring and analysis tool for tracking test suite health,
identifying failure patterns, and measuring improvement progress.

Usage:
    python test_health_dashboard.py --run-tests --analyze --report
    python test_health_dashboard.py --quick-check
    python test_health_dashboard.py --historical --compare last-week
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Type aliases for clarity
TestResult = dict[str, str | int | float | bool]

# Serial execution required: Thread safety concerns
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.performance,
    pytest.mark.slow,
]
FailureCategory = str
TestMetrics = dict[str, int | float]

@dataclass
class FailureRecord:
    """Represents a single test failure with categorization."""
    test_name: str
    test_file: str
    failure_type: str
    error_message: str
    traceback: str
    duration: float
    category: FailureCategory
    is_timeout: bool = False
    is_import_error: bool = False
    is_type_error: bool = False
    is_mock_related: bool = False
    is_qt_related: bool = False

@dataclass
class SuiteMetrics:
    """Comprehensive test suite metrics."""
    timestamp: datetime
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    error_tests: int

    # Performance metrics
    total_duration: float
    average_duration: float
    median_duration: float
    slowest_tests: list[tuple[str, float]] = field(default_factory=list)

    # Failure analysis
    failures_by_category: dict[FailureCategory, int] = field(default_factory=dict)
    failures_by_file: dict[str, int] = field(default_factory=dict)
    timeout_failures: int = 0
    import_failures: int = 0
    type_failures: int = 0
    mock_failures: int = 0
    qt_failures: int = 0

    # Health indicators
    pass_rate: float = 0.0
    improvement_trend: float = 0.0
    critical_failures: int = 0
    quick_wins_available: int = 0

class FailureCategorizer:
    """Categorizes test failures based on error patterns."""

    CATEGORY_PATTERNS = {
        'type_annotation': [
            r'TypeError.*type object',
            r'ArgumentError.*type',
            r'NameError.*not defined',
            r'AttributeError.*type object',
            r'unsupported operand type',
            r'invalid type in comparison',
            r'Union\[.*\] object',
        ],
        'timeout': [
            r'timeout',
            r'TimeoutError',
            r'pytest timeout',
            r'test session starts \(platform',
            r'timed out after \d+',
        ],
        'import_error': [
            r'ImportError',
            r'ModuleNotFoundError',
            r'cannot import name',
            r'circular import',
            r'No module named',
        ],
        'qt_related': [
            r'QApplication',
            r'QWidget',
            r'QDialog',
            r'qtbot',
            r'QTest',
            r'QSignal',
            r'QTimer',
            r'PySide6',
            r'PySide6',
        ],
        'mock_related': [
            r'Mock.*object',
            r'MagicMock',
            r'patch.*object',
            r'mock.*attribute',
            r'MockFactory',
            r'assert_called',
            r'side_effect',
        ],
        'hal_compression': [
            r'HAL.*compression',
            r'compression.*error',
            r'exhal',
            r'inhal',
            r'BrokenPipeError',
            r'subprocess.*hal',
        ],
        'threading': [
            r'thread',
            r'QThread',
            r'Worker.*thread',
            r'ThreadPoolExecutor',
            r'concurrent.futures',
            r'race condition',
            r'deadlock',
        ],
        'file_operations': [
            r'FileNotFoundError',
            r'PermissionError',
            r'OSError.*file',
            r'IOError',
            r'file.*not found',
            r'directory.*not found',
        ],
        'memory_issues': [
            r'MemoryError',
            r'out of memory',
            r'allocation failed',
            r'memory.*overflow',
        ],
        'logic_bugs': [
            r'AssertionError',
            r'ValueError.*invalid',
            r'IndexError',
            r'KeyError',
            r'AttributeError.*object.*no attribute',
        ],
    }

    def categorize_failure(self, failure_info: dict[str, str]) -> FailureCategory:
        """Categorize a failure based on error message and traceback."""
        combined_text = f"{failure_info.get('message', '')} {failure_info.get('traceback', '')}"
        combined_text = combined_text.lower()

        # Check patterns in order of specificity
        for category, patterns in self.CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, combined_text, re.IGNORECASE):
                    return category

        return 'uncategorized'

    def analyze_failure_trends(self, failures: list[FailureRecord]) -> dict[str, any]:
        """Analyze failure trends and patterns."""
        category_counts = Counter(f.category for f in failures)
        file_counts = Counter(f.test_file for f in failures)

        # Identify quick wins (categories with many simple fixes)
        quick_win_categories = {
            'type_annotation': 0.8,  # 80% can be fixed quickly
            'import_error': 0.9,     # 90% can be fixed quickly
            'mock_related': 0.6,     # 60% can be fixed quickly
        }

        quick_wins = sum(
            int(category_counts[cat] * percentage)
            for cat, percentage in quick_win_categories.items()
            if cat in category_counts
        )

        return {
            'category_distribution': dict(category_counts),
            'file_distribution': dict(file_counts.most_common(10)),
            'quick_wins_estimate': quick_wins,
            'critical_categories': [cat for cat, count in category_counts.items() if count >= 10],
            'affected_files': len(file_counts),
        }

class HealthTestRunner:
    """Handles test execution with different strategies."""

    def __init__(self, test_dir: Path):
        self.test_dir = test_dir
        self.project_root = test_dir.parent

    def run_progressive_tests(self) -> dict[str, SuiteMetrics]:
        """Run tests in progressive stages to quickly identify issues."""
        stages = [
            ("smoke_tests", [
                "tests/test_constants.py",
                "tests/test_base_manager.py",
                "tests/test_exceptions.py",
            ]),
            ("unit_core", ["-m", "not gui and not integration"]),
            ("integration", ["-m", "integration and not gui"]),
            ("gui_basic", [
                "tests/test_collapsible_group_box.py",
                "tests/test_sprite_preview_widget.py",
            ]),
            ("full_suite", ["tests/"]),
        ]

        results = {}

        for stage_name, test_args in stages:
            print(f"Running {stage_name} tests...")
            metrics = self._run_test_stage(stage_name, test_args)
            results[stage_name] = metrics

            # Stop if failure rate is too high (>10% for early stages)
            if metrics.total_tests > 0 and metrics.pass_rate < 0.9 and stage_name != "full_suite":
                print(f"High failure rate in {stage_name}: {metrics.pass_rate:.1%}")
                print("Stopping progressive run for analysis.")
                break

        return results

    def _run_test_stage(self, stage_name: str, test_args: list[str]) -> SuiteMetrics:
        """Run a single stage of tests and collect metrics."""
        start_time = time.time()

        # Prepare pytest command
        cmd = [
            sys.executable, "-m", "pytest",
            "--tb=short",
            "--quiet",
            "--junitxml=test_results.xml",  # type: ignore[attr-defined]
            "--durations=10",
            "--timeout=120",  # 2 minute timeout per test
        ] + test_args

        try:
            # Run tests
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout for entire stage
            )

            total_duration = time.time() - start_time

            # Parse results
            return self._parse_test_results(stage_name, result, total_duration)  # type: ignore[attr-defined]

        except subprocess.TimeoutExpired:
            return SuiteMetrics(
                timestamp=datetime.now(),
                total_tests=0,
                passed_tests=0,
                failed_tests=1,
                skipped_tests=0,
                error_tests=0,
                total_duration=600,
                average_duration=600,
                median_duration=600,
                timeout_failures=1
            )

    def _parse_test_results(self, stage_name: str, result: subprocess.CompletedProcess, duration: float) -> SuiteMetrics:  # type: ignore[attr-defined]
        """Parse test results from pytest output and XML."""
        metrics = SuiteMetrics(
            timestamp=datetime.now(),
            total_tests=0,
            passed_tests=0,
            failed_tests=0,
            skipped_tests=0,
            error_tests=0,
            total_duration=duration,
            average_duration=0,
            median_duration=0,
        )

        # Parse stdout for basic counts
        output = result.stdout + result.stderr

        # Look for pytest summary line
        summary_patterns = [
            r'(\d+) passed',
            r'(\d+) failed',
            r'(\d+) error',
            r'(\d+) skipped',
        ]

        for pattern in summary_patterns:
            match = re.search(pattern, output)
            if match:
                count = int(match.group(1))
                if 'passed' in pattern:
                    metrics.passed_tests = count
                elif 'failed' in pattern:
                    metrics.failed_tests = count
                elif 'error' in pattern:
                    metrics.error_tests = count
                elif 'skipped' in pattern:
                    metrics.skipped_tests = count

        metrics.total_tests = (
            metrics.passed_tests + metrics.failed_tests +
            metrics.error_tests + metrics.skipped_tests
        )

        if metrics.total_tests > 0:
            metrics.pass_rate = metrics.passed_tests / metrics.total_tests
            metrics.average_duration = duration / metrics.total_tests
            metrics.median_duration = metrics.average_duration  # Approximation

        # Try to parse XML for detailed information
        xml_path = self.project_root / "test_results.xml"  # type: ignore[attr-defined]
        if xml_path.exists():
            self._parse_junit_xml(xml_path, metrics)

        return metrics

    def _parse_junit_xml(self, xml_path: Path, metrics: SuiteMetrics) -> None:
        """Parse JUnit XML for detailed test information."""
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()

            categorizer = FailureCategorizer()
            failures = []
            durations = []

            for testcase in root.findall('.//testcase'):
                name = testcase.get('name', '')
                file = testcase.get('file', '')
                duration = float(testcase.get('time', 0))
                durations.append(duration)

                # Check for failures or errors
                failure = testcase.find('failure')
                error = testcase.find('error')

                if failure is not None or error is not None:
                    element = failure if failure is not None else error
                    message = element.get('message', '')
                    text = element.text or ''

                    failure_info = {
                        'message': message,
                        'traceback': text
                    }

                    category = categorizer.categorize_failure(failure_info)

                    test_failure = FailureRecord(
                        test_name=name,
                        test_file=file,
                        failure_type=element.tag,
                        error_message=message,
                        traceback=text,
                        duration=duration,
                        category=category,
                        is_timeout='timeout' in message.lower(),
                        is_import_error=category == 'import_error',
                        is_type_error=category == 'type_annotation',
                        is_mock_related=category == 'mock_related',
                        is_qt_related=category == 'qt_related',
                    )

                    failures.append(test_failure)

            # Update metrics with detailed analysis
            if failures:
                analysis = categorizer.analyze_failure_trends(failures)
                metrics.failures_by_category = analysis['category_distribution']
                metrics.failures_by_file = analysis['file_distribution']
                metrics.quick_wins_available = analysis['quick_wins_estimate']

                # Count specific failure types
                metrics.timeout_failures = sum(1 for f in failures if f.is_timeout)
                metrics.import_failures = sum(1 for f in failures if f.is_import_error)
                metrics.type_failures = sum(1 for f in failures if f.is_type_error)
                metrics.mock_failures = sum(1 for f in failures if f.is_mock_related)
                metrics.qt_failures = sum(1 for f in failures if f.is_qt_related)

            # Calculate duration statistics
            if durations:
                durations.sort()
                metrics.median_duration = durations[len(durations) // 2]
                metrics.slowest_tests = [
                    (tc.get('name', 'unknown'), float(tc.get('time', 0)))
                    for tc in root.findall('.//testcase')
                ]
                metrics.slowest_tests.sort(key=lambda x: x[1], reverse=True)
                metrics.slowest_tests = metrics.slowest_tests[:10]

        except Exception as e:
            print(f"Warning: Could not parse XML results: {e}")

class HealthMonitor:
    """Main class for monitoring test suite health."""

    def __init__(self, test_dir: str | Path):
        self.test_dir = Path(test_dir)
        self.project_root = self.test_dir.parent
        self.history_dir = self.test_dir / "scripts" / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)

        self.runner = HealthTestRunner(self.test_dir)
        self.categorizer = FailureCategorizer()

    def run_health_check(self, mode: str = "full") -> SuiteMetrics:
        """Run comprehensive health check."""
        print(f"Running test health check in '{mode}' mode...")

        if mode == "quick":
            # Run only smoke tests
            stages = self.runner.run_progressive_tests()
            return next(iter(stages.values())) if stages else None

        elif mode == "progressive":
            # Run progressive stages
            stages = self.runner.run_progressive_tests()
            return list(stages.values())[-1] if stages else None

        else:  # full mode
            # Run complete test suite
            return self.runner._run_test_stage("full_suite", ["tests/"])

    def save_metrics(self, metrics: SuiteMetrics) -> Path:
        """Save metrics to historical record."""
        timestamp = metrics.timestamp.strftime("%Y%m%d_%H%M%S")
        filename = f"test_health_{timestamp}.json"
        filepath = self.history_dir / filename

        # Convert to JSON-serializable format
        data = {
            "timestamp": metrics.timestamp.isoformat(),
            "total_tests": metrics.total_tests,
            "passed_tests": metrics.passed_tests,
            "failed_tests": metrics.failed_tests,
            "skipped_tests": metrics.skipped_tests,
            "error_tests": metrics.error_tests,
            "total_duration": metrics.total_duration,
            "average_duration": metrics.average_duration,
            "median_duration": metrics.median_duration,
            "slowest_tests": metrics.slowest_tests,
            "failures_by_category": metrics.failures_by_category,
            "failures_by_file": metrics.failures_by_file,
            "timeout_failures": metrics.timeout_failures,
            "import_failures": metrics.import_failures,
            "type_failures": metrics.type_failures,
            "mock_failures": metrics.mock_failures,
            "qt_failures": metrics.qt_failures,
            "pass_rate": metrics.pass_rate,
            "improvement_trend": metrics.improvement_trend,
            "critical_failures": metrics.critical_failures,
            "quick_wins_available": metrics.quick_wins_available,
        }

        with filepath.open('w') as f:
            json.dump(data, f, indent=2)

        return filepath

    def load_historical_metrics(self, days_back: int = 7) -> list[SuiteMetrics]:
        """Load historical metrics from the last N days."""
        cutoff_date = datetime.now() - timedelta(days=days_back)
        metrics_list = []

        for filepath in self.history_dir.glob("test_health_*.json"):
            try:
                with filepath.open() as f:
                    data = json.load(f)

                timestamp = datetime.fromisoformat(data["timestamp"])
                if timestamp >= cutoff_date:
                    # Reconstruct metrics object
                    metrics = SuiteMetrics(
                        timestamp=timestamp,
                        total_tests=data["total_tests"],
                        passed_tests=data["passed_tests"],
                        failed_tests=data["failed_tests"],
                        skipped_tests=data["skipped_tests"],
                        error_tests=data["error_tests"],
                        total_duration=data["total_duration"],
                        average_duration=data["average_duration"],
                        median_duration=data["median_duration"],
                        slowest_tests=data.get("slowest_tests", []),
                        failures_by_category=data.get("failures_by_category", {}),
                        failures_by_file=data.get("failures_by_file", {}),
                        timeout_failures=data.get("timeout_failures", 0),
                        import_failures=data.get("import_failures", 0),
                        type_failures=data.get("type_failures", 0),
                        mock_failures=data.get("mock_failures", 0),
                        qt_failures=data.get("qt_failures", 0),
                        pass_rate=data.get("pass_rate", 0.0),
                        improvement_trend=data.get("improvement_trend", 0.0),
                        critical_failures=data.get("critical_failures", 0),
                        quick_wins_available=data.get("quick_wins_available", 0),
                    )
                    metrics_list.append(metrics)

            except Exception as e:
                print(f"Warning: Could not load {filepath}: {e}")

        return sorted(metrics_list, key=lambda m: m.timestamp)

    def generate_health_report(self, metrics: SuiteMetrics, historical: list[SuiteMetrics] | None = None) -> str:
        """Generate comprehensive health report."""
        report = []
        report.append("=" * 80)
        report.append("SPRITEPAL TEST SUITE HEALTH DASHBOARD")
        report.append("=" * 80)
        report.append(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        # Overall metrics
        report.append("📊 OVERALL METRICS")
        report.append("-" * 40)
        report.append(f"Total Tests:      {metrics.total_tests:>6}")
        report.append(f"Passed:           {metrics.passed_tests:>6} ({metrics.passed_tests/metrics.total_tests*100:5.1f}%)")
        report.append(f"Failed:           {metrics.failed_tests:>6} ({metrics.failed_tests/metrics.total_tests*100:5.1f}%)")
        report.append(f"Errors:           {metrics.error_tests:>6} ({metrics.error_tests/metrics.total_tests*100:5.1f}%)")
        report.append(f"Skipped:          {metrics.skipped_tests:>6} ({metrics.skipped_tests/metrics.total_tests*100:5.1f}%)")
        report.append("")
        report.append(f"Pass Rate:        {metrics.pass_rate:>6.1%}")
        report.append(f"Total Duration:   {metrics.total_duration:>6.1f}s")
        report.append(f"Average per test: {metrics.average_duration:>6.1f}s")
        report.append(f"Median Duration:  {metrics.median_duration:>6.1f}s")
        report.append("")

        # Health indicators
        if metrics.pass_rate >= 0.95:
            status = "🟢 EXCELLENT"
        elif metrics.pass_rate >= 0.85:
            status = "🟡 GOOD"
        elif metrics.pass_rate >= 0.70:
            status = "🟠 NEEDS IMPROVEMENT"
        else:
            status = "🔴 CRITICAL"

        report.append(f"Health Status: {status}")
        report.append("")

        # Failure analysis
        if metrics.failures_by_category:
            report.append("🔍 FAILURE ANALYSIS")
            report.append("-" * 40)

            total_failures = sum(metrics.failures_by_category.values())
            for category, count in sorted(metrics.failures_by_category.items(), key=lambda x: x[1], reverse=True):
                percentage = count / total_failures * 100
                report.append(f"{category:20} {count:>6} ({percentage:5.1f}%)")

            report.append("")
            report.append(f"Quick Wins Available: {metrics.quick_wins_available}")
            report.append("")

            # Specific failure types
            if metrics.type_failures:
                report.append(f"Type Annotation Issues: {metrics.type_failures}")
            if metrics.timeout_failures:
                report.append(f"Timeout Failures: {metrics.timeout_failures}")
            if metrics.import_failures:
                report.append(f"Import Errors: {metrics.import_failures}")
            if metrics.mock_failures:
                report.append(f"Mock-related Issues: {metrics.mock_failures}")
            if metrics.qt_failures:
                report.append(f"Qt-related Issues: {metrics.qt_failures}")
            report.append("")

        # Most affected files
        if metrics.failures_by_file:
            report.append("📁 MOST AFFECTED FILES")
            report.append("-" * 40)
            for filename, count in list(metrics.failures_by_file.items())[:10]:
                report.append(f"{filename:40} {count:>6} failures")
            report.append("")

        # Slowest tests
        if metrics.slowest_tests:
            report.append("⏱️  SLOWEST TESTS")
            report.append("-" * 40)
            for test_name, duration in metrics.slowest_tests[:10]:
                report.append(f"{test_name:40} {duration:>8.1f}s")
            report.append("")

        # Historical comparison
        if historical and len(historical) > 1:
            report.append("📈 TREND ANALYSIS")
            report.append("-" * 40)

            prev_metrics = historical[-2]
            current_metrics = historical[-1]

            pass_rate_change = current_metrics.pass_rate - prev_metrics.pass_rate
            duration_change = current_metrics.total_duration - prev_metrics.total_duration

            if pass_rate_change > 0:
                trend_indicator = "📈 IMPROVING"
            elif pass_rate_change < 0:
                trend_indicator = "📉 DECLINING"
            else:
                trend_indicator = "➡️  STABLE"

            report.append(f"Pass Rate Change:     {pass_rate_change:+.1%} {trend_indicator}")
            report.append(f"Duration Change:      {duration_change:+.1f}s")
            report.append(f"Tests Added/Removed:  {current_metrics.total_tests - prev_metrics.total_tests:+d}")
            report.append("")

        # Recommendations
        report.append("💡 RECOMMENDATIONS")
        report.append("-" * 40)

        if metrics.type_failures > 10:
            report.append("• High priority: Fix type annotation issues for quick wins")

        if metrics.timeout_failures > 5:
            report.append("• Optimize slow tests or increase timeout limits")

        if metrics.import_failures > 0:
            report.append("• Critical: Fix import errors (may indicate broken dependencies)")

        if metrics.mock_failures > metrics.total_tests * 0.1:
            report.append("• Consider reducing mock complexity or migrating to real components")

        if metrics.average_duration > 2.0:
            report.append("• Performance: Test suite is running slow, consider optimization")

        if metrics.pass_rate < 0.80:
            report.append("• Focus on most affected files for maximum impact")

        return "\n".join(report)

    def generate_prioritized_fix_list(self, metrics: SuiteMetrics) -> dict[str, list[str]]:
        """Generate prioritized list of fixes based on failure analysis."""
        fixes = {
            "critical": [],
            "high_impact": [],
            "quick_wins": [],
            "optimization": [],
        }

        # Critical fixes (test suite functionality)
        if metrics.import_failures > 0:
            fixes["critical"].append(f"Fix {metrics.import_failures} import errors preventing test execution")

        if metrics.pass_rate < 0.5:
            fixes["critical"].append("Test suite below 50% pass rate - requires immediate attention")

        # High impact fixes (many tests affected)
        if metrics.type_failures > 20:
            fixes["high_impact"].append(f"Fix {metrics.type_failures} type annotation issues across test suite")

        if metrics.timeout_failures > 10:
            fixes["high_impact"].append(f"Address {metrics.timeout_failures} timeout failures")

        # Quick wins (easy fixes with good impact)
        if metrics.type_failures > 0:
            fixes["quick_wins"].append(f"Add missing type annotations ({metrics.type_failures} tests)")

        if "mock_related" in metrics.failures_by_category and metrics.failures_by_category["mock_related"] > 5:
            mock_count = metrics.failures_by_category["mock_related"]
            fixes["quick_wins"].append(f"Simplify mock usage in {mock_count} tests")

        # Most affected files
        if metrics.failures_by_file:
            top_files = list(metrics.failures_by_file.items())[:3]
            for filename, count in top_files:
                if count > 5:
                    fixes["high_impact"].append(f"Focus on {filename} ({count} failures)")

        # Performance optimizations
        if metrics.average_duration > 3.0:
            fixes["optimization"].append("Optimize slow tests (average >3s per test)")

        if metrics.slowest_tests:
            slowest = metrics.slowest_tests[0]
            if slowest[1] > 30:
                fixes["optimization"].append(f"Optimize slowest test: {slowest[0]} ({slowest[1]:.1f}s)")

        return fixes

def main():
    """Main entry point for test health dashboard."""
    parser = argparse.ArgumentParser(description="SpritePal Test Health Dashboard")
    parser.add_argument("--run-tests", action="store_true", help="Run test suite")
    parser.add_argument("--analyze", action="store_true", help="Analyze existing results")
    parser.add_argument("--report", action="store_true", help="Generate health report")
    parser.add_argument("--quick-check", action="store_true", help="Run quick smoke tests only")
    parser.add_argument("--historical", action="store_true", help="Include historical analysis")
    parser.add_argument("--compare", help="Compare with historical data (e.g., 'last-week')")
    parser.add_argument("--mode", choices=["quick", "progressive", "full"], default="full",
                       help="Test execution mode")
    parser.add_argument("--save", action="store_true", help="Save results to history")

    args = parser.parse_args()

    # Default to analyzing if no action specified
    if not any([args.run_tests, args.analyze, args.report, args.quick_check]):
        args.run_tests = True
        args.report = True
        args.save = True

    # Initialize monitor
    script_dir = Path(__file__).parent
    test_dir = script_dir.parent
    monitor = HealthMonitor(test_dir)

    metrics = None

    # Run tests if requested
    if args.run_tests or args.quick_check:
        mode = "quick" if args.quick_check else args.mode
        metrics = monitor.run_health_check(mode)

        if metrics and args.save:
            saved_path = monitor.save_metrics(metrics)
            print(f"Results saved to: {saved_path}")

    # Generate report if requested
    if args.report or args.analyze:
        if not metrics:
            # Load most recent metrics
            historical = monitor.load_historical_metrics(1)
            if historical:
                metrics = historical[-1]
            else:
                print("No test results available. Run with --run-tests first.")
                return

        # Load historical data if requested
        historical_data = None
        if args.historical or args.compare:
            days_back = 7
            if args.compare == "last-week":
                days_back = 7
            elif args.compare == "last-month":
                days_back = 30

            historical_data = monitor.load_historical_metrics(days_back)

        # Generate and display report
        report = monitor.generate_health_report(metrics, historical_data)
        print(report)

        # Generate prioritized fix list
        fixes = monitor.generate_prioritized_fix_list(metrics)

        print("\n" + "=" * 80)
        print("🔧 PRIORITIZED FIX LIST")
        print("=" * 80)

        for priority, fix_list in fixes.items():
            if fix_list:
                print(f"\n{priority.upper().replace('_', ' ')}:")
                print("-" * 30)
                for i, fix in enumerate(fix_list, 1):
                    print(f"{i}. {fix}")

if __name__ == "__main__":
    main()
