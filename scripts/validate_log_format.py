#!/usr/bin/env python3
"""
Validate dma_probe_log.txt format against Instrumentation Contract v1.1.

Ensures log files are parseable and self-describing. Fails fast on format drift.

Usage:
    python scripts/validate_log_format.py mesen2_exchange/dma_probe_log.txt
    python scripts/validate_log_format.py mesen2_exchange/sa1_hypothesis_run_*/

Exit codes:
    0 - Valid log format
    1 - Invalid format or missing required fields
    2 - File not found or read error
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# =============================================================================
# Log Header Pattern (must be first line)
# =============================================================================
# Example: # LOG_VERSION=1.1 RUN_ID=1735678900_a3f2 ROM=Kirby Super Star (USA) SHA256=N/A PRG_SIZE=0x100000
HEADER_PATTERN = re.compile(
    r"^# LOG_VERSION=(?P<version>[\d.]+) "
    r"RUN_ID=(?P<run_id>\S+) "
    r"ROM=(?P<rom>.+?) "
    r"SHA256=(?P<sha256>\S+) "
    r"PRG_SIZE=(?P<prg_size>\S+)$"
)

SUPPORTED_VERSIONS = {"1.1"}


# =============================================================================
# Log Line Patterns
# =============================================================================

# SA1_BANKS: frame=0 run=123_a3f2 cxb=0x00 dxb=0x01 exb=0x02 fxb=0x03 bmaps=0x00 bmap=0x00
SA1_BANKS_PATTERN = re.compile(
    r"SA1_BANKS \((?P<reason>\w+)\): "
    r"frame=(?P<frame>\d+) "
    r"run=(?P<run_id>\S+) "
    r"cxb=0x(?P<cxb>[0-9A-Fa-f]{2}) "
    r"dxb=0x(?P<dxb>[0-9A-Fa-f]{2}) "
    r"exb=0x(?P<exb>[0-9A-Fa-f]{2}) "
    r"fxb=0x(?P<fxb>[0-9A-Fa-f]{2}) "
    r"bmaps=0x(?P<bmaps>[0-9A-Fa-f]{2}) "
    r"bmap=0x(?P<bmap>[0-9A-Fa-f]{2})"
)

# SA1 DMA (ctrl_write): ctrl=0xA0 enabled=Y char_conv=Y auto=N src_dev=0 dest_dev=0 src=0x123456 dest=0x654321 size=0x0100
SA1_DMA_PATTERN = re.compile(
    r"SA1 DMA \((?P<reason>\w+)\): "
    r"ctrl=0x(?P<ctrl>[0-9A-Fa-f]{2}) "
    r"enabled=(?P<enabled>[YN]) "
    r"char_conv=(?P<char_conv>[YN]) "
    r"auto=(?P<auto>[YN])"
)

# DMA ch0: mode=0x01 VRAM word=0x1234 src=0x007E2000 size=0x0800 (legacy format)
DMA_VRAM_PATTERN = re.compile(
    r"DMA ch(?P<channel>\d): "
    r"mode=0x(?P<mode>[0-9A-Fa-f]{2}) "
    r"VRAM word=0x(?P<vram_word>[0-9A-Fa-f]{4})"
)

# SNES_DMA_VRAM: frame=100 run=123_a3f2 ch=1 dmap=0x01 src=0x3000 src_bank=0x00 size=0x0800 vmadd=0x6000
SNES_DMA_VRAM_PATTERN = re.compile(
    r"SNES_DMA_VRAM: "
    r"frame=(?P<frame>\d+) "
    r"run=(?P<run_id>\S+) "
    r"ch=(?P<channel>\d) "
    r"dmap=0x(?P<dmap>[0-9A-Fa-f]{2}) "
    r"src=0x(?P<src>[0-9A-Fa-f]{4}) "
    r"src_bank=0x(?P<src_bank>[0-9A-Fa-f]{2}) "
    r"size=0x(?P<size>[0-9A-Fa-f]{4}) "
    r"vmadd=0x(?P<vmadd>[0-9A-Fa-f]{4})"
)

# CCDMA_START: frame=100 run=123_a3f2 dcnt=0xA0 cdma=0x03 ss=0 (ROM) dest_dev=0 (I-RAM) src=0x3C8000 dest=0x003000 size=0x0800
CCDMA_START_PATTERN = re.compile(
    r"CCDMA_START: "
    r"frame=(?P<frame>\d+) "
    r"run=(?P<run_id>\S+) "
    r"dcnt=0x(?P<dcnt>[0-9A-Fa-f]{2}) "
    r"cdma=0x(?P<cdma>[0-9A-Fa-f]{2}) "
    r"ss=(?P<ss>\d) "
    r"\((?P<ss_name>\S+)\) "
    r"dest_dev=(?P<dest_dev>\d) "
    r"\((?P<dest_name>\S+)\) "
    r"src=0x(?P<src>[0-9A-Fa-f]{6}) "
    r"dest=0x(?P<dest>[0-9A-Fa-f]{6}) "
    r"size=0x(?P<size>[0-9A-Fa-f]{4})"
)

# Patterns we recognize (for statistics)
KNOWN_PATTERNS = {
    "SA1_BANKS": SA1_BANKS_PATTERN,
    "SA1_DMA": SA1_DMA_PATTERN,
    "DMA_VRAM": DMA_VRAM_PATTERN,
    "SNES_DMA_VRAM": SNES_DMA_VRAM_PATTERN,
    "CCDMA_START": CCDMA_START_PATTERN,
}


@dataclass
class LogHeader:
    """Parsed log header."""

    version: str
    run_id: str
    rom: str
    sha256: str
    prg_size: str
    raw_line: str


@dataclass
class ValidationResult:
    """Result of log validation."""

    valid: bool
    log_file: str
    header: LogHeader | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    line_counts: dict[str, int] = field(default_factory=dict)
    total_lines: int = 0
    unrecognized_lines: int = 0


def parse_header(line: str) -> LogHeader | None:
    """Parse log header line."""
    match = HEADER_PATTERN.match(line)
    if not match:
        return None
    return LogHeader(
        version=match.group("version"),
        run_id=match.group("run_id"),
        rom=match.group("rom"),
        sha256=match.group("sha256"),
        prg_size=match.group("prg_size"),
        raw_line=line,
    )


def validate_log(log_path: Path) -> ValidationResult:
    """Validate a dma_probe_log.txt file against the instrumentation contract."""
    result = ValidationResult(valid=True, log_file=str(log_path))

    if not log_path.exists():
        result.valid = False
        result.errors.append(f"File not found: {log_path}")
        return result

    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        result.valid = False
        result.errors.append(f"Failed to read file: {e}")
        return result

    if not lines:
        result.valid = False
        result.errors.append("Empty log file")
        return result

    result.total_lines = len(lines)

    # Validate header (must be first line)
    first_line = lines[0].strip()
    header = parse_header(first_line)

    if header is None:
        result.valid = False
        result.errors.append(f"Missing or invalid header. First line: {first_line[:100]}")
    else:
        result.header = header

        # Check version compatibility
        if header.version not in SUPPORTED_VERSIONS:
            result.valid = False
            result.errors.append(
                f"Unsupported log version: {header.version}. "
                f"Supported: {', '.join(sorted(SUPPORTED_VERSIONS))}"
            )

        # Warn about missing SHA256
        if header.sha256 == "N/A":
            result.warnings.append("ROM SHA256 not available (verification limited)")

    # Initialize line counters
    for name in KNOWN_PATTERNS:
        result.line_counts[name] = 0

    # Validate content lines (skip header)
    for line_no, line in enumerate(lines[1:], start=2):
        line = line.strip()
        if not line:
            continue

        # Check timestamp prefix (HH:MM:SS)
        if not re.match(r"^\d{2}:\d{2}:\d{2} ", line):
            result.warnings.append(f"Line {line_no}: Missing timestamp prefix")

        # Try to match known patterns
        matched = False
        for name, pattern in KNOWN_PATTERNS.items():
            if pattern.search(line):
                result.line_counts[name] += 1
                matched = True
                break

        if not matched:
            result.unrecognized_lines += 1

    # Warn if no SA1_BANKS init entry found
    if result.line_counts.get("SA1_BANKS", 0) == 0:
        result.warnings.append("No SA1_BANKS entries found (expected at least 'init')")

    return result


def print_report(result: ValidationResult) -> None:
    """Print validation report."""
    print("=" * 70)
    print("DMA PROBE LOG VALIDATION REPORT")
    print("=" * 70)
    print()

    print(f"File: {result.log_file}")
    print(f"Status: {'VALID' if result.valid else 'INVALID'}")
    print()

    if result.header:
        print("Header:")
        print(f"  Version:  {result.header.version}")
        print(f"  Run ID:   {result.header.run_id}")
        print(f"  ROM:      {result.header.rom}")
        print(f"  SHA256:   {result.header.sha256}")
        print(f"  PRG Size: {result.header.prg_size}")
        print()

    print(f"Total lines: {result.total_lines}")
    print()

    if result.line_counts:
        print("Line type counts:")
        for name, count in sorted(result.line_counts.items()):
            print(f"  {name}: {count}")
        print(f"  (unrecognized): {result.unrecognized_lines}")
        print()

    if result.errors:
        print("ERRORS:")
        for error in result.errors:
            print(f"  ✗ {error}")
        print()

    if result.warnings:
        print("WARNINGS:")
        for warning in result.warnings:
            print(f"  ⚠ {warning}")
        print()

    print("=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate dma_probe_log.txt format against Instrumentation Contract v1.1."
    )
    parser.add_argument(
        "target",
        type=Path,
        help="Log file or directory containing dma_probe_log.txt",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
    )

    args = parser.parse_args()

    # Find the log file
    if args.target.is_dir():
        log_path = args.target / "dma_probe_log.txt"
    else:
        log_path = args.target

    result = validate_log(log_path)

    # In strict mode, warnings become errors
    if args.strict and result.warnings:
        result.valid = False
        result.errors.extend([f"(strict) {w}" for w in result.warnings])

    if args.json:
        import json

        output = {
            "valid": result.valid,
            "log_file": result.log_file,
            "header": {
                "version": result.header.version,
                "run_id": result.header.run_id,
                "rom": result.header.rom,
                "sha256": result.header.sha256,
                "prg_size": result.header.prg_size,
            }
            if result.header
            else None,
            "errors": result.errors,
            "warnings": result.warnings,
            "line_counts": result.line_counts,
            "total_lines": result.total_lines,
            "unrecognized_lines": result.unrecognized_lines,
        }
        print(json.dumps(output, indent=2))
    else:
        print_report(result)

    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
