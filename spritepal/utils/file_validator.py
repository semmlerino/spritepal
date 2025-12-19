"""
Comprehensive file validation service for SpritePal.

This service consolidates all file validation logic from across the codebase
into a single, reusable service with detailed error reporting and comprehensive
file type support.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from utils.logging_config import get_logger

logger = get_logger(__name__)

from utils.constants import (
    CGRAM_PATTERNS,
    MAX_TILE_COUNT_DEFAULT,
    OAM_PATTERNS,
    VRAM_PATTERNS,
)


@dataclass
class FileInfo:
    """Information about a validated file"""
    path: str
    size: int
    exists: bool
    is_readable: bool
    extension: str
    resolved_path: str

@dataclass
class ValidationResult:
    """Result of file validation with detailed information"""
    is_valid: bool
    error_message: str | None = None
    warnings: list[str] = field(default_factory=list)
    file_info: FileInfo | None = None

class BasicFileValidator:
    """Handles file existence, permissions, and basic size checks."""

    @staticmethod
    def validate_existence(path: str, file_type: str = "file") -> ValidationResult:
        """
        Validate that a file exists and is accessible.

        Args:
            path: Path to validate
            file_type: Description of file type for error messages

        Returns:
            ValidationResult with existence validation
        """
        if not path:
            return ValidationResult(
                is_valid=False,
                error_message=f"{file_type} path is empty or None"
            )

        if not Path(path).exists():
            return ValidationResult(
                is_valid=False,
                error_message=f"{file_type} does not exist: {path}"
            )

        if not Path(path).is_file():
            return ValidationResult(
                is_valid=False,
                error_message=f"Path is not a file: {path}"
            )

        # Try to access the file
        try:
            with Path(path).open("rb") as f:
                f.read(1)  # Try to read one byte
        except PermissionError:
            return ValidationResult(
                is_valid=False,
                error_message=f"Permission denied reading {file_type}: {path}"
            )
        except OSError as e:
            return ValidationResult(
                is_valid=False,
                error_message=f"Cannot access {file_type}: {e}"
            )

        return ValidationResult(
            is_valid=True,
            file_info=BasicFileValidator.get_file_info(path)
        )

    @staticmethod
    def validate_properties(
        path: str,
        allowed_extensions: set[str] | None = None,
        min_size: int | None = None,
        max_size: int | None = None,
        allow_nonexistent: bool = False,
    ) -> ValidationResult:
        """
        Validate basic file properties (existence, extension, size).

        Args:
            path: File path to validate
            allowed_extensions: Set of allowed extensions (with dots)
            min_size: Minimum file size in bytes
            max_size: Maximum file size in bytes
            allow_nonexistent: If True, non-existent files pass validation
                (for backward compatibility with legacy validation module)

        Returns:
            ValidationResult with basic validation
        """
        # Handle non-existent files early if allowed
        if allow_nonexistent and not Path(path).exists():
            return ValidationResult(is_valid=True)

        # First check existence
        existence_result = BasicFileValidator.validate_existence(path)
        if not existence_result.is_valid:
            return existence_result

        file_info = existence_result.file_info
        if not file_info:
            return ValidationResult(
                is_valid=False,
                error_message="Could not get file information"
            )

        # Check extension if specified
        if allowed_extensions and file_info.extension.lower() not in allowed_extensions:
            return ValidationResult(
                is_valid=False,
                error_message=f"Invalid file extension: {file_info.extension}. Allowed: {sorted(allowed_extensions)}",
                file_info=file_info
            )

        # Check file size constraints
        if min_size is not None and file_info.size < min_size:
            size_desc = BasicFileValidator.format_file_size(file_info.size)
            min_desc = BasicFileValidator.format_file_size(min_size)
            return ValidationResult(
                is_valid=False,
                error_message=f"File too small: {size_desc} (minimum: {min_desc})",
                file_info=file_info
            )

        if max_size is not None and file_info.size > max_size:
            size_desc = BasicFileValidator.format_file_size(file_info.size)
            max_desc = BasicFileValidator.format_file_size(max_size)
            return ValidationResult(
                is_valid=False,
                error_message=f"File too large: {size_desc} (maximum: {max_desc})",
                file_info=file_info
            )

        return ValidationResult(
            is_valid=True,
            file_info=file_info
        )

    @staticmethod
    def get_file_info(path: str) -> FileInfo:
        """
        Get comprehensive file information.

        Args:
            path: File path

        Returns:
            FileInfo object with file details
        """
        try:
            resolved_path = str(Path(path).resolve())
            path_obj = Path(path)
            exists = path_obj.exists()
            size = path_obj.stat().st_size if exists else 0
            extension = Path(path).suffix

            # Test readability
            is_readable = False
            if exists:
                try:
                    with Path(path).open("rb") as f:
                        f.read(1)
                    is_readable = True
                except (PermissionError, OSError):
                    is_readable = False

            return FileInfo(
                path=path,
                size=size,
                exists=exists,
                is_readable=is_readable,
                extension=extension,
                resolved_path=resolved_path
            )
        except Exception:
            # Fallback for invalid paths
            return FileInfo(
                path=path,
                size=0,
                exists=False,
                is_readable=False,
                extension="",
                resolved_path=path
            )

    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """
        Format file size in human-readable format.

        Args:
            size_bytes: Size in bytes

        Returns:
            Formatted size string
        """
        if size_bytes < 1024:
            return f"{size_bytes} bytes"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes // 1024}KB"
        return f"{size_bytes // (1024 * 1024)}MB"

class FormatValidator:
    """Handles format-specific rules for VRAM, CGRAM, OAM, and ROM files."""

    # File size limits
    VRAM_MIN_SIZE = 0x10000  # 64KB minimum
    VRAM_MAX_SIZE = 0x100000  # 1MB maximum
    CGRAM_EXPECTED_SIZE = 512  # Exactly 512 bytes
    OAM_EXPECTED_SIZE = 544  # Exactly 544 bytes
    ROM_MIN_SIZE = 0x80000  # 512KB minimum
    ROM_MAX_SIZE = 0x1000000  # 16MB maximum

    # Valid ROM sizes (excluding SMC header)
    VALID_ROM_SIZES = [
        0x80000, 0x100000, 0x180000, 0x200000,
        0x280000, 0x300000, 0x400000, 0x600000
    ]

    @classmethod
    def validate_vram_format(cls, file_info: FileInfo) -> ValidationResult:
        """
        Validate VRAM-specific format requirements.

        Args:
            file_info: File information from BasicFileValidator

        Returns:
            ValidationResult with format-specific validation
        """
        warnings = []

        # Check size
        if file_info.size < cls.VRAM_MIN_SIZE:
            return ValidationResult(
                is_valid=False,
                error_message=f"VRAM file too small: {file_info.size} bytes",
                file_info=file_info
            )

        if file_info.size > cls.VRAM_MAX_SIZE:
            return ValidationResult(
                is_valid=False,
                error_message=f"VRAM file too large: {file_info.size} bytes",
                file_info=file_info
            )

        # Non-standard size warning
        if file_info.size != cls.VRAM_MIN_SIZE:
            size_kb = file_info.size // 1024
            warnings.append(f"Non-standard VRAM size: {size_kb}KB (expected: 64KB)")

        # Check for common VRAM file patterns
        if not any(pattern.replace("*", "").lower() in file_info.path.lower()
                  for pattern in VRAM_PATTERNS):
            warnings.append("File name doesn't match common VRAM patterns")

        return ValidationResult(
            is_valid=True,
            warnings=warnings,
            file_info=file_info
        )

    @classmethod
    def validate_cgram_format(cls, file_info: FileInfo) -> ValidationResult:
        """
        Validate CGRAM-specific format requirements.

        Args:
            file_info: File information from BasicFileValidator

        Returns:
            ValidationResult with format-specific validation
        """
        # CGRAM requires exact size
        if file_info.size != cls.CGRAM_EXPECTED_SIZE:
            return ValidationResult(
                is_valid=False,
                error_message=f"CGRAM file size invalid ({file_info.size} bytes). Expected exactly {cls.CGRAM_EXPECTED_SIZE} bytes.",
                file_info=file_info
            )

        warnings = []
        # Check for common CGRAM file patterns
        if not any(pattern.replace("*", "").lower() in file_info.path.lower()
                  for pattern in CGRAM_PATTERNS):
            warnings.append("File name doesn't match common CGRAM patterns")

        return ValidationResult(
            is_valid=True,
            warnings=warnings,
            file_info=file_info
        )

    @classmethod
    def validate_oam_format(cls, file_info: FileInfo) -> ValidationResult:
        """
        Validate OAM-specific format requirements.

        Args:
            file_info: File information from BasicFileValidator

        Returns:
            ValidationResult with format-specific validation
        """
        # OAM requires exact size
        if file_info.size != cls.OAM_EXPECTED_SIZE:
            return ValidationResult(
                is_valid=False,
                error_message=f"OAM file size invalid ({file_info.size} bytes). Expected exactly {cls.OAM_EXPECTED_SIZE} bytes.",
                file_info=file_info
            )

        warnings = []
        # Check for common OAM file patterns
        if not any(pattern.replace("*", "").lower() in file_info.path.lower()
                  for pattern in OAM_PATTERNS):
            warnings.append("File name doesn't match common OAM patterns")

        return ValidationResult(
            is_valid=True,
            warnings=warnings,
            file_info=file_info
        )

    @classmethod
    def validate_rom_format(cls, file_info: FileInfo) -> ValidationResult:
        """
        Validate ROM-specific format requirements.

        Args:
            file_info: File information from BasicFileValidator

        Returns:
            ValidationResult with format-specific validation
        """
        warnings = []

        # Check for SMC header
        has_smc_header = file_info.size % 1024 == 512
        if has_smc_header:
            warnings.append("ROM has SMC header (512 bytes) - will be handled automatically")

        # Check ROM size validity
        rom_size = file_info.size - (512 if has_smc_header else 0)
        if rom_size not in cls.VALID_ROM_SIZES:
            warnings.append(f"Non-standard ROM size: {rom_size // 1024}KB")

        return ValidationResult(
            is_valid=True,
            warnings=warnings,
            file_info=file_info
        )

    @staticmethod
    def validate_offset(offset: int, max_offset: int | None = None) -> ValidationResult:
        """
        Validate an offset value.

        Args:
            offset: Offset to validate
            max_offset: Maximum allowed offset (optional)

        Returns:
            ValidationResult with offset validation
        """
        if offset < 0:
            return ValidationResult(
                is_valid=False,
                error_message=f"Offset cannot be negative: {offset}"
            )

        if offset > FormatValidator.ROM_MAX_SIZE:
            return ValidationResult(
                is_valid=False,
                error_message=f"Offset exceeds maximum ROM size (16MB): 0x{offset:06X}"
            )

        if max_offset is not None and offset >= max_offset:
            return ValidationResult(
                is_valid=False,
                error_message=f"Offset 0x{offset:06X} exceeds maximum 0x{max_offset:06X}"
            )

        return ValidationResult(is_valid=True)

    @staticmethod
    def validate_tile_count(
        count: int, max_count: int = MAX_TILE_COUNT_DEFAULT
    ) -> ValidationResult:
        """
        Validate tile count to prevent excessive memory usage.

        Args:
            count: Number of tiles
            max_count: Maximum allowed tiles (default: 8192)

        Returns:
            ValidationResult with tile count validation
        """
        if count < 0:
            return ValidationResult(
                is_valid=False,
                error_message=f"Tile count cannot be negative: {count}"
            )
        if count > max_count:
            return ValidationResult(
                is_valid=False,
                error_message=f"Tile count {count} exceeds maximum: {max_count}"
            )
        return ValidationResult(is_valid=True)

class ContentValidator:
    """Handles content parsing and validation for various file types."""

    @staticmethod
    def validate_json_content(path: str) -> ValidationResult:
        """
        Validate JSON file content by attempting to parse it.

        Args:
            path: Path to JSON file

        Returns:
            ValidationResult with JSON parsing validation
        """
        try:
            with Path(path).open(encoding="utf-8") as f:
                json.load(f)
            return ValidationResult(is_valid=True)
        except json.JSONDecodeError as e:
            return ValidationResult(
                is_valid=False,
                error_message=f"Invalid JSON format: {e}"
            )
        except OSError as e:
            return ValidationResult(
                is_valid=False,
                error_message=f"Cannot read JSON file: {e}"
            )

    @staticmethod
    def validate_vram_header(path: str) -> ValidationResult:
        """
        Validate VRAM file header by reading first 16 bytes.

        Args:
            path: Path to VRAM file

        Returns:
            ValidationResult with header validation
        """
        try:
            with Path(path).open("rb") as f:
                header = f.read(16)
                if len(header) < 16:
                    return ValidationResult(
                        is_valid=False,
                        error_message="VRAM file appears corrupted or truncated"
                    )
            return ValidationResult(is_valid=True)
        except OSError as e:
            return ValidationResult(
                is_valid=False,
                error_message=f"Cannot read VRAM file: {e}"
            )

class FileValidator:
    """
    Comprehensive file validation service for all SpritePal file types.

    This facade coordinates BasicFileValidator, FormatValidator, and ContentValidator
    to provide comprehensive file validation while maintaining backward compatibility.
    """

    # File extensions
    VRAM_EXTENSIONS: ClassVar[set[str]] = {".dmp", ".bin", ".vram"}
    CGRAM_EXTENSIONS: ClassVar[set[str]] = {".dmp", ".bin", ".cgram", ".pal"}
    OAM_EXTENSIONS: ClassVar[set[str]] = {".dmp", ".bin", ".oam"}
    ROM_EXTENSIONS: ClassVar[set[str]] = {".smc", ".sfc", ".bin"}
    IMAGE_EXTENSIONS: ClassVar[set[str]] = {".png"}
    JSON_EXTENSIONS: ClassVar[set[str]] = {".json"}

    # File size limits (for backward compatibility)
    IMAGE_MAX_SIZE: ClassVar[int] = 10 * 1024 * 1024  # 10MB maximum
    JSON_MAX_SIZE: ClassVar[int] = 1 * 1024 * 1024  # 1MB maximum

    def __init__(self):
        """Initialize the facade with validator components."""
        self.basic = BasicFileValidator()
        self.format = FormatValidator()
        self.content = ContentValidator()

    @classmethod
    def validate_vram_file(
        cls, path: str, allow_nonexistent: bool = False
    ) -> ValidationResult:
        """
        Validate VRAM dump file with comprehensive checks.

        Args:
            path: Path to VRAM file
            allow_nonexistent: If True, non-existent files pass validation

        Returns:
            ValidationResult with detailed validation information
        """
        # Basic file validation first
        basic_result = BasicFileValidator.validate_properties(
            path,
            cls.VRAM_EXTENSIONS,
            FormatValidator.VRAM_MIN_SIZE,
            FormatValidator.VRAM_MAX_SIZE,
            allow_nonexistent=allow_nonexistent,
        )

        if not basic_result.is_valid:
            return basic_result

        # If file doesn't exist and that's allowed, skip further validation
        if not basic_result.file_info:
            return basic_result

        # Format-specific validation
        format_result = FormatValidator.validate_vram_format(basic_result.file_info)
        if not format_result.is_valid:
            return format_result

        # Merge warnings
        basic_result.warnings.extend(format_result.warnings)

        # Content validation - check header
        content_result = ContentValidator.validate_vram_header(path)
        if not content_result.is_valid:
            content_result.file_info = basic_result.file_info
            return content_result

        return basic_result

    @classmethod
    def validate_cgram_file(
        cls, path: str, allow_nonexistent: bool = False
    ) -> ValidationResult:
        """
        Validate CGRAM dump file with size requirements.

        Args:
            path: Path to CGRAM file
            allow_nonexistent: If True, non-existent files pass validation

        Returns:
            ValidationResult with detailed validation information
        """
        # Basic file validation
        basic_result = BasicFileValidator.validate_properties(
            path,
            cls.CGRAM_EXTENSIONS,
            FormatValidator.CGRAM_EXPECTED_SIZE,
            FormatValidator.CGRAM_EXPECTED_SIZE,
            allow_nonexistent=allow_nonexistent,
        )

        if not basic_result.is_valid:
            return basic_result

        # If file doesn't exist and that's allowed, skip further validation
        if not basic_result.file_info:
            return basic_result

        # Format-specific validation
        format_result = FormatValidator.validate_cgram_format(basic_result.file_info)
        if not format_result.is_valid:
            return format_result

        # Merge warnings
        basic_result.warnings.extend(format_result.warnings)

        return basic_result

    @classmethod
    def validate_oam_file(
        cls, path: str, allow_nonexistent: bool = False
    ) -> ValidationResult:
        """
        Validate OAM dump file with size requirements.

        Args:
            path: Path to OAM file
            allow_nonexistent: If True, non-existent files pass validation

        Returns:
            ValidationResult with detailed validation information
        """
        # Basic file validation
        basic_result = BasicFileValidator.validate_properties(
            path,
            cls.OAM_EXTENSIONS,
            FormatValidator.OAM_EXPECTED_SIZE,
            FormatValidator.OAM_EXPECTED_SIZE,
            allow_nonexistent=allow_nonexistent,
        )

        if not basic_result.is_valid:
            return basic_result

        # If file doesn't exist and that's allowed, skip further validation
        if not basic_result.file_info:
            return basic_result

        # Format-specific validation
        format_result = FormatValidator.validate_oam_format(basic_result.file_info)
        if not format_result.is_valid:
            return format_result

        # Merge warnings
        basic_result.warnings.extend(format_result.warnings)

        return basic_result

    @classmethod
    def validate_rom_file(
        cls, path: str, allow_nonexistent: bool = False
    ) -> ValidationResult:
        """
        Validate ROM file with comprehensive checks.

        Args:
            path: Path to ROM file
            allow_nonexistent: If True, non-existent files pass validation

        Returns:
            ValidationResult with detailed validation information
        """
        # Basic file validation
        basic_result = BasicFileValidator.validate_properties(
            path,
            cls.ROM_EXTENSIONS,
            FormatValidator.ROM_MIN_SIZE,
            FormatValidator.ROM_MAX_SIZE,
            allow_nonexistent=allow_nonexistent,
        )

        if not basic_result.is_valid:
            return basic_result

        # If file doesn't exist and that's allowed, skip further validation
        if not basic_result.file_info:
            return basic_result

        # Format-specific validation
        format_result = FormatValidator.validate_rom_format(basic_result.file_info)
        if not format_result.is_valid:
            return format_result

        # Merge warnings
        basic_result.warnings.extend(format_result.warnings)

        return basic_result

    @classmethod
    def validate_image_file(
        cls, path: str, allow_nonexistent: bool = False
    ) -> ValidationResult:
        """
        Validate image file (PNG) with size limits.

        Args:
            path: Path to image file
            allow_nonexistent: If True, non-existent files pass validation

        Returns:
            ValidationResult with detailed validation information
        """
        return BasicFileValidator.validate_properties(
            path, cls.IMAGE_EXTENSIONS, None, cls.IMAGE_MAX_SIZE,
            allow_nonexistent=allow_nonexistent,
        )

    @classmethod
    def validate_json_file(
        cls, path: str, allow_nonexistent: bool = False
    ) -> ValidationResult:
        """
        Validate JSON file with size limits and basic JSON validation.

        Args:
            path: Path to JSON file
            allow_nonexistent: If True, non-existent files pass validation

        Returns:
            ValidationResult with detailed validation information
        """
        # Basic file validation
        basic_result = BasicFileValidator.validate_properties(
            path, cls.JSON_EXTENSIONS, None, cls.JSON_MAX_SIZE,
            allow_nonexistent=allow_nonexistent,
        )

        if not basic_result.is_valid:
            return basic_result

        # If file doesn't exist and that's allowed, skip further validation
        if not basic_result.file_info:
            return basic_result

        # Content validation - parse JSON
        content_result = ContentValidator.validate_json_content(path)
        if not content_result.is_valid:
            content_result.file_info = basic_result.file_info
            return content_result

        return basic_result

    @classmethod
    def validate_file_existence(cls, path: str, file_type: str = "file") -> ValidationResult:
        """
        Validate that a file exists and is accessible.

        Args:
            path: Path to validate
            file_type: Description of file type for error messages

        Returns:
            ValidationResult with existence validation
        """
        return BasicFileValidator.validate_existence(path, file_type)

    @classmethod
    def validate_offset(cls, offset: int, max_offset: int | None = None) -> ValidationResult:
        """
        Validate an offset value.

        Args:
            offset: Offset to validate
            max_offset: Maximum allowed offset (optional)

        Returns:
            ValidationResult with offset validation
        """
        return FormatValidator.validate_offset(offset, max_offset)

    # Backward compatibility methods
    @classmethod
    def _validate_basic_file_properties(
        cls,
        path: str,
        allowed_extensions: set[str] | None = None,
        min_size: int | None = None,
        max_size: int | None = None
    ) -> ValidationResult:
        """Backward compatibility wrapper for basic file validation."""
        return BasicFileValidator.validate_properties(
            path, allowed_extensions, min_size, max_size
        )

    @classmethod
    def _get_file_info(cls, path: str) -> FileInfo:
        """Backward compatibility wrapper for file info retrieval."""
        return BasicFileValidator.get_file_info(path)

    @classmethod
    def _format_file_size(cls, size_bytes: int) -> str:
        """Backward compatibility wrapper for file size formatting."""
        return BasicFileValidator.format_file_size(size_bytes)


def atomic_write(path: Path | str, data: bytes) -> None:
    """
    Write data atomically using temp file + rename pattern.

    This ensures that if the write is interrupted (power failure, crash,
    disk full), the original file is not corrupted. The rename operation
    is atomic on POSIX systems.

    Args:
        path: Destination file path
        data: Binary data to write

    Raises:
        OSError: If the write fails
        IOError: If the data cannot be written completely
    """
    path = Path(path)
    parent_dir = path.parent

    # Ensure parent directory exists
    parent_dir.mkdir(parents=True, exist_ok=True)

    # Create temp file in same directory (required for atomic rename)
    temp_fd, temp_path_str = tempfile.mkstemp(
        dir=parent_dir,
        prefix=f".{path.name}.",
        suffix=".tmp"
    )
    temp_path = Path(temp_path_str)

    try:
        # Write data with explicit flush and sync
        with os.fdopen(temp_fd, 'wb') as f:
            bytes_written = f.write(data)
            if bytes_written != len(data):
                raise OSError(
                    f"Incomplete write: {bytes_written}/{len(data)} bytes"
                )
            f.flush()
            os.fsync(f.fileno())

        # Atomic rename (on POSIX; on Windows this may not be truly atomic)
        temp_path.replace(path)
        logger.debug(f"Atomically wrote {len(data)} bytes to {path}")

    except Exception:
        # Clean up temp file on any failure
        temp_path.unlink(missing_ok=True)
        raise


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename for safe file operations.
    
    Removes directory traversal attempts and invalid characters.
    
    Args:
        filename: The filename to sanitize
        
    Returns:
        A safe filename with invalid characters replaced
    """
    # Remove directory separators - use Path.name to get just the filename
    filename = Path(filename).name

    # Remove potentially dangerous characters
    invalid_chars = '<>:"|?*\x00'
    for char in invalid_chars:
        filename = filename.replace(char, "_")

    # Remove leading/trailing dots and spaces
    filename = filename.strip(". ")

    # Ensure filename is not empty
    if not filename:
        filename = "unnamed"

    return filename
