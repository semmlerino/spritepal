#!/usr/bin/env python3
"""
Automated PRG ablation bisection tool.

Usage:
    python auto_bisect.py <target_addr> <start_addr> <end_addr> [--baseline <path>]

Example:
    python auto_bisect.py 0xE9E667 0xE9E000 0xE9FFFF --baseline prg_sweep_baseline_v225.txt

The tool will:
1. Run ablation tests, automatically bisecting toward the target address
2. Parse output logs for flip counts
3. Stop when reaching a single byte
4. Generate documentation for the bisection chain
"""

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Paths
SPRITEPAL_DIR = Path(r"C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal")
BATCH_FILE = SPRITEPAL_DIR / "run_ablation_range.bat"
LOG_FILE = SPRITEPAL_DIR / "mesen2_exchange" / "dma_probe_log.txt"
DEFAULT_BASELINE = SPRITEPAL_DIR / "prg_sweep_baseline_v225.txt"


def parse_addr(addr_str: str) -> int:
    """Parse hex address string to int."""
    return int(addr_str, 16)


def format_addr(addr: int) -> str:
    """Format address as hex string."""
    return f"0x{addr:X}"


def parse_staging_line(line: str) -> dict | None:
    """Parse a STAGING_SUMMARY line into components."""
    m = re.search(
        r'frame=(\d+).*src=(0x[0-9A-Fa-f]+).*size=(\d+).*payload_hash=(0x[0-9A-Fa-f]+).*vram=(0x[0-9A-Fa-f]+)',
        line
    )
    if m:
        return {
            'frame': int(m.group(1)),
            'src': m.group(2),
            'size': int(m.group(3)),
            'hash': m.group(4),
            'vram': m.group(5),
            'key': f"{m.group(1)}_{m.group(2)}_{m.group(3)}_{m.group(5)}"
        }
    return None


def load_staging(filepath: Path, vram_filter: list[str] | None = None) -> dict:
    """Load staging entries from log file, filtered by VRAM prefix."""
    entries = {}
    with open(filepath) as f:
        for line in f:
            if 'STAGING_SUMMARY' not in line:
                continue
            p = parse_staging_line(line)
            if p:
                if vram_filter and not any(p['vram'].startswith(pf) for pf in vram_filter):
                    continue
                entries[p['key']] = p
    return entries


def extract_hits(filepath: Path) -> list[tuple[int, int]]:
    """Extract ABLATION_HIT addresses and frames from log."""
    hits = []
    with open(filepath) as f:
        for line in f:
            m = re.search(r'ABLATION_HIT.*addr=(0x[0-9A-Fa-f]+).*frame=(\d+)', line)
            if m:
                hits.append((parse_addr(m.group(1)), int(m.group(2))))
    return hits


def compare_logs(baseline_path: Path, ablation_path: Path) -> tuple[int, int, int]:
    """
    Compare baseline and ablation logs.
    Returns: (flip_count, common_count, baseline_count)
    """
    baseline = load_staging(baseline_path, ['0x4', '0x5'])
    ablation = load_staging(ablation_path, ['0x4', '0x5'])

    common = set(baseline.keys()) & set(ablation.keys())

    flips = 0
    for key in common:
        if baseline[key]['hash'] != ablation[key]['hash']:
            flips += 1

    return flips, len(common), len(baseline)


def run_ablation(start: int, end: int) -> bool:
    """Run ablation test for given range. Returns True on success."""
    print(f"\n{'='*60}")
    print(f"Running ablation: {format_addr(start)} - {format_addr(end)}")
    print(f"Range size: {end - start + 1} bytes")
    print('='*60)

    # Run the batch file
    result = subprocess.run(
        [str(BATCH_FILE), format_addr(start), format_addr(end)],
        cwd=str(SPRITEPAL_DIR),
        shell=True,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"ERROR: Batch file failed with code {result.returncode}")
        print(result.stderr)
        return False

    # Verify log file exists
    if not LOG_FILE.exists():
        print("ERROR: Log file not created")
        return False

    return True


def bisect(target: int, start: int, end: int, baseline_path: Path) -> list[dict]:
    """
    Perform binary search bisection toward target address.
    Returns list of results for each step.
    """
    results = []
    step = 0

    while end > start:
        step += 1
        range_size = end - start + 1

        # Determine which half contains the target
        mid = start + (end - start) // 2

        if target <= mid:
            # Target in lower half
            test_start, test_end = start, mid
            next_start, next_end = start, mid
        else:
            # Target in upper half
            test_start, test_end = mid + 1, end
            next_start, next_end = mid + 1, end

        print(f"\n[Step {step}] Testing range containing target {format_addr(target)}")
        print(f"  Range: {format_addr(test_start)} - {format_addr(test_end)} ({test_end - test_start + 1} bytes)")

        # Run the test
        if not run_ablation(test_start, test_end):
            print("FATAL: Ablation run failed")
            break

        # Analyze results
        flips, common, baseline_count = compare_logs(baseline_path, LOG_FILE)
        hits = extract_hits(LOG_FILE)
        common_pct = (common / baseline_count * 100) if baseline_count > 0 else 0

        result = {
            'step': step,
            'start': test_start,
            'end': test_end,
            'size': test_end - test_start + 1,
            'flips': flips,
            'common': common,
            'common_pct': common_pct,
            'hits': hits,
            'causal': flips > 0
        }
        results.append(result)

        print(f"  Flips: {flips}, Common: {common}/{baseline_count} ({common_pct:.1f}%)")
        print(f"  Hits: {len(hits)}")

        if flips == 0:
            print("  WARNING: No flips - signal lost! Target address may be wrong.")
            # Continue anyway to the range we expect
        else:
            print(f"  CAUSAL - continuing bisection")

        # Save log for this step (copy instead of rename to avoid lock issues)
        log_backup = SPRITEPAL_DIR / f"bisect_step_{step}_{format_addr(test_start)}_{format_addr(test_end)}.txt"
        for attempt in range(3):
            try:
                if LOG_FILE.exists():
                    shutil.copy(LOG_FILE, log_backup)
                    print(f"  Log saved: {log_backup.name}")
                break
            except PermissionError:
                time.sleep(2)
        else:
            print(f"  Warning: Could not save log (file locked)")

        # Move to next range
        start, end = next_start, next_end

    # Final single-byte test
    if start == end:
        step += 1
        print(f"\n[Step {step}] FINAL: Single byte test {format_addr(start)}")

        if not run_ablation(start, start):
            print("FATAL: Final ablation run failed")
        else:
            flips, common, baseline_count = compare_logs(baseline_path, LOG_FILE)
            hits = extract_hits(LOG_FILE)
            common_pct = (common / baseline_count * 100) if baseline_count > 0 else 0

            result = {
                'step': step,
                'start': start,
                'end': start,
                'size': 1,
                'flips': flips,
                'common': common,
                'common_pct': common_pct,
                'hits': hits,
                'causal': flips > 0
            }
            results.append(result)

            print(f"  Flips: {flips}, Common: {common}/{baseline_count} ({common_pct:.1f}%)")

            if flips > 0:
                print(f"\n{'='*60}")
                print(f"SUCCESS: Minimal causal read address: {format_addr(start)}")
                print(f"{'='*60}")
            else:
                print(f"\n{'='*60}")
                print(f"WARNING: Final byte shows no flips - may need investigation")
                print(f"{'='*60}")

    return results


def generate_documentation(target: int, initial_start: int, initial_end: int, results: list[dict]) -> str:
    """Generate documentation block for the bisection chain."""
    lines = []
    lines.append(f"REM === {format_addr(target)} BISECTION CHAIN (AUTO-GENERATED) ===")
    lines.append(f"REM Target: {format_addr(target)}")
    lines.append(f"REM Initial range: {format_addr(initial_start)} - {format_addr(initial_end)} ({initial_end - initial_start + 1} bytes)")
    lines.append("REM")

    final = results[-1] if results else None
    if final and final['causal']:
        lines.append(f"REM RESULT: Minimal causal read address: {format_addr(final['start'])}")
        lines.append(f"REM   - {final['flips']} payload_hash flips")
        lines.append(f"REM   - Reduction: {initial_end - initial_start + 1} bytes -> 1 byte")
        lines.append("REM")

    lines.append("REM Bisection chain:")
    for r in results:
        status = "CAUSAL" if r['causal'] else "NOT CAUSAL"
        lines.append(f"REM   {format_addr(r['start'])}-{format_addr(r['end'])} ({r['size']}B): {status} - {r['flips']} flips")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Automated PRG ablation bisection')
    parser.add_argument('target', help='Target address to bisect toward (e.g., 0xE9E667)')
    parser.add_argument('start', help='Start of initial range (e.g., 0xE9E000)')
    parser.add_argument('end', help='End of initial range (e.g., 0xE9FFFF)')
    parser.add_argument('--baseline', default=str(DEFAULT_BASELINE),
                        help='Path to baseline log file')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print plan without running')

    args = parser.parse_args()

    target = parse_addr(args.target)
    start = parse_addr(args.start)
    end = parse_addr(args.end)
    baseline_path = Path(args.baseline)

    print(f"Auto-Bisection Tool")
    print(f"{'='*60}")
    print(f"Target address:  {format_addr(target)}")
    print(f"Initial range:   {format_addr(start)} - {format_addr(end)}")
    print(f"Range size:      {end - start + 1} bytes")
    print(f"Baseline:        {baseline_path}")
    print(f"{'='*60}")

    # Validate target is in range
    if not (start <= target <= end):
        print(f"ERROR: Target {format_addr(target)} not in range {format_addr(start)}-{format_addr(end)}")
        sys.exit(1)

    # Validate baseline exists
    if not baseline_path.exists():
        print(f"ERROR: Baseline file not found: {baseline_path}")
        sys.exit(1)

    # Calculate number of steps
    import math
    steps = math.ceil(math.log2(end - start + 1)) + 1
    print(f"Estimated steps: {steps}")

    if args.dry_run:
        print("\n[DRY RUN] Would bisect:")
        s, e = start, end
        step = 0
        while e > s:
            step += 1
            mid = s + (e - s) // 2
            if target <= mid:
                test_s, test_e = s, mid
                s, e = s, mid
            else:
                test_s, test_e = mid + 1, e
                s, e = mid + 1, e
            print(f"  Step {step}: {format_addr(test_s)} - {format_addr(test_e)} ({test_e - test_s + 1} bytes)")
        print(f"  Step {step + 1}: {format_addr(s)} (1 byte)")
        sys.exit(0)

    # Confirm before running
    print(f"\nThis will run ~{steps} ablation tests (~{steps * 45} seconds).")
    print("Press Enter to continue or Ctrl+C to abort...")
    try:
        input()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)

    # Run bisection
    results = bisect(target, start, end, baseline_path)

    # Generate documentation
    print("\n" + "="*60)
    print("DOCUMENTATION BLOCK (copy to batch file):")
    print("="*60)
    doc = generate_documentation(target, start, end, results)
    print(doc)

    # Save documentation to file
    doc_file = SPRITEPAL_DIR / f"bisect_{format_addr(target)}_results.txt"
    with open(doc_file, 'w') as f:
        f.write(doc)
    print(f"\nSaved to: {doc_file}")


if __name__ == '__main__':
    main()
