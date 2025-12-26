#!/usr/bin/env python3
from __future__ import annotations

"""
Install Performance Validation Dependencies

This script ensures all dependencies for performance validation are installed.
"""

import subprocess
import sys


def install_package(package):
    """Install a package using pip."""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"✅ Installed {package}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install {package}: {e}")
        return False


def check_package(package):
    """Check if a package is already installed."""
    try:
        __import__(package)
        print(f"✅ {package} already installed")
        return True
    except ImportError:
        print(f"⚠️  {package} not found, installing...")
        return False


def main():
    """Install performance validation dependencies."""
    print("🔧 Installing Performance Validation Dependencies")
    print("=" * 50)

    # Core dependencies for performance testing
    dependencies = [
        "psutil",  # System/process monitoring
        "pytest-benchmark",  # Precise benchmarking
        "memory-profiler",  # Memory usage profiling
    ]

    all_success = True

    for dep in dependencies:
        if not check_package(dep.replace("-", "_")):
            if not install_package(dep):
                all_success = False

    print("\n" + "=" * 50)
    if all_success:
        print("✅ All performance validation dependencies are ready!")
        print("\nYou can now run performance validation:")
        print("  python scripts/run_performance_validation.py --verbose")
    else:
        print("❌ Some dependencies failed to install")
        print("Please install manually or check your environment")
        sys.exit(1)


if __name__ == "__main__":
    main()
