#!/usr/bin/env python3
from __future__ import annotations

"""
Comprehensive Integration Test Runner for SpritePal.

This script runs the integration tests that would catch the specific bugs that were fixed:
- Infinite loop prevention in BatchThumbnailWorker
- Memory leaks with large sprite sets
- Thread leaks from improper worker cleanup
- Worker lifecycle management issues
- Fullscreen viewer edge cases

Usage:
    python3 run_comprehensive_integration_tests.py [options]

Options:
    --gui           Run GUI tests (requires display)
    --headless      Run headless tests only
    --performance   Include performance tests
    --memory        Include memory leak tests
    --coverage      Run with coverage reporting
    --parallel      Run tests in parallel
    --verbose       Verbose output
    --markers       Show available test markers
    --dry-run       Show which tests would run without executing
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def setup_environment():
    """Setup the test environment."""
    # Add the project directory to Python path
    project_root = Path(__file__).parent
    sys.path.insert(0, str(project_root))

    # Set environment variables for testing
    os.environ["PYTEST_CURRENT_TEST"] = "integration"

    # Ensure virtual environment is used
    if hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix):
        print("✓ Running in virtual environment")
    else:
        print("⚠ Warning: Not running in virtual environment")
        print("  Consider activating venv with: source venv/bin/activate")


def get_pytest_command(args):
    """Build the pytest command based on arguments."""
    cmd = [sys.executable, "-m", "pytest"]

    # Test selection based on markers and arguments
    test_markers = []

    if args.gui and not args.headless:
        test_markers.append("gui")
    elif args.headless and not args.gui:
        test_markers.append("headless")
    # If neither specified, run both

    if args.performance:
        test_markers.append("performance")

    if args.memory:
        test_markers.append("not slow")  # Memory tests tend to be slow, so include fast ones

    # Build marker expression
    if test_markers:
        marker_expr = " or ".join(test_markers)
        cmd.extend(["-m", marker_expr])

    # Test paths
    integration_test_paths = [
        "tests/integration/test_fullscreen_sprite_viewer_integration.py",
        "tests/integration/test_gallery_window_integration.py",
        "tests/integration/test_batch_thumbnail_worker_integration.py",
        "tests/integration/test_worker_lifecycle_management_integration.py",
        "tests/integration/test_memory_management_integration.py",
        "tests/integration/test_complete_ui_workflows_comprehensive.py",
    ]

    # Filter paths that exist
    existing_paths = [path for path in integration_test_paths if Path(path).exists()]
    cmd.extend(existing_paths)

    # Coverage reporting
    if args.coverage:
        cmd.extend(
            [
                "--cov=ui.widgets.fullscreen_sprite_viewer",
                "--cov=ui.windows.detached_gallery_window",
                "--cov=ui.workers.batch_thumbnail_worker",
                "--cov=ui.common.worker_manager",
                "--cov-report=html:htmlcov/integration",
                "--cov-report=term-missing",
            ]
        )

    # Parallel execution
    if args.parallel:
        # Use pytest-xdist for parallel execution
        cmd.extend(["-n", "auto"])

    # Output options
    if args.verbose:
        cmd.extend(["-v", "-s"])
    else:
        cmd.append("-v")

    # Timeout for hanging tests
    cmd.extend(["--timeout=300"])  # 5 minute timeout per test

    # Show local variables on failures
    cmd.append("--tb=short")

    # Disable warnings for cleaner output
    cmd.append("--disable-warnings")

    return cmd


def show_available_markers():
    """Show available test markers."""
    print("\nAvailable test markers for integration tests:")
    print("=" * 50)

    markers = [
        ("gui", "Tests requiring GUI environment (display/X11)"),
        ("headless", "Tests that can run without display"),
        ("integration", "Integration tests"),
        ("performance", "Performance and benchmark tests"),
        ("memory", "Memory management and leak tests"),
        ("slow", "Slow tests (>5 seconds)"),
        ("worker_threads", "Tests involving worker threads"),
        ("thread_safety", "Thread safety tests"),
        ("qt_real", "Tests using real Qt components"),
        ("mock_only", "Tests using only mocked components"),
    ]

    for marker, description in markers:
        print(f"  {marker:<15} - {description}")

    print("\nExample usage:")
    print("  python3 run_comprehensive_integration_tests.py --gui --performance")
    print("  python3 run_comprehensive_integration_tests.py --headless --memory")
    print("  python3 run_comprehensive_integration_tests.py --coverage --verbose")


def check_dependencies():
    """Check that required dependencies are installed."""
    required_packages = [
        "pytest",
        "pytest-qt",
        "pytest-cov",
        "pytest-xdist",
        "pytest-timeout",
        "PySide6",
        "Pillow",
    ]

    missing_packages = []

    for package in required_packages:
        try:
            __import__(package.replace("-", "_").lower())
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print("❌ Missing required packages:")
        for package in missing_packages:
            print(f"  - {package}")
        print("\nInstall with:")
        print(f"  python3 -m pip install {' '.join(missing_packages)}")
        return False

    print("✓ All required packages are installed")
    return True


def dry_run_info(cmd):
    """Show what would be executed in dry run mode."""
    print("\nDry run - would execute:")
    print("=" * 50)
    print(" ".join(cmd))

    print("\nTest files that would be included:")
    test_files = [arg for arg in cmd if arg.endswith(".py")]
    for test_file in test_files:
        if Path(test_file).exists():
            print(f"  ✓ {test_file}")
        else:
            print(f"  ❌ {test_file} (not found)")

    print(f"\nTotal test files: {len([f for f in test_files if Path(f).exists()])}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run comprehensive integration tests for SpritePal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --gui                    # GUI tests only
  %(prog)s --headless              # Headless tests only  
  %(prog)s --performance           # Include performance tests
  %(prog)s --coverage --verbose    # With coverage and verbose output
  %(prog)s --parallel --gui        # Parallel GUI tests
  %(prog)s --dry-run --memory      # Show what memory tests would run
        """,
    )

    parser.add_argument("--gui", action="store_true", help="Run GUI tests (requires display)")
    parser.add_argument("--headless", action="store_true", help="Run headless tests only")
    parser.add_argument("--performance", action="store_true", help="Include performance tests")
    parser.add_argument("--memory", action="store_true", help="Include memory leak tests")
    parser.add_argument("--coverage", action="store_true", help="Run with coverage reporting")
    parser.add_argument("--parallel", action="store_true", help="Run tests in parallel")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--markers", action="store_true", help="Show available test markers")
    parser.add_argument("--dry-run", action="store_true", help="Show which tests would run without executing")

    args = parser.parse_args()

    if args.markers:
        show_available_markers()
        return 0

    print("SpritePal Comprehensive Integration Test Runner")
    print("=" * 50)

    # Setup environment
    setup_environment()

    # Check dependencies
    if not check_dependencies():
        return 1

    # Build pytest command
    cmd = get_pytest_command(args)

    if args.dry_run:
        dry_run_info(cmd)
        return 0

    # Display test configuration
    print("\nTest configuration:")
    print(f"  GUI tests: {'Yes' if args.gui or (not args.headless) else 'No'}")
    print(f"  Headless tests: {'Yes' if args.headless or (not args.gui) else 'No'}")
    print(f"  Performance tests: {'Yes' if args.performance else 'No'}")
    print(f"  Memory tests: {'Yes' if args.memory else 'No'}")
    print(f"  Coverage: {'Yes' if args.coverage else 'No'}")
    print(f"  Parallel: {'Yes' if args.parallel else 'No'}")
    print(f"  Verbose: {'Yes' if args.verbose else 'No'}")

    print(f"\nExecuting: {' '.join(cmd)}")
    print("=" * 50)

    # Run tests
    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\n\n⚠ Tests interrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Error running tests: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
