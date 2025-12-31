#!/usr/bin/env python3
from __future__ import annotations

"""
Install Memory Profiling Dependencies

This script installs the required packages for comprehensive memory leak profiling:
- objgraph: Object reference tracking and visualization
- pympler: Advanced memory profiling and analysis
- psutil: Process and system monitoring
- memory_profiler: Line-by-line memory profiling
"""

import subprocess
import sys


def install_package(package_name: str, description: str):
    """Install a package with pip."""
    print(f"Installing {package_name}: {description}")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        print(f"✅ {package_name} installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install {package_name}: {e}")
        return False


def check_virtual_environment():
    """Check if we're in a virtual environment."""
    in_venv = hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)

    if not in_venv:
        print("⚠️  WARNING: Not in a virtual environment!")
        print("   Consider activating your venv first:")
        print("   source venv/bin/activate  # Linux/macOS")
        print("   venv\\Scripts\\activate     # Windows")
        print()

        response = input("Continue anyway? (y/N): ").lower().strip()
        if response != "y":
            print("Installation cancelled.")
            return False
    else:
        print(f"✅ Virtual environment detected: {sys.prefix}")

    return True


def main():
    """Install all memory profiling dependencies."""
    print("SpritePal Memory Profiling Dependencies Installer")
    print("=" * 50)

    if not check_virtual_environment():
        return 1

    # Packages to install
    packages = [
        ("objgraph", "Object reference tracking and leak detection"),
        ("pympler", "Advanced memory profiling and heap analysis"),
        ("psutil", "Process and system resource monitoring"),
        ("memory_profiler", "Line-by-line memory usage profiling"),
        ("graphviz", "Graph visualization (optional, for objgraph graphs)"),
    ]

    print(f"\nInstalling {len(packages)} packages...")
    print()

    success_count = 0
    failed_packages = []

    for package, description in packages:
        if install_package(package, description):
            success_count += 1
        else:
            failed_packages.append(package)
        print()  # Blank line for readability

    # Summary
    print("Installation Summary")
    print("-" * 20)
    print(f"Successful: {success_count}/{len(packages)}")

    if failed_packages:
        print(f"Failed: {', '.join(failed_packages)}")
        print()
        print("You can try installing failed packages manually:")
        for package in failed_packages:
            print(f"  pip install {package}")
    else:
        print("✅ All packages installed successfully!")

    print()
    print("Next steps:")
    print("1. Run baseline memory profiling:")
    print("   python memory_leak_profiler.py --output baseline_report.txt")
    print()
    print("2. Run comprehensive leak tests:")
    print("   python scripts/run_memory_leak_tests.py")
    print()
    print("3. Monitor specific dialogs:")
    print("   python scripts/profile_dialog_leaks.py --dialog ManualOffsetDialog")

    return 0 if not failed_packages else 1


if __name__ == "__main__":
    sys.exit(main())
