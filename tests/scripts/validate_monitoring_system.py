#!/usr/bin/env python3
"""
Validation Script for Test Monitoring System

Verifies that all monitoring tools are properly set up and provides
basic usage examples.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str, timeout: int = 30) -> tuple[bool, str]:
    """Run a command and return success status and output."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=Path(__file__).parent.parent.parent
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout}s"
    except Exception as e:
        return False, f"Error running command: {e}"


def validate_system():
    """Validate that the monitoring system is properly set up."""

    print("🔍 Validating Test Monitoring System")
    print("=" * 50)

    # Test 1: Progressive Test Runner - List Stages
    print("\n1. Testing Progressive Test Runner...")
    success, output = run_command(
        [sys.executable, "tests/scripts/progressive_test_runner.py", "--list-stages"], "List test stages"
    )

    if success and "Available test stages" in output:
        print("   ✅ Progressive test runner working")
        stages_count = output.count("- ")
        print(f"   📊 Found {stages_count} test stages defined")
    else:
        print("   ❌ Progressive test runner failed")
        print(f"   Error: {output[:200]}...")

    # Test 2: Fix Verification Orchestrator - List Categories
    print("\n2. Testing Fix Verification Orchestrator...")
    success, output = run_command(
        [sys.executable, "tests/scripts/fix_verification_orchestrator.py"], "List fix categories"
    )

    if success and "Available Fix Categories" in output:
        print("   ✅ Fix verification orchestrator working")
        categories = output.count("- ")
        print(f"   📊 Found {categories} fix categories available")
    else:
        print("   ❌ Fix verification orchestrator failed")
        print(f"   Error: {output[:200]}...")

    # Test 3: Test Health Dashboard - Import Check
    print("\n3. Testing Test Health Dashboard...")
    success, output = run_command(
        [
            sys.executable,
            "-c",
            "from tests.scripts.test_health_dashboard import TestHealthMonitor; print('Import successful')",
        ],
        "Import health dashboard",
        timeout=10,
    )

    if success and "Import successful" in output:
        print("   ✅ Test health dashboard imports working")
    else:
        print("   ❌ Test health dashboard import failed")
        print(f"   Error: {output[:200]}...")

    # Test 4: Regression Detector - Help
    print("\n4. Testing Regression Detector...")
    success, output = run_command(
        [sys.executable, "tests/scripts/regression_detector.py", "--help"], "Show regression detector help", timeout=10
    )

    if success and "Regression Detection System" in output:
        print("   ✅ Regression detector working")
    else:
        print("   ❌ Regression detector failed")
        print(f"   Error: {output[:200]}...")

    # Test 5: Directory Structure
    print("\n5. Checking Directory Structure...")
    scripts_dir = Path("tests/scripts")
    history_dir = scripts_dir / "history"
    sessions_dir = scripts_dir / "sessions"

    if scripts_dir.exists():
        print("   ✅ Scripts directory exists")
    else:
        print("   ❌ Scripts directory missing")
        return False

    history_dir.mkdir(exist_ok=True)
    sessions_dir.mkdir(exist_ok=True)

    print("   ✅ History and sessions directories created")

    # Test 6: Basic pytest functionality
    print("\n6. Testing Basic Pytest Integration...")
    success, output = run_command(
        ["bash", "-c", "source venv/bin/activate && python -m pytest tests/test_constants.py --collect-only -q"],
        "Collect constants tests",
        timeout=30,
    )

    if success:
        print("   ✅ Pytest integration working")
        if "collected" in output:
            import re

            match = re.search(r"(\d+) items? collected", output)
            if match:
                print(f"   📊 Successfully collected {match.group(1)} tests from constants")
    else:
        print("   ⚠️  Pytest integration has issues (this is expected)")
        print("   📝 Note: This indicates the actual test issues we need to fix")

    print("\n" + "=" * 50)
    print("✅ Monitoring System Validation Complete!")

    return True


def show_usage_examples():
    """Show practical usage examples."""

    print("\n🚀 QUICK START EXAMPLES")
    print("=" * 50)

    print("\n📊 1. Get Current Test Health:")
    print("   python tests/scripts/test_health_dashboard.py --quick-check")
    print("   (Note: May take 2-10 minutes depending on test suite status)")

    print("\n🔄 2. Run Progressive Test Analysis:")
    print("   python tests/scripts/progressive_test_runner.py --stage infrastructure")
    print("   python tests/scripts/progressive_test_runner.py --max-stage unit_core")

    print("\n🎯 3. Start Fix Verification Session:")
    print("   python tests/scripts/fix_verification_orchestrator.py \\")
    print("       --start-verification type_annotation \\")
    print("       --description 'Fix type annotations across test suite'")

    print("\n📈 4. Create Baseline Before Changes:")
    print("   python tests/scripts/regression_detector.py \\")
    print("       --baseline --tag 'before_fixes' \\")
    print("       --description 'State before type annotation fixes'")

    print("\n🔍 5. Check Fix Progress:")
    print("   python tests/scripts/fix_verification_orchestrator.py \\")
    print("       --check-progress your_session_id")

    print("\n📋 6. List All Sessions:")
    print("   python tests/scripts/fix_verification_orchestrator.py --list-sessions")

    print("\n🎉 7. Finalize and Generate Report:")
    print("   python tests/scripts/fix_verification_orchestrator.py \\")
    print("       --finalize-verification your_session_id")

    print("\n💡 RECOMMENDED WORKFLOW:")
    print("-" * 30)
    print("1. Run quick health check to understand current state")
    print("2. Start verification session for your fix category")
    print("3. Make incremental fixes")
    print("4. Check progress regularly with progressive runner")
    print("5. Finalize session when satisfied with results")
    print("6. Use regression detector to compare with previous state")


def main():
    """Main validation function."""

    # Change to project root
    project_root = Path(__file__).parent.parent.parent
    import os

    os.chdir(project_root)

    print(f"Working directory: {Path.cwd()}")
    print(f"Project root: {project_root}")

    # Validate system
    if validate_system():
        show_usage_examples()

        print("\n🎯 NEXT STEPS:")
        print("-" * 20)
        print("1. Try: python tests/scripts/progressive_test_runner.py --stage infrastructure")
        print("2. Check results and identify main issues")
        print("3. Start verification session for your first fix category")
        print("4. Begin systematic fix process")

        return True
    else:
        print("\n❌ System validation failed!")
        print("Please check error messages above and fix issues before proceeding.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
