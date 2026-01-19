#!/usr/bin/env python3
"""
Compare Lua memory dumps against Mesen2's Memory Viewer exports.

This is Step C of the debugging process:
If dumps match → Capture is correct, problem is in reconstruction
If dumps differ → Capture has a bug in how it reads memory

Usage:
    python compare_memory_dumps.py lua_dump.dmp mesen_dump.dmp
    python compare_memory_dumps.py --dir /path/to/dumps  # Compare all pairs

Example:
    python compare_memory_dumps.py lua_dump_1234_VRAM.dmp VRAMdump.dmp
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def compare_dumps(lua_path: Path, mesen_path: Path, verbose: bool = False) -> tuple[bool, str]:
    """
    Compare two memory dump files byte-by-byte.

    Returns (match: bool, message: str)
    """
    if not lua_path.exists():
        return False, f"Lua dump not found: {lua_path}"
    if not mesen_path.exists():
        return False, f"Mesen dump not found: {mesen_path}"

    lua_data = lua_path.read_bytes()
    mesen_data = mesen_path.read_bytes()

    if len(lua_data) != len(mesen_data):
        return False, f"Size mismatch: Lua={len(lua_data)} bytes, Mesen={len(mesen_data)} bytes"

    # Find first difference
    differences = []
    for i, (a, b) in enumerate(zip(lua_data, mesen_data)):
        if a != b:
            differences.append((i, a, b))
            if len(differences) >= 20:  # Cap at 20 differences for brevity
                break

    if not differences:
        return True, f"MATCH: {len(lua_data)} bytes identical"

    # Build difference report
    lines = [f"MISMATCH: {len(differences)}+ differences found in {len(lua_data)} bytes"]
    lines.append("")
    lines.append("First differences (offset, lua_byte, mesen_byte):")
    for offset, lua_byte, mesen_byte in differences[:10]:
        lines.append(f"  0x{offset:06X}: Lua=0x{lua_byte:02X} vs Mesen=0x{mesen_byte:02X}")

    if len(differences) > 10:
        lines.append(f"  ... and {len(differences) - 10}+ more")

    return False, "\n".join(lines)


def find_matching_pairs(dump_dir: Path) -> list[tuple[Path, Path, str]]:
    """Find Lua and Mesen dump pairs in a directory."""
    pairs = []

    # Look for Lua dumps (pattern: lua_dump_*_VRAM.dmp, lua_dump_*_CGRAM.dmp, lua_dump_*_OAM.dmp)
    for lua_file in dump_dir.glob("lua_dump_*_*.dmp"):
        # Extract memory type from filename
        parts = lua_file.stem.split("_")
        if len(parts) >= 3:
            mem_type = parts[-1]  # VRAM, CGRAM, OAM

            # Look for corresponding Mesen dump
            mesen_patterns = [
                f"{mem_type}dump.dmp",
                f"{mem_type}.dmp",
                f"{mem_type}Dump.dmp",  # Mixed case
            ]

            for pattern in mesen_patterns:
                mesen_path = dump_dir / pattern
                if mesen_path.exists():
                    pairs.append((lua_file, mesen_path, mem_type))
                    break

    return pairs


def main():
    parser = argparse.ArgumentParser(
        description="Compare Lua memory dumps against Mesen2 exports"
    )
    parser.add_argument("lua_dump", nargs="?", help="Path to Lua dump file")
    parser.add_argument("mesen_dump", nargs="?", help="Path to Mesen dump file")
    parser.add_argument("--dir", "-d", help="Directory containing both dump types")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.dir:
        # Auto-detect pairs in directory
        dump_dir = Path(args.dir)
        if not dump_dir.exists():
            print(f"Error: Directory not found: {dump_dir}")
            return 1

        pairs = find_matching_pairs(dump_dir)
        if not pairs:
            print(f"No matching dump pairs found in {dump_dir}")
            print("Looking for: lua_dump_*_VRAM.dmp + VRAMdump.dmp (etc.)")
            return 1

        print(f"Found {len(pairs)} dump pairs in {dump_dir}")
        print("=" * 60)

        all_match = True
        for lua_path, mesen_path, mem_type in pairs:
            print(f"\n{mem_type}:")
            print(f"  Lua:   {lua_path.name}")
            print(f"  Mesen: {mesen_path.name}")

            match, message = compare_dumps(lua_path, mesen_path, args.verbose)
            print(f"  Result: {message}")

            if not match:
                all_match = False

        print("\n" + "=" * 60)
        if all_match:
            print("VERDICT: All dumps MATCH - capture is correct!")
            print("         Problem is in reconstruction (Python code)")
        else:
            print("VERDICT: Dumps DIFFER - capture has a bug!")
            print("         Problem is in Lua memory reading")

        return 0 if all_match else 1

    elif args.lua_dump and args.mesen_dump:
        # Direct comparison of two files
        lua_path = Path(args.lua_dump)
        mesen_path = Path(args.mesen_dump)

        match, message = compare_dumps(lua_path, mesen_path, args.verbose)
        print(message)

        return 0 if match else 1

    else:
        parser.print_help()
        print("\nExamples:")
        print("  python compare_memory_dumps.py lua_dump_1234_VRAM.dmp VRAMdump.dmp")
        print("  python compare_memory_dumps.py --dir /path/to/DededeDMP")
        return 1


if __name__ == "__main__":
    sys.exit(main())
