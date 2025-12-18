#!/usr/bin/env python3
from __future__ import annotations

"""
Safe test runner for SpritePal that handles Qt testing in various environments.

Uses Qt offscreen mode as the canonical approach for headless testing.
See CLAUDE.md for details on the testing strategy.
"""

import os
import subprocess
import sys


class TestEnvironment:
    """Detect and configure test environment"""

    def __init__(self):
        self.is_wsl = self._detect_wsl()
        self.is_ci = bool(os.environ.get("CI"))
        self.has_display = bool(os.environ.get("DISPLAY"))
        self.qt_platform = os.environ.get("QT_QPA_PLATFORM", "")

    def _detect_wsl(self):
        """Detect if running in WSL"""
        if sys.platform != "linux":
            return False
        try:
            with open("/proc/version") as f:
                return "microsoft" in f.read().lower()
        except OSError:
            return False

    def get_strategy(self):
        """Determine best testing strategy.

        Returns 'native' if display available and not CI, otherwise 'offscreen'.
        Offscreen is the canonical approach for headless testing.
        """
        if self.has_display and not self.is_ci:
            return "native"
        return "offscreen"

    def __str__(self):
        return (
            f"TestEnvironment(\n"
            f"  WSL: {self.is_wsl}\n"
            f"  CI: {self.is_ci}\n"
            f"  Display: {self.has_display}\n"
            f"  Qt Platform: {self.qt_platform or 'not set'}\n"
            f"  Strategy: {self.get_strategy()}\n"
            f")"
        )


def run_tests_native(args):
    """Run tests with native display"""
    print("Running tests with native display...")
    env = os.environ.copy()
    # Don't override QT_QPA_PLATFORM if display is available
    if "QT_QPA_PLATFORM" in env:
        del env["QT_QPA_PLATFORM"]

    cmd = [sys.executable, "-m", "pytest", *args]
    return subprocess.run(cmd, check=False, env=env).returncode


def run_tests_offscreen(args):
    """Run tests with Qt offscreen platform.

    GUI tests run in offscreen mode - rendered to framebuffer, not displayed.
    This is the canonical approach for headless testing. See CLAUDE.md.
    """
    print("Running tests with Qt offscreen platform...")
    print("Note: GUI tests run in offscreen mode (rendered to framebuffer, not displayed)")

    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_BACKEND"] = "software"
    env["QT_LOGGING_RULES"] = "*.debug=false"

    cmd = [sys.executable, "-m", "pytest", *args]
    return subprocess.run(cmd, check=False, env=env).returncode


def main():
    """Main entry point"""
    args = sys.argv[1:]

    # Detect environment
    env = TestEnvironment()
    print(env)

    # Special handling for explicit strategies
    if "--native" in args:
        args.remove("--native")
        return run_tests_native(args)
    if "--offscreen" in args:
        args.remove("--offscreen")
        return run_tests_offscreen(args)

    # Auto-select strategy
    strategy = env.get_strategy()

    if strategy == "native":
        return run_tests_native(args)
    return run_tests_offscreen(args)


if __name__ == "__main__":
    sys.exit(main())
