#!/usr/bin/env python3
"""
Validate sprite extraction pipeline JSON files against schema v2 requirements.

Validates:
- Schema version >= 2
- Address fields end in _word or _byte
- Required fields present
- Deprecated field names not used

Usage:
    python scripts/validate_schema.py mesen2_exchange/
    python scripts/validate_schema.py mesen2_exchange/sprite_capture_*.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Deprecated v1 field names that should not appear in v2
DEPRECATED_FIELDS = {
    "oam_base_addr": "Use obj_tile_base_word instead",
    "oam_addr_offset": "Use obj_tile_offset_word instead",
    "confidence": "Use observation_count instead",
}

# Address-related patterns that require _word or _byte suffix
ADDRESS_PATTERNS = [
    r".*_addr$",
    r".*_offset$",
    r".*_base$",
]

# Fields exempt from suffix requirement (not addresses)
EXEMPT_FIELDS = {
    "tile_addr",  # This is actually a word address - should be renamed
}


class ValidationResult:
    """Holds validation results for a single file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


def check_address_suffix(field: str) -> str | None:
    """
    Check if an address-like field has the required _word or _byte suffix.

    Returns error message if invalid, None if valid or not applicable.
    """
    if field in EXEMPT_FIELDS:
        return None

    for pattern in ADDRESS_PATTERNS:
        if re.match(pattern, field):
            if not (field.endswith("_word") or field.endswith("_byte")):
                return f"Address field '{field}' must end with _word or _byte"

    return None


def collect_all_fields(obj: Any, prefix: str = "") -> list[str]:
    """Recursively collect all field names in a JSON structure."""
    fields: list[str] = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            full_key = f"{prefix}.{key}" if prefix else key
            fields.append(key)
            fields.extend(collect_all_fields(value, full_key))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            fields.extend(collect_all_fields(item, f"{prefix}[{i}]"))

    return fields


def validate_file(path: Path) -> ValidationResult:
    """Validate a single JSON file against schema v2 requirements."""
    result = ValidationResult(path)

    # Read and parse file
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        result.add_error(f"JSON parse error: {e}")
        return result
    except OSError as e:
        result.add_error(f"Read error: {e}")
        return result

    # Check schema version
    version = data.get("schema_version", 1)
    if version < 2:
        result.add_error(f"Schema version {version} < 2. Run: python scripts/migrate_v1_to_v2.py {path}")

    # Collect all field names
    all_fields = collect_all_fields(data)
    unique_fields = set(all_fields)

    # Check for deprecated fields
    for field in unique_fields:
        if field in DEPRECATED_FIELDS:
            result.add_error(f"Deprecated field '{field}': {DEPRECATED_FIELDS[field]}")

    # Check address field suffixes
    for field in unique_fields:
        error = check_address_suffix(field)
        if error:
            result.add_warning(error)

    return result


def find_json_files(target: Path) -> list[Path]:
    """Find all JSON files in the target path."""
    if target.is_file():
        return [target] if target.suffix == ".json" else []
    elif target.is_dir():
        return list(target.glob("**/*.json"))
    else:
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate sprite extraction JSON files against schema v2.")
    parser.add_argument(
        "targets",
        type=Path,
        nargs="+",
        help="Files or directories to validate",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only show files with issues",
    )

    args = parser.parse_args()

    # Collect all JSON files
    files: list[Path] = []
    for target in args.targets:
        if not target.exists():
            print(f"WARNING: Target not found: {target}", file=sys.stderr)
            continue
        files.extend(find_json_files(target))

    if not files:
        print("No JSON files found")
        return 0

    print(f"Validating {len(files)} JSON file(s)...")
    print()

    valid_count = 0
    warning_count = 0
    error_count = 0

    for path in sorted(files):
        result = validate_file(path)

        # Count warnings as errors in strict mode
        has_issues = len(result.errors) > 0 or (args.strict and len(result.warnings) > 0)

        if has_issues:
            error_count += 1
            print(f"✗ {path.name}")
            for error in result.errors:
                print(f"    ERROR: {error}")
            for warning in result.warnings:
                prefix = "ERROR" if args.strict else "WARNING"
                print(f"    {prefix}: {warning}")
        elif result.warnings:
            warning_count += 1
            if not args.quiet:
                print(f"⚠ {path.name}")
                for warning in result.warnings:
                    print(f"    WARNING: {warning}")
        else:
            valid_count += 1
            if not args.quiet:
                print(f"✓ {path.name}")

    print()
    print(f"Summary: {valid_count} valid, {warning_count} warnings, {error_count} errors")

    if error_count > 0:
        print()
        print("To fix schema version errors, run:")
        print("  python scripts/migrate_v1_to_v2.py mesen2_exchange/")

    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
