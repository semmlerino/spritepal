#!/usr/bin/env python3
"""Mock density checker for enforcing real component testing standards.

SpritePal targets a mock density of 0.032 or lower, meaning tests should
primarily use real components rather than mocks. This module provides tools
to analyze and report on mock usage in test files.

Mock density = mock_operations / total_test_operations

Usage:
    # Check specific directory
    python mock_density_checker.py tests/

    # Check with custom threshold
    python mock_density_checker.py tests/ --threshold 0.05

    # Integrate with pytest (add to conftest.py):
    def pytest_sessionfinish(session, exitstatus):
        if os.environ.get('CHECK_MOCK_DENSITY'):
            from tests.infrastructure.mock_density_checker import check_and_report
            check_and_report(Path('tests'), threshold=0.05)
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple


class MockUsage(NamedTuple):
    """Summary of mock usage in a file."""
    file_path: Path
    mock_operations: int
    real_operations: int
    density: float


@dataclass
class DetailedAnalysis:
    """Detailed mock usage analysis for a file."""
    file_path: Path
    mock_calls: list[str]  # List of mock function calls found
    real_calls: list[str]  # List of real component calls found
    mock_count: int
    real_count: int

    @property
    def density(self) -> float:
        total = self.mock_count + self.real_count
        return self.mock_count / total if total > 0 else 0.0


# Patterns indicating mock usage
MOCK_INDICATORS = frozenset([
    'Mock',
    'MagicMock',
    'patch',
    'create_autospec',
    'PropertyMock',
    'AsyncMock',
    'mock_open',
])

# Patterns indicating real component usage
REAL_INDICATORS = frozenset([
    'RealComponentFactory',
    'ManagerTestContext',
    'create_extraction_manager',
    'create_injection_manager',
    'create_session_manager',
    'ThreadSafeTestImage',
])


def analyze_file(file_path: Path) -> DetailedAnalysis:
    """Analyze mock density for a single file.

    Args:
        file_path: Path to Python test file

    Returns:
        DetailedAnalysis with mock and real component usage
    """
    mock_calls: list[str] = []
    real_calls: list[str] = []

    try:
        content = file_path.read_text(encoding='utf-8')
        tree = ast.parse(content)
    except (SyntaxError, OSError) as e:
        print(f"Warning: Could not parse {file_path}: {e}", file=sys.stderr)
        return DetailedAnalysis(
            file_path=file_path,
            mock_calls=[],
            real_calls=[],
            mock_count=0,
            real_count=0
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if not func_name:
                continue

            if func_name in MOCK_INDICATORS:
                mock_calls.append(func_name)
            elif func_name in REAL_INDICATORS or func_name.startswith('create_'):
                real_calls.append(func_name)

        # Check for decorators like @patch
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for decorator in node.decorator_list:
                dec_name = _get_decorator_name(decorator)
                if dec_name and dec_name in MOCK_INDICATORS:
                    mock_calls.append(f"@{dec_name}")

    return DetailedAnalysis(
        file_path=file_path,
        mock_calls=mock_calls,
        real_calls=real_calls,
        mock_count=len(mock_calls),
        real_count=len(real_calls)
    )


def _get_func_name(node: ast.Call) -> str | None:
    """Extract function name from Call node."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    elif isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _get_decorator_name(decorator: ast.expr) -> str | None:
    """Extract decorator name."""
    if isinstance(decorator, ast.Name):
        return decorator.id
    elif isinstance(decorator, ast.Attribute):
        return decorator.attr
    elif isinstance(decorator, ast.Call):
        return _get_func_name(decorator)
    return None


def check_directory(
    test_dir: Path,
    threshold: float = 0.032,
    exclude_patterns: list[str] | None = None
) -> list[MockUsage]:
    """Check all test files in a directory against mock density threshold.

    Args:
        test_dir: Directory containing test files
        threshold: Maximum allowed mock density (default 0.032)
        exclude_patterns: Patterns to exclude from checking

    Returns:
        List of MockUsage for files exceeding threshold
    """
    exclude_patterns = exclude_patterns or [
        'infrastructure/',
        'conftest',
        '__pycache__',
        'fixtures/',
    ]

    violations: list[MockUsage] = []

    for test_file in test_dir.rglob('test_*.py'):
        # Skip excluded paths
        rel_path = str(test_file.relative_to(test_dir))
        if any(pat in rel_path for pat in exclude_patterns):
            continue

        analysis = analyze_file(test_file)
        if analysis.density > threshold:
            violations.append(MockUsage(
                file_path=test_file,
                mock_operations=analysis.mock_count,
                real_operations=analysis.real_count,
                density=analysis.density
            ))

    return sorted(violations, key=lambda x: x.density, reverse=True)


def check_and_report(
    test_dir: Path,
    threshold: float = 0.05,
    verbose: bool = True
) -> bool:
    """Check directory and print report.

    Args:
        test_dir: Directory to check
        threshold: Maximum allowed mock density
        verbose: Whether to print detailed output

    Returns:
        True if all files pass, False if violations found
    """
    violations = check_directory(test_dir, threshold)

    if not violations:
        if verbose:
            print(f"All test files pass mock density threshold ({threshold})")
        return True

    print(f"\n{'='*60}")
    print("Mock Density Violations")
    print(f"{'='*60}")
    print(f"Threshold: {threshold} (target: 0.032)")
    print(f"Files exceeding threshold: {len(violations)}")
    print()

    for usage in violations:
        rel_path = usage.file_path
        print(f"  {rel_path}")
        print(f"    Density: {usage.density:.3f} ({usage.mock_operations} mocks, {usage.real_operations} real)")

    print()
    print("To improve:")
    print("  1. Replace Mock() with RealComponentFactory")
    print("  2. Use ManagerTestContext for lifecycle management")
    print("  3. Only mock at system boundaries (file I/O, network)")
    print(f"{'='*60}\n")

    return False


def get_summary(test_dir: Path) -> dict[str, float | int]:
    """Get summary statistics for entire test directory.

    Returns:
        Dictionary with summary stats
    """
    total_mock = 0
    total_real = 0
    file_count = 0

    for test_file in test_dir.rglob('test_*.py'):
        if 'infrastructure' in str(test_file) or 'conftest' in str(test_file):
            continue

        analysis = analyze_file(test_file)
        total_mock += analysis.mock_count
        total_real += analysis.real_count
        file_count += 1

    total = total_mock + total_real
    overall_density = total_mock / total if total > 0 else 0.0

    return {
        'total_files': file_count,
        'total_mock_operations': total_mock,
        'total_real_operations': total_real,
        'overall_density': overall_density,
    }


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Check mock density in test files'
    )
    parser.add_argument(
        'directory',
        type=Path,
        help='Directory containing test files'
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=0.05,
        help='Maximum allowed mock density (default: 0.05)'
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Print summary statistics only'
    )

    args = parser.parse_args()

    if args.summary:
        stats = get_summary(args.directory)
        print("Mock Density Summary")
        print("-" * 40)
        print(f"Total test files: {stats['total_files']}")
        print(f"Mock operations: {stats['total_mock_operations']}")
        print(f"Real operations: {stats['total_real_operations']}")
        print(f"Overall density: {stats['overall_density']:.4f}")
        print("Target density: 0.032")
        return 0

    success = check_and_report(args.directory, args.threshold)
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
