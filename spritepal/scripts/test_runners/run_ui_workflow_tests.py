#!/usr/bin/env python3
from __future__ import annotations

"""
UI Workflow Test Runner for SpritePal

This script runs the complete UI workflow integration tests with proper
environment setup and reporting.

Usage:
    python run_ui_workflow_tests.py [--headless] [--verbose] [--test=specific_test]

Environment Requirements:
- pytest-qt installed
- PySide6 with proper Qt installation
- Qt offscreen mode is used for headless testing (no xvfb needed)
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def setup_environment():
    """Set up environment for UI testing."""
    # Add project root to Python path
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    
    # Set Qt platform for testing
    if not os.environ.get("DISPLAY") and not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    
    # Ensure proper logging for Qt
    os.environ["QT_LOGGING_RULES"] = "qt.qpa.xcb.xcb_screen=false"

def check_dependencies():
    """Check that required dependencies are installed."""
    required_packages = ['pytest', 'pytest-qt', 'PySide6']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"Missing required packages: {', '.join(missing_packages)}")
        print("Install with: pip install " + " ".join(missing_packages))
        return False
    
    return True

def run_tests(args):
    """Run the UI workflow tests with appropriate configuration."""
    setup_environment()
    
    if not check_dependencies():
        return 1
    
    # Base pytest command
    cmd = [
        sys.executable, "-m", "pytest",
        "test_complete_ui_workflows_integration.py",
        "-v",  # Verbose output
        "--tb=short",  # Short traceback format
        "--strict-markers",  # Strict marker checking
        "-m", "gui",  # Only run GUI tests
    ]
    
    # Add test-specific arguments
    if args.verbose:
        cmd.append("-s")  # Don't capture stdout
    
    if args.test:
        cmd.extend(["-k", args.test])  # Run specific test
    
    if args.headless:
        # Use Qt offscreen mode for headless testing (canonical approach)
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QUICK_BACKEND"] = "software"
    
    # Add coverage if requested
    if args.coverage:
        cmd.extend(["--cov=ui", "--cov-report=html", "--cov-report=term"])
    
    # Add parallel execution if supported and not serial
    if not args.serial and not args.test:
        try:
            import xdist
            cmd.extend(["-n", "auto"])
            del xdist  # Avoid unused variable warning
        except ImportError:
            print("pytest-xdist not available, running serially")
    
    print(f"Running command: {' '.join(cmd)}")
    print("-" * 60)
    
    # Run the tests
    result = subprocess.run(cmd, cwd=Path(__file__).parent)
    return result.returncode

def run_specific_workflow_tests():
    """Run specific workflow tests with detailed reporting."""
    workflows = {
        "startup": "test_app_startup_dark_theme_rom_loading_workflow",
        "manual_offset": "test_manual_offset_dialog_interaction_workflow", 
        "signals": "test_sprite_found_signal_propagation_workflow",
        "tabs": "test_manual_offset_tab_switching_state_preservation_workflow",
        "resize": "test_window_resize_layout_theme_preservation_workflow",
        "responsiveness": "test_ui_responsiveness_during_workflows",
        "errors": "test_error_recovery_in_ui_workflows",
    }
    
    print("Available workflow tests:")
    for key, test_name in workflows.items():
        print(f"  {key}: {test_name}")
    
    choice = input("\nEnter workflow to test (or 'all'): ").strip().lower()
    
    if choice == 'all':
        return run_tests(argparse.Namespace(
            verbose=True, test=None, headless=False, 
            coverage=False, serial=True
        ))
    elif choice in workflows:
        return run_tests(argparse.Namespace(
            verbose=True, test=workflows[choice], headless=False,
            coverage=False, serial=True
        ))
    else:
        print(f"Unknown workflow: {choice}")
        return 1

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run SpritePal UI workflow integration tests"
    )
    
    parser.add_argument(
        "--headless", action="store_true",
        help="Run tests in headless mode (uses Qt offscreen platform)"
    )
    
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Verbose output (don't capture stdout)"
    )
    
    parser.add_argument(
        "--test", "-k",
        help="Run specific test (pytest -k pattern)"
    )
    
    parser.add_argument(
        "--coverage", action="store_true",
        help="Generate coverage report"
    )
    
    parser.add_argument(
        "--serial", action="store_true",
        help="Force serial execution (no parallel tests)"
    )
    
    parser.add_argument(
        "--interactive", "-i", action="store_true",
        help="Interactive mode - choose specific workflows"
    )
    
    args = parser.parse_args()
    
    if args.interactive:
        return run_specific_workflow_tests()
    else:
        return run_tests(args)

if __name__ == "__main__":
    sys.exit(main())
