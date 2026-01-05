#!/usr/bin/env python3
"""
Compare FILL_BUFFER_BYTES against ROM bytes at PRG run addresses.

Determines whether the buffer fill is a direct copy or decompression.

Usage:
    python compare_fill_session.py <rom_file> <log_file>

Example:
    python compare_fill_session.py "roms/Kirby Super Star (USA).sfc" mesen2_exchange/dma_probe_log.txt
"""

import re
import sys
from pathlib import Path


def sa1_prg_to_file_offset(prg_addr: int) -> int:
    """Convert SA-1 PRG address to file offset.

    SA-1 HiROM mapping for banks $C0-$FF:
    file_offset = (bank - 0xC0) * 0x10000 + (addr & 0xFFFF)
    """
    bank = (prg_addr >> 16) & 0xFF
    offset = prg_addr & 0xFFFF

    if bank >= 0xC0:
        return (bank - 0xC0) * 0x10000 + offset
    elif bank >= 0x00 and bank <= 0x3F:
        # LoROM-style mapping (banks 00-3F mirror 80-BF)
        return (bank * 0x8000) + (offset - 0x8000) if offset >= 0x8000 else None
    else:
        return None


def parse_fill_sessions(log_path: Path) -> list:
    """Parse FILL_SESSION and FILL_BUFFER_BYTES pairs from log."""
    sessions = []
    current_session = None

    with open(log_path) as f:
        for line in f:
            # Parse FILL_SESSION
            match = re.search(r"FILL_SESSION: frame=(\d+).*prg_runs=\[(.*?)\]", line)
            if match:
                frame = int(match.group(1))
                prg_runs_str = match.group(2)

                # Parse PRG runs: 0xAAAAAA-0xBBBBBB(N)
                prg_runs = []
                for run_match in re.finditer(r"0x([0-9A-Fa-f]+)-0x([0-9A-Fa-f]+)\((\d+)\)", prg_runs_str):
                    start = int(run_match.group(1), 16)
                    end = int(run_match.group(2), 16)
                    length = int(run_match.group(3))
                    prg_runs.append({"start": start, "end": end, "length": length})

                current_session = {
                    "frame": frame,
                    "prg_runs": prg_runs,
                    "buffer_bytes": None,
                    "buffer_range": None,
                }
                continue

            # Parse FILL_BUFFER_BYTES
            match = re.search(
                r"FILL_BUFFER_BYTES: frame=(\d+) addr_range=0x([0-9A-Fa-f]+)-0x([0-9A-Fa-f]+) bytes=(\d+) hex=([0-9A-Fa-f-]+)",
                line,
            )
            if match and current_session:
                frame = int(match.group(1))
                if frame == current_session["frame"]:
                    addr_start = int(match.group(2), 16)
                    addr_end = int(match.group(3), 16)
                    int(match.group(4))
                    hex_str = match.group(5)

                    # Parse hex bytes (handle -- gaps)
                    buffer_bytes = []
                    i = 0
                    while i < len(hex_str):
                        if hex_str[i : i + 2] == "--":
                            buffer_bytes.append(None)
                            i += 2
                        else:
                            buffer_bytes.append(int(hex_str[i : i + 2], 16))
                            i += 2

                    current_session["buffer_bytes"] = buffer_bytes
                    current_session["buffer_range"] = (addr_start, addr_end)
                    sessions.append(current_session)
                    current_session = None

    return sessions


def compare_session(session: dict, rom_data: bytes) -> dict:
    """Compare buffer bytes against ROM bytes at largest PRG run."""
    result = {
        "frame": session["frame"],
        "buffer_size": len(session["buffer_bytes"]) if session["buffer_bytes"] else 0,
        "matches": [],
        "best_match": None,
    }

    if not session["buffer_bytes"] or not session["prg_runs"]:
        return result

    buffer_bytes = [b for b in session["buffer_bytes"] if b is not None]
    if not buffer_bytes:
        return result

    # Sort PRG runs by length (largest first)
    sorted_runs = sorted(session["prg_runs"], key=lambda r: r["length"], reverse=True)

    for run in sorted_runs:
        file_offset = sa1_prg_to_file_offset(run["start"])
        if file_offset is None:
            continue

        run_length = run["length"]
        if file_offset + run_length > len(rom_data):
            continue

        rom_bytes = list(rom_data[file_offset : file_offset + run_length])

        # Compare: look for substring match in buffer
        match_info = {
            "prg_start": run["start"],
            "prg_length": run_length,
            "file_offset": file_offset,
            "exact_match": False,
            "substring_match": False,
            "match_position": None,
            "match_length": 0,
        }

        # Check exact match (ROM bytes appear verbatim in buffer)
        buffer_str = bytes(buffer_bytes)
        rom_str = bytes(rom_bytes)

        pos = buffer_str.find(rom_str)
        if pos >= 0:
            match_info["exact_match"] = True
            match_info["substring_match"] = True
            match_info["match_position"] = pos
            match_info["match_length"] = run_length
        else:
            # Check for partial/substring match
            # Try finding largest common subsequence
            for start in range(len(buffer_bytes) - 8):
                for rom_start in range(len(rom_bytes) - 8):
                    match_len = 0
                    while (
                        start + match_len < len(buffer_bytes)
                        and rom_start + match_len < len(rom_bytes)
                        and buffer_bytes[start + match_len] == rom_bytes[rom_start + match_len]
                    ):
                        match_len += 1

                    if match_len >= 8 and match_len > match_info["match_length"]:
                        match_info["substring_match"] = True
                        match_info["match_position"] = start
                        match_info["match_length"] = match_len

        result["matches"].append(match_info)

        if match_info["exact_match"] or (
            match_info["match_length"] > 0
            and (result["best_match"] is None or match_info["match_length"] > result["best_match"]["match_length"])
        ):
            result["best_match"] = match_info

    return result


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    rom_path = Path(sys.argv[1])
    log_path = Path(sys.argv[2])

    if not rom_path.exists():
        print(f"Error: ROM file not found: {rom_path}")
        sys.exit(1)

    if not log_path.exists():
        print(f"Error: Log file not found: {log_path}")
        sys.exit(1)

    print(f"Loading ROM: {rom_path}")
    with open(rom_path, "rb") as f:
        rom_data = f.read()
    print(f"ROM size: {len(rom_data)} bytes")

    print(f"\nParsing log: {log_path}")
    sessions = parse_fill_sessions(log_path)
    print(f"Found {len(sessions)} fill sessions with buffer bytes")

    if not sessions:
        print("\nNo FILL_BUFFER_BYTES entries found.")
        print("Make sure you're running v2.10+ of the DMA probe with BUFFER_WRITE_WATCH=1")
        sys.exit(0)

    print("\n" + "=" * 70)
    print("COMPARISON RESULTS")
    print("=" * 70)

    exact_matches = 0
    substring_matches = 0
    no_matches = 0

    for session in sessions:
        result = compare_session(session, rom_data)

        print(f"\nFrame {result['frame']}: {result['buffer_size']} buffer bytes")

        if result["best_match"]:
            bm = result["best_match"]
            if bm["exact_match"]:
                exact_matches += 1
                print(f"  EXACT MATCH: PRG 0x{bm['prg_start']:06X} ({bm['prg_length']} bytes)")
                print(f"    File offset: 0x{bm['file_offset']:06X}")
                print(f"    Buffer position: {bm['match_position']}")
            elif bm["substring_match"]:
                substring_matches += 1
                print(f"  PARTIAL MATCH: PRG 0x{bm['prg_start']:06X}")
                print(f"    File offset: 0x{bm['file_offset']:06X}")
                print(f"    Match length: {bm['match_length']} bytes at buffer pos {bm['match_position']}")
            else:
                no_matches += 1
                print("  NO MATCH - likely decompression")
        else:
            no_matches += 1
            print("  NO MATCH - likely decompression")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Exact matches (direct copy):    {exact_matches}")
    print(f"Partial matches:                {substring_matches}")
    print(f"No matches (decompression):     {no_matches}")

    if exact_matches > 0:
        print("\n*** DIRECT COPY DETECTED ***")
        print("Some buffer fills are verbatim ROM copies.")
        print("The PRG addresses can be converted directly to ROM offsets.")
    elif substring_matches > 0:
        print("\n*** PARTIAL MATCHES ***")
        print("Some ROM data appears in buffer, but not as complete copies.")
        print("May indicate block-based decompression or stride patterns.")
    else:
        print("\n*** DECOMPRESSION LIKELY ***")
        print("Buffer bytes don't match ROM bytes.")
        print("The fill routine is transforming data (HAL compression?).")


if __name__ == "__main__":
    main()
