"""
Dump file detection functions for VRAM, CGRAM, and OAM files.

Provides auto-detection of related dump files using pattern matching.
When one dump file is loaded (e.g., VRAM), this service finds related files
(CGRAM, OAM) in the same directory using common naming conventions.

This module uses pure functions instead of a stateless service class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from utils.logging_config import get_logger

logger = get_logger(__name__)


# Common suffixes to strip when extracting base name
DUMP_SUFFIXES = [
    "_VRAM",
    "_CGRAM",
    "_OAM",
    ".SnesVideoRam",
    ".SnesCgRam",
    ".SnesSpriteRam",
    ".VRAM",
    ".CGRAM",
    ".OAM",
]


@dataclass
class DetectedFiles:
    """Results from file detection.

    Attributes:
        vram_path: Path to VRAM dump file, or None if not found
        cgram_path: Path to CGRAM dump file, or None if not found
        oam_path: Path to OAM dump file, or None if not found
    """

    vram_path: Path | None = None
    cgram_path: Path | None = None
    oam_path: Path | None = None

    def has_any(self) -> bool:
        """Check if any files were detected."""
        return any([self.vram_path, self.cgram_path, self.oam_path])

    def merge(self, other: DetectedFiles) -> DetectedFiles:
        """Merge with another DetectedFiles, preferring existing values."""
        return DetectedFiles(
            vram_path=self.vram_path or other.vram_path,
            cgram_path=self.cgram_path or other.cgram_path,
            oam_path=self.oam_path or other.oam_path,
        )


@dataclass
class FileTypeConfig:
    """Configuration for a file type to detect.

    Attributes:
        file_type: Type identifier ("vram", "cgram", "oam")
        exact_patterns: Patterns using base name (e.g., "{base}_VRAM.dmp")
        glob_patterns: Glob patterns for directory scanning (e.g., "*VRAM*.dmp")
    """

    file_type: str
    exact_patterns: list[str] = field(default_factory=list)
    glob_patterns: list[str] = field(default_factory=list)


# File type configurations
VRAM_CONFIG = FileTypeConfig(
    file_type="vram",
    exact_patterns=[
        "{base}_VRAM.dmp",
        "{base}.SnesVideoRam.dmp",
        "{base}.VRAM.dmp",
    ],
    glob_patterns=["*VRAM*.dmp", "*VideoRam*.dmp"],
)

CGRAM_CONFIG = FileTypeConfig(
    file_type="cgram",
    exact_patterns=[
        "{base}_CGRAM.dmp",
        "{base}.SnesCgRam.dmp",
        "{base}.CGRAM.dmp",
    ],
    glob_patterns=["*CGRAM*.dmp", "*CgRam*.dmp"],
)

OAM_CONFIG = FileTypeConfig(
    file_type="oam",
    exact_patterns=[
        "{base}_OAM.dmp",
        "{base}.SnesSpriteRam.dmp",
        "{base}.OAM.dmp",
    ],
    glob_patterns=["*OAM*.dmp", "*SpriteRam*.dmp"],
)

ALL_CONFIGS = [VRAM_CONFIG, CGRAM_CONFIG, OAM_CONFIG]


def get_base_name(file_path: Path) -> str:
    """Extract base name by stripping common dump file suffixes.

    Args:
        file_path: Path to a dump file

    Returns:
        Base name without dump-specific suffixes

    Examples:
        >>> get_base_name(Path("game_VRAM.dmp"))
        'game'
        >>> get_base_name(Path("savestate.SnesVideoRam.dmp"))
        'savestate'
    """
    base_name = file_path.stem

    for suffix in DUMP_SUFFIXES:
        if base_name.endswith(suffix):
            return base_name[: -len(suffix)]

    return base_name


def find_file_by_patterns(
    directory: Path,
    base_name: str,
    patterns: list[str],
) -> Path | None:
    """Find a file matching one of the exact patterns.

    Args:
        directory: Directory to search in
        base_name: Base name to use in pattern substitution
        patterns: List of patterns with {base} placeholder

    Returns:
        Path to matching file, or None if not found
    """
    for pattern in patterns:
        filename = pattern.format(base=base_name)
        candidate = directory / filename
        if candidate.exists():
            logger.debug(f"Found file by pattern: {candidate}")
            return candidate
    return None


def find_file_by_glob(
    directory: Path,
    glob_patterns: list[str],
) -> Path | None:
    """Find a file matching one of the glob patterns.

    Args:
        directory: Directory to search in
        glob_patterns: List of glob patterns to try

    Returns:
        Path to first matching file, or None if not found
    """
    for pattern in glob_patterns:
        matches = list(directory.glob(pattern))
        if matches:
            logger.debug(f"Found file by glob {pattern}: {matches[0]}")
            return matches[0]
    return None


def detect_related_files(
    file_path: Path,
    existing: DetectedFiles | None = None,
) -> DetectedFiles:
    """Find related dump files from one loaded file.

    Given a path to one dump file (e.g., VRAM), attempts to find
    related files (CGRAM, OAM) in the same directory using pattern matching.

    Args:
        file_path: Path to a loaded dump file
        existing: Already-loaded files to skip

    Returns:
        DetectedFiles with paths to any found related files

    Example:
        >>> detect_related_files(Path("/dumps/game_VRAM.dmp"))
        DetectedFiles(vram_path=None, cgram_path=Path('/dumps/game_CGRAM.dmp'), ...)
    """
    existing = existing or DetectedFiles()
    result = DetectedFiles()

    directory = file_path.parent
    base_name = get_base_name(file_path)

    logger.debug(f"Detecting related files for base name: {base_name}")

    # Try to find each file type
    for config in ALL_CONFIGS:
        # Skip if already loaded
        if config.file_type == "vram" and existing.vram_path:
            continue
        if config.file_type == "cgram" and existing.cgram_path:
            continue
        if config.file_type == "oam" and existing.oam_path:
            continue

        # Try exact pattern matching first
        found = find_file_by_patterns(directory, base_name, config.exact_patterns)

        if found:
            if config.file_type == "vram":
                result.vram_path = found
            elif config.file_type == "cgram":
                result.cgram_path = found
            elif config.file_type == "oam":
                result.oam_path = found

    return result


def scan_directory_for_dumps(
    directory: Path,
    existing: DetectedFiles | None = None,
) -> DetectedFiles:
    """Scan a directory for dump files using glob patterns.

    Less precise than detect_related_files but finds files even without
    a base name reference.

    Args:
        directory: Directory to scan
        existing: Already-loaded files to skip

    Returns:
        DetectedFiles with paths to any found files
    """
    existing = existing or DetectedFiles()
    result = DetectedFiles()

    if not directory.exists():
        return result

    logger.debug(f"Scanning directory for dumps: {directory}")

    for config in ALL_CONFIGS:
        # Skip if already loaded
        if config.file_type == "vram" and existing.vram_path:
            continue
        if config.file_type == "cgram" and existing.cgram_path:
            continue
        if config.file_type == "oam" and existing.oam_path:
            continue

        found = find_file_by_glob(directory, config.glob_patterns)

        if found:
            if config.file_type == "vram":
                result.vram_path = found
            elif config.file_type == "cgram":
                result.cgram_path = found
            elif config.file_type == "oam":
                result.oam_path = found

    return result


def find_dumps_from_directories(
    directories: list[Path],
    existing: DetectedFiles | None = None,
) -> DetectedFiles:
    """Try multiple directories in order, stopping when files found.

    Searches directories in priority order. Stops searching once any
    dump files are found in a directory.

    Args:
        directories: List of directories to search, in priority order
        existing: Already-loaded files to skip

    Returns:
        DetectedFiles with paths to any found files
    """
    existing = existing or DetectedFiles()

    for directory in directories:
        if not directory or not directory.exists():
            continue

        result = scan_directory_for_dumps(directory, existing)
        if result.has_any():
            logger.debug(f"Found dumps in directory: {directory}")
            return result

    return DetectedFiles()


def auto_detect_all(
    trigger_file: Path | None = None,
    search_directories: list[Path] | None = None,
    existing: DetectedFiles | None = None,
) -> DetectedFiles:
    """Auto-detect dump files using both related file detection and directory scanning.

    Combines both strategies:
    1. If trigger_file is provided, find related files by pattern
    2. If search_directories are provided, scan them in order

    Args:
        trigger_file: A file that was just loaded, to find related files
        search_directories: Directories to scan in priority order
        existing: Already-loaded files to skip

    Returns:
        DetectedFiles with paths to any found files
    """
    existing = existing or DetectedFiles()
    result = DetectedFiles()

    # Strategy 1: Related file detection
    if trigger_file and trigger_file.exists():
        result = detect_related_files(trigger_file, existing)

    # Strategy 2: Directory scanning
    if search_directories:
        # Merge existing with any found so far
        combined_existing = existing.merge(result)
        dir_result = find_dumps_from_directories(search_directories, combined_existing)
        result = result.merge(dir_result)

    return result
