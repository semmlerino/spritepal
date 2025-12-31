#!/usr/bin/env python3
"""
Compile HAL compression tools (exhal/inhal) for the current platform.

Usage:
    python compile_hal_tools.py           # Compile for current platform
    python compile_hal_tools.py --check   # Check if tools exist without compiling
    python compile_hal_tools.py --clean   # Remove compiled binaries

Expected outputs (in tools/):
    - Windows: exhal.exe, inhal.exe
    - Linux/macOS: exhal, inhal
    - Platform marker: .platform_windows or .platform_linux

Requirements:
    - Windows: MinGW-w64 (gcc) or Visual Studio (cl)
    - Linux/macOS: gcc or clang, make

Failure modes:
    - Exit 1: Compiler not found (install gcc/MinGW)
    - Exit 2: Source files not found
    - Exit 3: Compilation failed (check compiler output)
    - Exit 4: Copy to tools/ failed

Source location:
    ../archive/obsolete_test_images/ultrathink/
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
TOOLS_DIR = SCRIPT_DIR / "tools"
SOURCE_DIR = SCRIPT_DIR.parent / "archive" / "obsolete_test_images" / "ultrathink"

# Source files required for compilation
EXHAL_SOURCES = ["exhal.c", "compress.c"]
INHAL_SOURCES = ["inhal.c", "compress.c", "memmem.c"]


def detect_platform() -> str:
    """Detect current platform: 'windows', 'linux', or 'darwin'."""
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    elif system == "darwin":
        return "darwin"
    else:
        return "linux"


def find_compiler() -> tuple[str, list[str]] | None:
    """
    Find available C compiler.

    Returns:
        Tuple of (compiler_path, base_flags) or None if not found.
    """
    system = detect_platform()

    if system == "windows":
        # Try MinGW first, then MSVC
        for compiler in ["gcc", "x86_64-w64-mingw32-gcc", "cl"]:
            if shutil.which(compiler):
                if compiler == "cl":
                    return compiler, ["/O2", "/W3"]
                return compiler, ["-O2", "-Wall"]
    else:
        # Try gcc, then clang
        for compiler in ["gcc", "clang", "cc"]:
            if shutil.which(compiler):
                return compiler, ["-O2", "-Wall"]

    return None


def check_sources() -> bool:
    """Verify source files exist."""
    required_files = {"exhal.c", "inhal.c", "compress.c", "compress.h", "memmem.c"}
    if not SOURCE_DIR.exists():
        print(f"ERROR: Source directory not found: {SOURCE_DIR}", file=sys.stderr)
        return False

    missing = []
    for f in required_files:
        if not (SOURCE_DIR / f).exists():
            missing.append(f)

    if missing:
        print(f"ERROR: Missing source files in {SOURCE_DIR}:", file=sys.stderr)
        for f in missing:
            print(f"  - {f}", file=sys.stderr)
        return False

    return True


def compile_tool(
    compiler: str,
    flags: list[str],
    sources: list[str],
    output: str,
    system: str,
) -> bool:
    """
    Compile a single tool.

    Args:
        compiler: Compiler executable name
        flags: Compiler flags
        sources: List of source file names
        output: Output binary name (without extension)
        system: Target platform

    Returns:
        True if compilation succeeded
    """
    source_paths = [str(SOURCE_DIR / src) for src in sources]

    if system == "windows":
        output_name = f"{output}.exe"
    else:
        output_name = output

    output_path = TOOLS_DIR / output_name

    if compiler == "cl":
        # MSVC syntax
        cmd = [compiler, *flags, *source_paths, f"/Fe:{output_path}"]
    else:
        # GCC/Clang syntax
        cmd = [compiler, *flags, "-o", str(output_path), *source_paths]

    print(f"Compiling {output_name}...")
    print(f"  Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=SOURCE_DIR,
        )

        if result.returncode != 0:
            print(f"ERROR: Compilation failed for {output_name}", file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            if result.stdout:
                print(result.stdout, file=sys.stderr)
            return False

        # Make executable on Unix
        if system != "windows":
            output_path.chmod(0o755)

        print(f"  Created: {output_path}")
        return True

    except FileNotFoundError:
        print(f"ERROR: Compiler not found: {compiler}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR: Compilation error: {e}", file=sys.stderr)
        return False


def write_platform_marker(system: str) -> None:
    """Write platform marker file to tools directory."""
    # Remove any existing markers
    for marker in TOOLS_DIR.glob(".platform_*"):
        marker.unlink()

    marker_name = f".platform_{system}"
    marker_path = TOOLS_DIR / marker_name
    marker_path.touch()
    print(f"Created platform marker: {marker_name}")


def check_existing_tools() -> dict[str, bool]:
    """Check which tools already exist."""
    system = detect_platform()
    ext = ".exe" if system == "windows" else ""

    return {
        "exhal": (TOOLS_DIR / f"exhal{ext}").exists(),
        "inhal": (TOOLS_DIR / f"inhal{ext}").exists(),
    }


def clean_tools() -> None:
    """Remove compiled binaries and markers."""
    removed = []

    for pattern in ["exhal", "exhal.exe", "inhal", "inhal.exe", ".platform_*"]:
        for f in TOOLS_DIR.glob(pattern):
            if f.is_file():
                f.unlink()
                removed.append(f.name)

    if removed:
        print(f"Removed: {', '.join(removed)}")
    else:
        print("No files to remove.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile HAL compression tools (exhal/inhal)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if tools exist without compiling",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove compiled binaries",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompile even if tools exist",
    )
    args = parser.parse_args()

    system = detect_platform()
    print(f"Platform: {system}")
    print(f"Tools directory: {TOOLS_DIR}")
    print(f"Source directory: {SOURCE_DIR}")
    print()

    # Ensure tools directory exists
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)

    if args.clean:
        clean_tools()
        return 0

    existing = check_existing_tools()

    if args.check:
        all_exist = all(existing.values())
        for tool, exists in existing.items():
            status = "OK" if exists else "MISSING"
            print(f"  {tool}: {status}")
        return 0 if all_exist else 1

    # Skip if tools exist and --force not specified
    if all(existing.values()) and not args.force:
        print("Tools already exist. Use --force to recompile.")
        return 0

    # Find compiler
    compiler_result = find_compiler()
    if not compiler_result:
        print("ERROR: No C compiler found.", file=sys.stderr)
        print(file=sys.stderr)
        if system == "windows":
            print("Install MinGW-w64: https://www.mingw-w64.org/downloads/", file=sys.stderr)
            print("Or install Visual Studio with C++ workload", file=sys.stderr)
        else:
            print("Install GCC: sudo apt-get install build-essential", file=sys.stderr)
        return 1

    compiler, flags = compiler_result
    print(f"Compiler: {compiler}")
    print()

    # Check sources
    if not check_sources():
        return 2

    # Compile both tools
    success = True

    if not compile_tool(compiler, flags, EXHAL_SOURCES, "exhal", system):
        success = False

    if not compile_tool(compiler, flags, INHAL_SOURCES, "inhal", system):
        success = False

    if not success:
        print()
        print("ERROR: Compilation failed. See errors above.", file=sys.stderr)
        return 3

    # Write platform marker
    write_platform_marker(system)

    print()
    print("SUCCESS: HAL tools compiled successfully!")
    print()
    print("Next steps:")
    print("  1. Run 'uv run pytest tests/test_hal_golden.py -v' to verify")
    print("  2. The tools are now available for ROM extraction/injection")

    return 0


if __name__ == "__main__":
    sys.exit(main())
