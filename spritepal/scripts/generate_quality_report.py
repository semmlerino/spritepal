#!/usr/bin/env python3
from __future__ import annotations

"""
Quality Report Generator

Combines results from various quality checks into comprehensive reports.
Designed for CI/CD integration and trend analysis.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


class QualityReportGenerator:
    """Generates comprehensive quality reports from multiple check results."""

    def __init__(self):
        self.type_check_data: dict[str, Any] = {}
        self.mock_density_data: dict[str, Any] = {}
        self.lint_data: dict[str, Any] = {}
        self.test_data: dict[str, Any] = {}

    def load_json_report(self, file_path: str) -> dict[str, Any]:
        """Load a JSON report file safely."""
        try:
            if Path(file_path).exists():
                with Path(file_path).open() as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"Warning: Could not load {file_path}: {e}", file=sys.stderr)
            return {}

    def calculate_quality_metrics(self) -> dict[str, Any]:
        """Calculate comprehensive quality metrics."""
        metrics = {
            "overall_score": 0,
            "type_safety_score": 0,
            "test_quality_score": 0,
            "code_quality_score": 0,
            "maintainability_score": 0,
            "grade": "F",
            "trend": "unknown",
            "areas_for_improvement": [],
            "strengths": [],
        }

        # Type Safety Score (40% weight)
        type_score = self._calculate_type_safety_score()
        metrics["type_safety_score"] = type_score

        # Test Quality Score (30% weight)
        test_score = self._calculate_test_quality_score()
        metrics["test_quality_score"] = test_score

        # Code Quality Score (20% weight)
        code_score = self._calculate_code_quality_score()
        metrics["code_quality_score"] = code_score

        # Maintainability Score (10% weight)
        maintainability_score = self._calculate_maintainability_score()
        metrics["maintainability_score"] = maintainability_score

        # Overall weighted score
        overall = type_score * 0.4 + test_score * 0.3 + code_score * 0.2 + maintainability_score * 0.1
        metrics["overall_score"] = round(overall, 1)

        # Assign grade
        if overall >= 95:
            metrics["grade"] = "A+"
        elif overall >= 90:
            metrics["grade"] = "A"
        elif overall >= 85:
            metrics["grade"] = "A-"
        elif overall >= 80:
            metrics["grade"] = "B+"
        elif overall >= 75:
            metrics["grade"] = "B"
        elif overall >= 70:
            metrics["grade"] = "B-"
        elif overall >= 65:
            metrics["grade"] = "C+"
        elif overall >= 60:
            metrics["grade"] = "C"
        else:
            metrics["grade"] = "D" if overall >= 50 else "F"

        # Identify areas for improvement and strengths
        self._analyze_improvement_areas(metrics)

        return metrics

    def _calculate_type_safety_score(self) -> float:
        """Calculate type safety score based on type checking results."""
        if not self.type_check_data:
            return 50.0  # Default if no data

        total_errors = self.type_check_data.get("summary", {}).get("total_errors", 0)
        critical_errors = self.type_check_data.get("critical_errors", 0)

        # Start with perfect score
        score = 100.0

        # Heavy penalty for critical errors
        score -= critical_errors * 3.0

        # Moderate penalty for other errors
        other_errors = total_errors - critical_errors
        score -= other_errors * 1.0

        # Bonus for low error counts
        if total_errors == 0:
            score += 5.0  # Bonus for perfect type safety
        elif total_errors <= 10:
            score += 2.0  # Small bonus for excellent type safety

        return max(0.0, min(100.0, score))

    def _calculate_test_quality_score(self) -> float:
        """Calculate test quality score based on mock density and test patterns."""
        if not self.mock_density_data:
            return 75.0  # Default if no data

        violations = self.mock_density_data.get("violations", [])
        avg_density = self.mock_density_data.get("summary", {}).get("avg_density", 0)
        self.mock_density_data.get("total_files", 1)

        # Start with good score
        score = 85.0

        # Penalty for mock density violations
        score -= len(violations) * 3.0

        # Penalty for high average density
        score -= avg_density * 200  # Convert to percentage impact

        # Bonus for good test coverage patterns
        deprecated_count = sum(len(v.get("deprecated_patterns", [])) for v in violations)
        if deprecated_count == 0:
            score += 10.0  # Bonus for no deprecated patterns
        else:
            score -= deprecated_count * 1.0

        return max(0.0, min(100.0, score))

    def _calculate_code_quality_score(self) -> float:
        """Calculate code quality score based on linting results."""
        # This would be enhanced with actual lint data
        # For now, return a baseline score
        return 80.0

    def _calculate_maintainability_score(self) -> float:
        """Calculate maintainability score based on various factors."""
        score = 80.0  # Baseline

        # Factor in error distribution across files
        if self.type_check_data:
            files_with_errors = self.type_check_data.get("summary", {}).get("files_with_errors", 0)
            total_errors = self.type_check_data.get("summary", {}).get("total_errors", 0)

            if total_errors > 0 and files_with_errors > 0:
                errors_per_file = total_errors / files_with_errors
                if errors_per_file > 5:
                    score -= 10  # Many errors concentrated in few files is bad
                elif errors_per_file < 2:
                    score += 5  # Errors spread across many files is better

        return max(0.0, min(100.0, score))

    def _analyze_improvement_areas(self, metrics: dict[str, Any]) -> None:
        """Analyze and identify specific areas for improvement."""
        improvements = []
        strengths = []

        # Type safety analysis
        if metrics["type_safety_score"] < 80:
            if self.type_check_data.get("critical_errors", 0) > 10:
                improvements.append("Critical type errors need immediate attention")
            if self.type_check_data.get("summary", {}).get("total_errors", 0) > 50:
                improvements.append("High number of type errors - focus on type annotations")
        else:
            strengths.append("Excellent type safety")

        # Test quality analysis
        if metrics["test_quality_score"] < 80:
            violations = len(self.mock_density_data.get("violations", []))
            if violations > 5:
                improvements.append("High mock density - consider migrating to RealComponentFactory")

            deprecated_patterns = sum(
                len(v.get("deprecated_patterns", [])) for v in self.mock_density_data.get("violations", [])
            )
            if deprecated_patterns > 0:
                improvements.append("Deprecated MockFactory patterns found")
        else:
            strengths.append("Good test architecture")

        # Overall analysis
        if metrics["overall_score"] >= 90:
            strengths.append("Outstanding overall code quality")
        elif metrics["overall_score"] >= 80:
            strengths.append("Good overall code quality")

        metrics["areas_for_improvement"] = improvements
        metrics["strengths"] = strengths

    def generate_json_report(self, include_raw_data: bool = False) -> dict[str, Any]:
        """Generate a comprehensive JSON report."""
        metrics = self.calculate_quality_metrics()

        report = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "generator_version": "1.0.0",
                "report_type": "comprehensive_quality",
            },
            "quality_metrics": metrics,
            "summary": {
                "overall_grade": metrics["grade"],
                "overall_score": metrics["overall_score"],
                "passing_threshold": metrics["overall_score"] >= 70,
                "recommendations_count": len(metrics["areas_for_improvement"]),
            },
        }

        # Add summaries of each check type
        if self.type_check_data:
            report["type_checking"] = {
                "summary": self.type_check_data.get("summary", {}),
                "critical_errors": self.type_check_data.get("critical_errors", 0),
                "thresholds_passed": self.type_check_data.get("thresholds", {}).get("overall_passed", False),
            }

        if self.mock_density_data:
            report["test_quality"] = {
                "total_files": self.mock_density_data.get("total_files", 0),
                "violations": len(self.mock_density_data.get("violations", [])),
                "avg_density": self.mock_density_data.get("summary", {}).get("avg_density", 0),
            }

        # Include raw data if requested (for debugging)
        if include_raw_data:
            report["raw_data"] = {
                "type_check": self.type_check_data,
                "mock_density": self.mock_density_data,
                "lint": self.lint_data,
                "test": self.test_data,
            }

        return report

    def generate_markdown_report(self) -> str:
        """Generate a comprehensive markdown report."""
        metrics = self.calculate_quality_metrics()
        report = []

        # Header
        report.append("# Quality Gate Report")
        report.append(f"*Generated on {datetime.now().strftime('%Y-%m-%d at %H:%M UTC')}*")
        report.append("")

        # Quality Score Summary
        grade_emoji = {
            "A+": "🌟",
            "A": "🟢",
            "A-": "🟢",
            "B+": "🟡",
            "B": "🟡",
            "B-": "🟡",
            "C+": "🟠",
            "C": "🟠",
            "D": "🔴",
            "F": "🔴",
        }

        emoji = grade_emoji.get(metrics["grade"], "⚪")
        report.append(f"## {emoji} Quality Score")
        report.append(f"**Overall Grade: {metrics['grade']} ({metrics['overall_score']}/100)**")
        report.append("")

        # Score breakdown
        report.append("### 📊 Score Breakdown")
        report.append(f"- 🛡️ **Type Safety**: {metrics['type_safety_score']:.1f}/100 (40% weight)")
        report.append(f"- 🧪 **Test Quality**: {metrics['test_quality_score']:.1f}/100 (30% weight)")
        report.append(f"- 📝 **Code Quality**: {metrics['code_quality_score']:.1f}/100 (20% weight)")
        report.append(f"- 🔧 **Maintainability**: {metrics['maintainability_score']:.1f}/100 (10% weight)")
        report.append("")

        # Type Checking Results
        if self.type_check_data:
            report.append("## 🔍 Type Checking Results")
            summary = self.type_check_data.get("summary", {})
            total_errors = summary.get("total_errors", 0)
            critical_errors = self.type_check_data.get("critical_errors", 0)

            if total_errors == 0:
                report.append("✅ **Perfect type safety!** No errors found.")
            else:
                status_icon = "🔴" if critical_errors > 10 else "🟡" if critical_errors > 0 else "🟢"
                report.append(f"{status_icon} **{total_errors} type errors found**")

                if critical_errors > 0:
                    report.append(f"  - 🚨 **{critical_errors} critical errors** (need immediate attention)")

                other_errors = total_errors - critical_errors
                if other_errors > 0:
                    report.append(f"  - ℹ️ {other_errors} other errors")

            # Show top error types
            top_errors = self.type_check_data.get("top_error_types", [])
            if top_errors:
                report.append("")
                report.append("**Most Common Error Types:**")
                for error_type, count in top_errors[:5]:
                    report.append(f"- `{error_type}`: {count} occurrences")

            report.append("")

        # Mock Density Results
        if self.mock_density_data:
            report.append("## 🧪 Test Quality Analysis")
            violations = self.mock_density_data.get("violations", [])
            summary = self.mock_density_data.get("summary", {})
            avg_density = summary.get("avg_density", 0)
            total_files = self.mock_density_data.get("total_files", 0)

            if not violations:
                report.append("✅ **Excellent test quality!** Mock density within acceptable limits.")
            else:
                report.append(f"⚠️ **{len(violations)} files exceed mock density thresholds**")

            report.append(f"- **Average mock density**: {avg_density:.4f}")
            report.append(f"- **Test files analyzed**: {total_files}")

            if violations:
                report.append("")
                report.append("**Files needing attention:**")
                for v in violations[:5]:  # Show top 5
                    icon = "🔴" if v.get("type") == "new_file" else "🟡"
                    file_name = Path(v["file"]).name  # Just filename for readability
                    report.append(
                        f"- {icon} `{file_name}`: {v['density']:.4f} (threshold: {v.get('threshold', 'N/A')})"
                    )

            report.append("")

        # Strengths and Improvements
        if metrics["strengths"]:
            report.append("## ✨ Strengths")
            for strength in metrics["strengths"]:
                report.append(f"- {strength}")
            report.append("")

        if metrics["areas_for_improvement"]:
            report.append("## 🎯 Areas for Improvement")
            priority_items = [
                item
                for item in metrics["areas_for_improvement"]
                if "critical" in item.lower() or "immediate" in item.lower()
            ]
            other_items = [item for item in metrics["areas_for_improvement"] if item not in priority_items]

            if priority_items:
                report.append("### 🚨 High Priority")
                for item in priority_items:
                    report.append(f"1. **{item}**")
                report.append("")

            if other_items:
                report.append("### 📈 General Improvements")
                for i, item in enumerate(other_items, 1):
                    report.append(f"{i}. {item}")
                report.append("")
        else:
            report.append("## 🎉 Excellent Work!")
            report.append("No specific areas for improvement identified. Keep up the great work!")
            report.append("")

        # Migration Guidance (specific to this project)
        if any("MockFactory" in str(v) for v in self.mock_density_data.get("violations", [])):
            report.append("## 🔄 Migration Guidance")
            report.append("Consider migrating from `MockFactory` to `RealComponentFactory` for:")
            report.append("- Better type safety without unsafe `cast()` operations")
            report.append("- Real managers with test data injection")
            report.append("- Improved integration testing capabilities")
            report.append("- Elimination of mock-related bugs")
            report.append("")
            report.append("See `tests/infrastructure/migration_helpers.py` for automated migration tools.")
            report.append("")

        # Footer
        report.append("---")
        report.append("*This report was generated automatically by the SpritePal Quality Gate system.*")
        report.append(f"*Quality threshold for passing: 70/100 (Current: {metrics['overall_score']}/100)*")

        return "\n".join(report)

    def load_all_data(
        self,
        type_check_file: str | None = None,
        mock_density_file: str | None = None,
        lint_file: str | None = None,
        test_file: str | None = None,
    ) -> None:
        """Load all available quality check data."""
        if type_check_file:
            self.type_check_data = self.load_json_report(type_check_file)

        if mock_density_file:
            self.mock_density_data = self.load_json_report(mock_density_file)

        if lint_file:
            self.lint_data = self.load_json_report(lint_file)

        if test_file:
            self.test_data = self.load_json_report(test_file)


def main():
    parser = argparse.ArgumentParser(description="Generate comprehensive quality report from multiple check results")
    parser.add_argument("--type-check", help="Type check results JSON file")
    parser.add_argument("--mock-density", help="Mock density results JSON file")
    parser.add_argument("--lint", help="Lint results JSON file")
    parser.add_argument("--test", help="Test results JSON file")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--format", choices=["json", "markdown"], default="json", help="Output format (default: json)")
    parser.add_argument(
        "--include-raw-data", action="store_true", help="Include raw data in JSON output (for debugging)"
    )
    parser.add_argument(
        "--threshold", type=float, default=70.0, help="Quality score threshold for passing (default: 70)"
    )

    args = parser.parse_args()

    # Create generator and load data
    generator = QualityReportGenerator()
    generator.load_all_data(
        type_check_file=args.type_check, mock_density_file=args.mock_density, lint_file=args.lint, test_file=args.test
    )

    # Generate report in requested format
    if args.format == "markdown":
        report_content = generator.generate_markdown_report()
    else:
        report_data = generator.generate_json_report(include_raw_data=args.include_raw_data)
        report_content = json.dumps(report_data, indent=2)

    # Save or print report
    if args.output:
        with Path(args.output).open("w") as f:
            f.write(report_content)
        print(f"Quality report saved to {args.output}")
    else:
        print(report_content)

    # Exit with appropriate code based on quality score
    if args.format == "json":
        quality_score = generator.calculate_quality_metrics()["overall_score"]
        return 0 if quality_score >= args.threshold else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
