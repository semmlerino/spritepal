#!/usr/bin/env python3
"""
Fix Verification Orchestrator for SpritePal Test Suite

Coordinates the complete fix verification workflow:
1. Creates baseline before fixes
2. Monitors fix progress with progressive testing
3. Detects regressions and improvements 
4. Generates comprehensive verification reports
5. Provides prioritized fix recommendations

Usage:
    python fix_verification_orchestrator.py --start-verification "type_annotation_fixes"
    python fix_verification_orchestrator.py --check-progress "type_annotation_fixes"
    python fix_verification_orchestrator.py --finalize-verification "type_annotation_fixes"
    python fix_verification_orchestrator.py --full-analysis
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from progressive_test_runner import ProgressiveTestRunner
from regression_detector import RegressionDetector

# Import our monitoring modules
from test_health_dashboard import HealthMonitor, SuiteMetrics


@dataclass
class FixVerificationSession:
    """Tracks a fix verification session."""
    session_id: str
    fix_category: str
    description: str
    started: datetime
    baseline_file: Path | None = None
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    final_report: Path | None = None
    status: str = "active"  # active, completed, abandoned
    expected_improvements: dict[str, int] = field(default_factory=dict)
    actual_improvements: dict[str, int] = field(default_factory=dict)

@dataclass
class FixImpactAnalysis:
    """Analysis of fix impact across different dimensions."""
    category: str
    tests_fixed: int
    tests_broken: int
    net_improvement: int
    pass_rate_change: float
    performance_impact: float
    risk_score: float
    confidence_level: float
    recommended_action: str

class FixVerificationOrchestrator:
    """Orchestrates comprehensive fix verification workflow."""

    # Common fix categories and their expected patterns
    FIX_CATEGORIES = {
        'type_annotation': {
            'description': 'Type annotation and typing fixes',
            'typical_improvements': ['type_failures', 'import_failures'],
            'risk_factors': ['logic_bugs', 'performance'],
            'expected_files': ['*.py'],
        },
        'timeout_fixes': {
            'description': 'Test timeout and performance fixes',
            'typical_improvements': ['timeout_failures', 'performance'],
            'risk_factors': ['threading', 'qt_related'],
            'expected_files': ['test_*.py'],
        },
        'hal_mocking': {
            'description': 'HAL compression mocking improvements',
            'typical_improvements': ['hal_compression', 'mock_related'],
            'risk_factors': ['logic_bugs', 'integration'],
            'expected_files': ['test_*hal*.py', '*compression*'],
        },
        'qt_testing': {
            'description': 'Qt testing infrastructure improvements',
            'typical_improvements': ['qt_related', 'mock_related'],
            'risk_factors': ['gui', 'threading'],
            'expected_files': ['*dialog*.py', '*widget*.py', '*ui*.py'],
        },
        'mock_reduction': {
            'description': 'Migration from mocks to real components',
            'typical_improvements': ['mock_related', 'integration'],
            'risk_factors': ['performance', 'threading'],
            'expected_files': ['test_*integration*.py', 'test_*real*.py'],
        },
    }

    def __init__(self, test_dir: Path):
        self.test_dir = test_dir
        self.project_root = test_dir.parent
        self.scripts_dir = test_dir / "scripts"
        self.sessions_dir = self.scripts_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        # Initialize monitoring components
        self.health_monitor = HealthMonitor(test_dir)
        self.progressive_runner = ProgressiveTestRunner(self.project_root)
        self.regression_detector = RegressionDetector(self.scripts_dir / "history")

        # Active sessions
        self.active_sessions: dict[str, FixVerificationSession] = {}
        self._load_active_sessions()

    def start_verification_session(self,
                                  fix_category: str,
                                  description: str = "",
                                  expected_improvements: dict[str, int] | None = None) -> str:
        """Start a new fix verification session."""

        session_id = f"{fix_category}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        print(f"🚀 Starting Fix Verification Session: {session_id}")
        print(f"Category: {fix_category}")
        print(f"Description: {description}")
        print()

        # Create session
        session = FixVerificationSession(
            session_id=session_id,
            fix_category=fix_category,
            description=description or self.FIX_CATEGORIES.get(fix_category, {}).get('description', ''),
            started=datetime.now(),
            expected_improvements=expected_improvements or {},
        )

        # Create baseline snapshot
        print("📸 Creating baseline snapshot...")
        baseline_metrics = self.health_monitor.run_health_check("full")
        baseline_file = self.health_monitor.save_metrics(baseline_metrics)
        session.baseline_file = baseline_file

        print(f"✅ Baseline created: {baseline_file}")
        print(f"   Total tests: {baseline_metrics.total_tests}")
        print(f"   Pass rate: {baseline_metrics.pass_rate:.1%}")

        # Save session
        self.active_sessions[session_id] = session
        self._save_session(session)

        # Generate initial recommendations
        self._generate_fix_recommendations(session, baseline_metrics)

        return session_id

    def check_progress(self, session_id: str, create_checkpoint: bool = True) -> dict[str, Any]:
        """Check progress of an active verification session."""

        if session_id not in self.active_sessions:
            session = self._load_session(session_id)
            if not session:
                raise ValueError(f"Session not found: {session_id}")
        else:
            session = self.active_sessions[session_id]

        print(f"📊 Checking Progress: {session_id}")
        print(f"Started: {session.started.strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # Run progressive tests to quickly assess current state
        print("🔄 Running progressive test check...")
        progressive_results = self.progressive_runner.run_all_stages(continue_on_failure=True)

        if not progressive_results:
            print("❌ No test results - possible infrastructure issue")
            return {"status": "error", "message": "No test results"}

        # Get current full metrics
        print("📈 Getting complete health metrics...")
        current_metrics = self.health_monitor.run_health_check("full")
        current_file = self.health_monitor.save_metrics(current_metrics)

        # Compare with baseline
        if session.baseline_file:
            print("🔍 Analyzing changes since baseline...")
            regression_report = self.regression_detector.compare_results(
                session.baseline_file, current_file
            )

            print(self.regression_detector.generate_report_text(regression_report))

        # Create checkpoint if requested
        if create_checkpoint:
            checkpoint = {
                'timestamp': datetime.now().isoformat(),
                'metrics_file': str(current_file),
                'progressive_results': [
                    {
                        'stage': result.name,
                        'pass_rate': result.pass_rate,
                        'duration': result.duration,
                        'total_tests': result.total_tests,
                    }
                    for result in progressive_results
                ],
                'overall_pass_rate': current_metrics.pass_rate,
                'total_tests': current_metrics.total_tests,
            }

            session.checkpoints.append(checkpoint)
            self._save_session(session)

            print(f"📌 Checkpoint created ({len(session.checkpoints)} total)")

        # Calculate progress metrics
        progress_data = self._calculate_progress_metrics(session, current_metrics)

        return progress_data

    def finalize_verification(self, session_id: str) -> Path:
        """Finalize verification session with comprehensive report."""

        if session_id not in self.active_sessions:
            session = self._load_session(session_id)
            if not session:
                raise ValueError(f"Session not found: {session_id}")
        else:
            session = self.active_sessions[session_id]

        print(f"🎯 Finalizing Verification Session: {session_id}")
        print()

        # Get final metrics
        print("📊 Capturing final test state...")
        final_metrics = self.health_monitor.run_health_check("full")
        final_file = self.health_monitor.save_metrics(final_metrics)

        # Generate comprehensive report
        report_content = self._generate_final_report(session, final_metrics, final_file)

        # Save report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.scripts_dir / f"verification_report_{session_id}_{timestamp}.md"

        with open(report_file, 'w') as f:
            f.write(report_content)

        # Update session
        session.status = "completed"
        session.final_report = report_file
        self._save_session(session)

        print("✅ Verification completed!")
        print(f"📄 Final report: {report_file}")

        return report_file

    def _generate_final_report(self, session: FixVerificationSession,
                              final_metrics: SuiteMetrics,
                              final_file: Path) -> str:
        """Generate comprehensive final verification report."""

        lines = []
        lines.append("# Fix Verification Report")
        lines.append("")
        lines.append(f"**Session ID:** `{session.session_id}`")
        lines.append(f"**Fix Category:** {session.fix_category}")
        lines.append(f"**Description:** {session.description}")
        lines.append(f"**Started:** {session.started.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Duration:** {datetime.now() - session.started}")
        lines.append(f"**Checkpoints:** {len(session.checkpoints)}")
        lines.append("")

        # Executive summary
        lines.append("## Executive Summary")
        lines.append("")

        if session.baseline_file:
            # Load baseline for comparison
            baseline_data = json.loads(session.baseline_file.read_text())
            baseline_pass_rate = baseline_data.get('pass_rate', 0.0)
            baseline_total = baseline_data.get('total_tests', 0)

            improvement = final_metrics.pass_rate - baseline_pass_rate
            test_change = final_metrics.total_tests - baseline_total

            if improvement > 0.05:
                summary_status = "🟢 **SIGNIFICANT IMPROVEMENT**"
            elif improvement > 0.01:
                summary_status = "🟡 **MINOR IMPROVEMENT**"
            elif improvement > -0.01:
                summary_status = "➡️ **NO SIGNIFICANT CHANGE**"
            elif improvement > -0.05:
                summary_status = "🟠 **MINOR REGRESSION**"
            else:
                summary_status = "🔴 **SIGNIFICANT REGRESSION**"

            lines.append(f"**Result:** {summary_status}")
            lines.append("")
            lines.append(f"- **Pass Rate Change:** {baseline_pass_rate:.1%} → {final_metrics.pass_rate:.1%} ({improvement:+.1%})")
            lines.append(f"- **Test Count Change:** {baseline_total} → {final_metrics.total_tests} ({test_change:+d})")
            lines.append(f"- **Tests Fixed:** {max(0, int(improvement * final_metrics.total_tests))}")

        lines.append("")

        # Detailed metrics comparison
        lines.append("## Detailed Analysis")
        lines.append("")

        if session.baseline_file:
            # Generate regression analysis
            regression_report = self.regression_detector.compare_results(
                session.baseline_file, final_file
            )

            lines.append("### Changes by Category")
            lines.append("")

            if regression_report.category_changes:
                lines.append("| Category | Before | After | Change | Status |")
                lines.append("|----------|--------|-------|--------|---------|")

                for category, changes in regression_report.category_changes.items():
                    before = changes['before']
                    after = changes['after']
                    change = changes['change']

                    if change < 0:
                        status = "✅ Improved"
                    elif change > 0:
                        status = "❌ Regressed"
                    else:
                        status = "➡️ No change"

                    lines.append(f"| {category} | {before} | {after} | {change:+d} | {status} |")

            lines.append("")

        # Performance analysis
        lines.append("### Performance Impact")
        lines.append("")

        if session.checkpoints:
            # Track performance over time
            durations = []
            for checkpoint in session.checkpoints:
                for result in checkpoint.get('progressive_results', []):
                    durations.append(result.get('duration', 0))

            if durations:
                avg_duration = sum(durations) / len(durations)
                lines.append(f"- **Average Test Duration:** {avg_duration:.2f}s")

        lines.append(f"- **Final Total Duration:** {final_metrics.total_duration:.1f}s")
        lines.append(f"- **Average per Test:** {final_metrics.average_duration:.2f}s")
        lines.append("")

        # Progress timeline
        if session.checkpoints:
            lines.append("### Progress Timeline")
            lines.append("")
            lines.append("| Checkpoint | Pass Rate | Tests | Duration | Notes |")
            lines.append("|------------|-----------|-------|----------|-------|")

            for i, checkpoint in enumerate(session.checkpoints, 1):
                timestamp = datetime.fromisoformat(checkpoint['timestamp'])
                pass_rate = checkpoint.get('overall_pass_rate', 0.0)
                total_tests = checkpoint.get('total_tests', 0)

                # Find overall duration from progressive results
                duration = sum(
                    result.get('duration', 0)
                    for result in checkpoint.get('progressive_results', [])
                )

                lines.append(f"| {i} | {pass_rate:.1%} | {total_tests} | {duration:.1f}s | {timestamp.strftime('%H:%M:%S')} |")

            lines.append("")

        # Risk assessment
        lines.append("### Risk Assessment")
        lines.append("")

        risks = []

        if session.baseline_file and final_metrics.pass_rate < baseline_pass_rate:
            risks.append("⚠️ Pass rate decreased - potential regressions introduced")

        if final_metrics.timeout_failures > 5:
            risks.append(f"⚠️ {final_metrics.timeout_failures} timeout failures - may indicate deadlocks")

        if final_metrics.import_failures > 0:
            risks.append(f"🚨 {final_metrics.import_failures} import failures - critical infrastructure issues")

        # Check for significant performance regression
        if session.checkpoints and len(session.checkpoints) > 1:
            first_duration = sum(
                result.get('duration', 0)
                for result in session.checkpoints[0].get('progressive_results', [])
            )
            last_duration = sum(
                result.get('duration', 0)
                for result in session.checkpoints[-1].get('progressive_results', [])
            )

            if last_duration > first_duration * 1.5:
                risks.append("⚠️ Significant performance regression detected")

        if not risks:
            lines.append("✅ No significant risks identified")
        else:
            for risk in risks:
                lines.append(f"- {risk}")

        lines.append("")

        # Recommendations
        lines.append("### Recommendations")
        lines.append("")

        # Generate context-aware recommendations
        recommendations = self._generate_context_recommendations(session, final_metrics)

        for i, rec in enumerate(recommendations, 1):
            lines.append(f"{i}. {rec}")

        lines.append("")

        # Next steps
        lines.append("### Next Steps")
        lines.append("")

        if final_metrics.pass_rate >= 0.95:
            lines.append("🎉 **Excellent progress!** Test suite is in very good health.")
            lines.append("")
            lines.append("**Suggested next actions:**")
            lines.append("- Focus on remaining edge cases and optimization")
            lines.append("- Consider adding more integration tests")
            lines.append("- Set up continuous monitoring to maintain quality")

        elif final_metrics.pass_rate >= 0.85:
            lines.append("✅ **Good progress!** Test suite is in reasonable health.")
            lines.append("")
            lines.append("**Suggested next actions:**")
            lines.append("- Address remaining high-impact failures")
            lines.append("- Focus on most affected test files")
            lines.append("- Consider mock reduction in stable areas")

        elif final_metrics.pass_rate >= 0.70:
            lines.append("🟡 **Moderate progress.** More work needed for production readiness.")
            lines.append("")
            lines.append("**Suggested next actions:**")
            lines.append("- Prioritize critical infrastructure fixes")
            lines.append("- Focus on categories with most failures")
            lines.append("- Consider breaking down complex tests")

        else:
            lines.append("🔴 **Limited progress.** Significant issues remain.")
            lines.append("")
            lines.append("**Suggested next actions:**")
            lines.append("- Review fix strategy - current approach may need adjustment")
            lines.append("- Focus on fundamental infrastructure issues first")
            lines.append("- Consider getting additional expert review")

        lines.append("")

        # Technical details
        lines.append("## Technical Details")
        lines.append("")
        lines.append(f"**Final Metrics File:** `{final_file.name}`")
        lines.append(f"**Session Data:** `{session.session_id}.json`")

        if session.baseline_file:
            lines.append(f"**Baseline File:** `{session.baseline_file.name}`")

        lines.append("")
        lines.append("---")
        lines.append(f"*Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by Fix Verification Orchestrator*")

        return "\n".join(lines)

    def _generate_context_recommendations(self, session: FixVerificationSession,
                                        metrics: SuiteMetrics) -> list[str]:
        """Generate context-aware recommendations based on fix category and results."""

        recommendations = []
        fix_category = session.fix_category

        # Category-specific recommendations
        if fix_category == 'type_annotation':
            if metrics.type_failures > 20:
                recommendations.append("Continue focusing on type annotation fixes - still significant issues remaining")
            if metrics.import_failures > 0:
                recommendations.append("Address import errors immediately - they may be blocking other type fixes")
            if metrics.type_failures < 10:
                recommendations.append("Type annotation fixes showing good progress - consider systematic cleanup")

        elif fix_category == 'timeout_fixes':
            if metrics.timeout_failures > 10:
                recommendations.append("Timeout issues persist - investigate potential deadlocks or infinite loops")
            if metrics.average_duration > 3.0:
                recommendations.append("Tests still running slow - consider breaking up long-running operations")
            if metrics.timeout_failures < 5:
                recommendations.append("Timeout fixes effective - consider similar optimizations for remaining slow tests")

        elif fix_category == 'hal_mocking':
            if metrics.failures_by_category.get('hal_compression', 0) > 5:
                recommendations.append("HAL compression issues remain - review mock implementation strategy")
            if 'BrokenPipeError' in str(metrics.failures_by_category):
                recommendations.append("Broken pipe errors suggest HAL process management needs improvement")

        elif fix_category == 'mock_reduction':
            if metrics.mock_failures > metrics.total_tests * 0.1:
                recommendations.append("High mock failure rate - consider reverting some mock reductions")
            if metrics.pass_rate > 0.9:
                recommendations.append("Mock reduction successful - continue with similar components")

        # General recommendations based on metrics
        if metrics.quick_wins_available > 10:
            recommendations.append(f"Focus on {metrics.quick_wins_available} quick wins for maximum impact")

        if len(metrics.failures_by_file) > 0:
            top_file = max(metrics.failures_by_file.items(), key=lambda x: x[1])
            if top_file[1] > 5:
                recommendations.append(f"Prioritize fixes in {top_file[0]} ({top_file[1]} failures)")

        if not recommendations:
            recommendations.append("Continue current fix strategy - metrics show positive trends")

        return recommendations

    def _calculate_progress_metrics(self, session: FixVerificationSession,
                                  current_metrics: SuiteMetrics) -> dict[str, Any]:
        """Calculate detailed progress metrics for the session."""

        progress = {
            'session_id': session.session_id,
            'elapsed_time': str(datetime.now() - session.started),
            'checkpoints_count': len(session.checkpoints),
            'current_pass_rate': current_metrics.pass_rate,
            'current_total_tests': current_metrics.total_tests,
        }

        if session.baseline_file:
            # Calculate improvements since baseline
            baseline_data = json.loads(session.baseline_file.read_text())
            baseline_pass_rate = baseline_data.get('pass_rate', 0.0)
            baseline_total = baseline_data.get('total_tests', 0)

            progress.update({
                'baseline_pass_rate': baseline_pass_rate,
                'baseline_total_tests': baseline_total,
                'pass_rate_improvement': current_metrics.pass_rate - baseline_pass_rate,
                'tests_count_change': current_metrics.total_tests - baseline_total,
                'estimated_tests_fixed': max(0, int((current_metrics.pass_rate - baseline_pass_rate) * current_metrics.total_tests)),
            })

        # Track progress over checkpoints
        if session.checkpoints:
            checkpoint_rates = [cp.get('overall_pass_rate', 0.0) for cp in session.checkpoints]
            if len(checkpoint_rates) > 1:
                recent_trend = checkpoint_rates[-1] - checkpoint_rates[-2]
                progress['recent_trend'] = recent_trend
                progress['trending'] = 'improving' if recent_trend > 0.01 else 'declining' if recent_trend < -0.01 else 'stable'

        return progress

    def _generate_fix_recommendations(self, session: FixVerificationSession,
                                    baseline_metrics: SuiteMetrics) -> None:
        """Generate initial fix recommendations based on baseline metrics."""

        print("💡 Initial Fix Recommendations")
        print("-" * 40)

        fix_category = session.fix_category
        category_info = self.FIX_CATEGORIES.get(fix_category, {})

        # Category-specific recommendations
        typical_improvements = category_info.get('typical_improvements', [])
        risk_factors = category_info.get('risk_factors', [])

        print(f"Fix Category: {fix_category}")
        if typical_improvements:
            print(f"Expected Improvements: {', '.join(typical_improvements)}")
        if risk_factors:
            print(f"Risk Factors to Monitor: {', '.join(risk_factors)}")

        print()
        print("Based on baseline metrics:")

        # Generate specific recommendations
        recommendations = []

        if baseline_metrics.type_failures > 20 and fix_category == 'type_annotation':
            recommendations.append(f"High priority: {baseline_metrics.type_failures} type annotation issues")

        if baseline_metrics.timeout_failures > 10 and fix_category == 'timeout_fixes':
            recommendations.append(f"Focus on {baseline_metrics.timeout_failures} timeout failures")

        if baseline_metrics.import_failures > 0:
            recommendations.append(f"Critical: Fix {baseline_metrics.import_failures} import errors first")

        # Most affected files
        if baseline_metrics.failures_by_file:
            top_files = sorted(baseline_metrics.failures_by_file.items(), key=lambda x: x[1], reverse=True)[:3]
            for filename, count in top_files:
                if count > 5:
                    recommendations.append(f"Target {filename} ({count} failures)")

        if not recommendations:
            recommendations.append("Baseline looks good - focus on incremental improvements")

        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. {rec}")

        print()

    def _save_session(self, session: FixVerificationSession) -> None:
        """Save session data to disk."""
        session_file = self.sessions_dir / f"{session.session_id}.json"

        session_data = {
            'session_id': session.session_id,
            'fix_category': session.fix_category,
            'description': session.description,
            'started': session.started.isoformat(),
            'baseline_file': str(session.baseline_file) if session.baseline_file else None,
            'checkpoints': session.checkpoints,
            'final_report': str(session.final_report) if session.final_report else None,
            'status': session.status,
            'expected_improvements': session.expected_improvements,
            'actual_improvements': session.actual_improvements,
        }

        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=2)

    def _load_session(self, session_id: str) -> FixVerificationSession | None:
        """Load session data from disk."""
        session_file = self.sessions_dir / f"{session_id}.json"

        if not session_file.exists():
            return None

        with open(session_file) as f:
            data = json.load(f)

        session = FixVerificationSession(
            session_id=data['session_id'],
            fix_category=data['fix_category'],
            description=data['description'],
            started=datetime.fromisoformat(data['started']),
            baseline_file=Path(data['baseline_file']) if data['baseline_file'] else None,
            checkpoints=data['checkpoints'],
            final_report=Path(data['final_report']) if data['final_report'] else None,
            status=data['status'],
            expected_improvements=data.get('expected_improvements', {}),
            actual_improvements=data.get('actual_improvements', {}),
        )

        return session

    def _load_active_sessions(self) -> None:
        """Load all active sessions from disk."""
        for session_file in self.sessions_dir.glob("*.json"):
            try:
                with open(session_file) as f:
                    data = json.load(f)

                if data.get('status', 'active') == 'active':
                    session = self._load_session(data['session_id'])
                    if session:
                        self.active_sessions[session.session_id] = session
            except Exception as e:
                print(f"Warning: Could not load session {session_file}: {e}")

    def list_sessions(self, show_completed: bool = False) -> None:
        """List all verification sessions."""

        all_sessions = []

        # Load all sessions from disk
        for session_file in self.sessions_dir.glob("*.json"):
            try:
                session = self._load_session(session_file.stem)
                if session:
                    all_sessions.append(session)
            except Exception as e:
                print(f"Warning: Could not load {session_file}: {e}")

        if not all_sessions:
            print("No verification sessions found.")
            return

        # Filter by status
        if not show_completed:
            all_sessions = [s for s in all_sessions if s.status == 'active']

        print(f"📋 Verification Sessions ({'All' if show_completed else 'Active only'})")
        print("=" * 60)

        for session in sorted(all_sessions, key=lambda s: s.started, reverse=True):
            status_icon = "✅" if session.status == 'completed' else "🔄" if session.status == 'active' else "❌"
            duration = datetime.now() - session.started

            print(f"{status_icon} {session.session_id}")
            print(f"   Category: {session.fix_category}")
            print(f"   Started: {session.started.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   Duration: {duration}")
            print(f"   Checkpoints: {len(session.checkpoints)}")
            print(f"   Status: {session.status}")
            if session.description:
                print(f"   Description: {session.description}")
            print()

    def run_full_analysis(self) -> None:
        """Run complete analysis with all monitoring tools."""

        print("🔬 Running Full Test Suite Analysis")
        print("=" * 60)

        # 1. Health Dashboard
        print("\n📊 1. Health Dashboard Analysis")
        print("-" * 40)
        metrics = self.health_monitor.run_health_check("full")
        report = self.health_monitor.generate_health_report(metrics)
        print(report)

        # 2. Progressive Testing
        print("\n🚀 2. Progressive Test Analysis")
        print("-" * 40)
        self.progressive_runner.run_all_stages(continue_on_failure=True)

        # 3. Recent Comparisons
        print("\n📈 3. Recent Trend Analysis")
        print("-" * 40)
        recent_pairs = self.regression_detector.find_recent_comparisons(7)

        if recent_pairs:
            print(f"Found {len(recent_pairs)} recent comparisons")
            # Show most recent comparison
            before_file, after_file = recent_pairs[-1]
            regression_report = self.regression_detector.compare_results(before_file, after_file)
            print(self.regression_detector.generate_report_text(regression_report))
        else:
            print("No recent comparisons available")

        # 4. Fix Recommendations
        print("\n💡 4. Prioritized Fix Recommendations")
        print("-" * 40)
        fixes = self.health_monitor.generate_prioritized_fix_list(metrics)

        for priority, fix_list in fixes.items():
            if fix_list:
                print(f"\n{priority.upper().replace('_', ' ')}:")
                for i, fix in enumerate(fix_list, 1):
                    print(f"  {i}. {fix}")

def main():
    """Main entry point for fix verification orchestrator."""
    parser = argparse.ArgumentParser(description="Fix Verification Orchestrator")

    # Session management
    parser.add_argument("--start-verification", metavar="CATEGORY",
                       help="Start new verification session")
    parser.add_argument("--description", default="",
                       help="Description for verification session")
    parser.add_argument("--check-progress", metavar="SESSION_ID",
                       help="Check progress of active session")
    parser.add_argument("--finalize-verification", metavar="SESSION_ID",
                       help="Finalize verification session")

    # Session listing
    parser.add_argument("--list-sessions", action="store_true",
                       help="List all verification sessions")
    parser.add_argument("--show-completed", action="store_true",
                       help="Include completed sessions in listing")

    # Analysis
    parser.add_argument("--full-analysis", action="store_true",
                       help="Run complete test suite analysis")

    # Options
    parser.add_argument("--no-checkpoint", action="store_true",
                       help="Don't create checkpoint when checking progress")

    args = parser.parse_args()

    # Initialize orchestrator
    script_dir = Path(__file__).parent
    test_dir = script_dir.parent
    orchestrator = FixVerificationOrchestrator(test_dir)

    # Handle commands
    if args.start_verification:
        session_id = orchestrator.start_verification_session(
            args.start_verification,
            args.description
        )
        print(f"\n🎯 Session started: {session_id}")
        print(f"Use --check-progress {session_id} to monitor progress")

    elif args.check_progress:
        try:
            progress = orchestrator.check_progress(
                args.check_progress,
                create_checkpoint=not args.no_checkpoint
            )
            print("\n📊 Progress Summary:")
            for key, value in progress.items():
                print(f"  {key}: {value}")
        except ValueError as e:
            print(f"Error: {e}")

    elif args.finalize_verification:
        try:
            report_file = orchestrator.finalize_verification(args.finalize_verification)
            print("\n✅ Verification completed!")
            print(f"📄 Report available at: {report_file}")
        except ValueError as e:
            print(f"Error: {e}")

    elif args.list_sessions:
        orchestrator.list_sessions(args.show_completed)

    elif args.full_analysis:
        orchestrator.run_full_analysis()

    else:
        # Default: show help and available categories
        parser.print_help()
        print("\nAvailable Fix Categories:")
        print("-" * 30)
        for category, info in orchestrator.FIX_CATEGORIES.items():
            print(f"  {category:20} - {info['description']}")

if __name__ == "__main__":
    main()
