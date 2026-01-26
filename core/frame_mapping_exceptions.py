"""Domain exceptions for frame mapping operations.

Provides specific exception types for frame mapping errors, enabling
precise error handling and meaningful error messages throughout the
codebase.

P0-2: Replace generic exception handling with domain-specific exceptions.
"""

from __future__ import annotations


class FrameMappingError(Exception):
    """Base exception for frame mapping operations.

    All frame mapping-specific exceptions inherit from this class,
    allowing callers to catch all frame mapping errors with a single
    except clause when appropriate.
    """

    pass


class MappingError(FrameMappingError):
    """Error during mapping creation or update.

    Raised when:
    - Creating a mapping with invalid frame IDs
    - Updating a mapping that doesn't exist
    - Attempting operations on unmapped frames
    """

    pass


class InjectionError(FrameMappingError):
    """Error during frame injection into ROM.

    Raised when:
    - ROM file cannot be read or written
    - Tile extraction fails
    - Compression fails
    - ROM offset verification fails
    """

    pass


class CaptureParseError(FrameMappingError):
    """Error parsing Mesen capture file.

    Raised when:
    - Capture file is malformed JSON
    - Required fields are missing
    - Entry data is invalid
    """

    pass


class ProjectError(FrameMappingError):
    """Error with project file operations.

    Raised when:
    - Project file cannot be read or written
    - Project version is unsupported
    - Project data is corrupted or invalid
    """

    pass


class StaleEntriesError(FrameMappingError):
    """Stored entry IDs no longer exist in capture file.

    Raised when:
    - Capture file was re-recorded with different entry IDs
    - Game frame's selected_entry_ids don't match current capture

    Contains the frame_id for recovery/fallback decisions.
    """

    def __init__(self, message: str, frame_id: str) -> None:
        super().__init__(message)
        self.frame_id = frame_id


class PaletteError(FrameMappingError):
    """Error with palette operations.

    Raised when:
    - Palette extraction fails
    - Color quantization produces invalid results
    - Palette index is out of bounds
    """

    pass
