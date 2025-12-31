#!/usr/bin/env python3
"""
Migrate sprite extraction pipeline JSON files from schema v1 to v2.

Schema v2 changes:
- oam_base_addr → obj_tile_base_word (VRAM address, not OAM)
- oam_addr_offset → obj_tile_offset_word (VRAM address, not OAM)
- confidence → observation_count (avoid statistics confusion)
- Adds schema_version field

Usage:
    python scripts/migrate_v1_to_v2.py mesen2_exchange/
    python scripts/migrate_v1_to_v2.py mesen2_exchange/tile_hash_database.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

FIELD_RENAMES: dict[str, str] = {
    "oam_base_addr": "obj_tile_base_word",
    "oam_addr_offset": "obj_tile_offset_word",
    "confidence": "observation_count",
}

# Also rename in nested structures
NESTED_FIELD_RENAMES: dict[str, str] = {
    "oam_base_addr": "obj_tile_base_word",
    "oam_addr_offset": "obj_tile_offset_word",
}


def rename_fields(obj: Any, renames: dict[str, str]) -> Any:
    """Recursively rename fields in a JSON structure."""
    if isinstance(obj, dict):
        return {
            renames.get(k, k): rename_fields(v, renames)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [rename_fields(item, renames) for item in obj]
    else:
        return obj


def get_schema_version(data: dict[str, Any]) -> int:
    """Extract schema version from data, defaulting to 1."""
    return data.get("schema_version", 1)


def migrate_file(input_path: Path, dry_run: bool = False) -> tuple[bool, str]:
    """
    Migrate a single JSON file from v1 to v2.

    Returns:
        (success, message) tuple
    """
    try:
        with open(input_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return False, f"JSON parse error: {e}"
    except OSError as e:
        return False, f"Read error: {e}"

    # Check if already migrated
    version = get_schema_version(data)
    if version >= 2:
        return True, f"Already v{version}, skipping"

    # Perform migration
    migrated = rename_fields(data, FIELD_RENAMES)
    migrated["schema_version"] = 2

    if dry_run:
        return True, "Would migrate (dry-run)"

    # Write back in-place
    try:
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(migrated, f, indent=2)
    except OSError as e:
        return False, f"Write error: {e}"

    return True, "Migrated v1 → v2"


def find_json_files(target: Path) -> list[Path]:
    """Find all JSON files in the target path."""
    if target.is_file():
        return [target] if target.suffix == ".json" else []
    elif target.is_dir():
        return list(target.glob("**/*.json"))
    else:
        return []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate sprite extraction JSON files from schema v1 to v2."
    )
    parser.add_argument(
        "target",
        type=Path,
        help="File or directory to migrate",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show all files, not just those modified",
    )

    args = parser.parse_args()

    if not args.target.exists():
        print(f"ERROR: Target not found: {args.target}", file=sys.stderr)
        return 1

    files = find_json_files(args.target)
    if not files:
        print(f"No JSON files found in {args.target}")
        return 0

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Processing {len(files)} JSON file(s)...")
    print()

    migrated_count = 0
    error_count = 0
    skipped_count = 0

    for path in sorted(files):
        success, message = migrate_file(path, dry_run=args.dry_run)

        if not success:
            print(f"ERROR: {path.name}: {message}")
            error_count += 1
        elif "Migrated" in message or "Would migrate" in message:
            print(f"✓ {path.name}: {message}")
            migrated_count += 1
        else:
            if args.verbose:
                print(f"- {path.name}: {message}")
            skipped_count += 1

    print()
    print(f"Summary: {migrated_count} migrated, {skipped_count} skipped, {error_count} errors")

    if args.dry_run and migrated_count > 0:
        print()
        print("Run without --dry-run to apply changes.")

    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
