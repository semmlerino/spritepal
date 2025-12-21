"""
Type guards for runtime type checking and narrowing.

This module provides TypeGuard functions that help the type checker
understand runtime type checks, enabling safer type narrowing and
better error detection.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, TypeGuard, TypeVar

if TYPE_CHECKING:
    from pathlib import Path

    from PySide6.QtCore import QObject

    from core.managers.base_manager import BaseManager
    from core.types import ROMExtractionParams

# Type variable for manager type guards
T = TypeVar('T', bound='BaseManager')

def is_valid_rom_path(path: object) -> TypeGuard[str]:
    """
    Type guard to check if a path is a valid ROM file path.

    Args:
        path: Object to check

    Returns:
        True if path is a valid ROM file path string
    """
    return (
        isinstance(path, str)
        and len(path) > 0
        and (path.endswith('.sfc') or path.endswith('.smc'))
    )

def is_valid_offset(value: object) -> TypeGuard[int]:
    """
    Type guard to check if a value is a valid ROM offset.

    Args:
        value: Object to check

    Returns:
        True if value is a valid offset (non-negative integer within ROM range)
    """
    return (
        isinstance(value, int)
        and 0 <= value <= 0x800000  # 8MB max ROM size
        and value == int(value)     # Ensure no precision loss
    )

def is_manager_instance(obj: object, manager_type: type[T]) -> TypeGuard[T]:
    """
    Type guard to check if an object is a specific manager type.

    Args:
        obj: Object to check
        manager_type: Expected manager class

    Returns:
        True if obj is an instance of the manager type with required methods
    """
    return (
        isinstance(obj, manager_type)
        and hasattr(obj, 'cleanup')
        and callable(obj.cleanup)
    )

def is_qobject_with_parent(obj: object) -> TypeGuard[QObject]:
    """
    Type guard to check if an object is a QObject that can have parent set.

    Args:
        obj: Object to check

    Returns:
        True if obj is a QObject with setParent method
    """
    try:
        from PySide6.QtCore import QObject
        return (
            isinstance(obj, QObject)
            and hasattr(obj, 'setParent')
            and callable(obj.setParent)
        )
    except ImportError:
        return False

def is_complete_extraction_params(params: dict[str, object]) -> TypeGuard[ROMExtractionParams]:
    """
    Type guard to check if a dict contains complete ROM extraction parameters.

    Args:
        params: Dictionary to check

    Returns:
        True if params contains all required extraction parameters
    """
    required_keys = {'rom_path', 'sprite_offset', 'output_base', 'sprite_name'}
    return (
        all(key in params for key in required_keys)
        and is_valid_rom_path(params.get('rom_path'))
        and is_valid_offset(params.get('sprite_offset'))
        and isinstance(params.get('output_base'), str)
        and isinstance(params.get('sprite_name'), str)
    )

def is_path_like(obj: object) -> TypeGuard[str | Path]:
    """
    Type guard to check if an object is path-like.

    Args:
        obj: Object to check

    Returns:
        True if obj is a string or Path object
    """
    if isinstance(obj, str):
        return True

    try:
        from pathlib import Path
        return isinstance(obj, Path)
    except ImportError:
        return False

def safe_int_conversion(value: object, base: int = 10) -> int | None:
    """
    Safely convert various types to integer with validation.

    Args:
        value: Value to convert
        base: Numeric base (10 for decimal, 16 for hex)

    Returns:
        Converted integer or None if conversion fails
    """
    try:
        if isinstance(value, str):
            # Handle hex strings
            if value.startswith(('0x', '0X')):
                return int(value, 16)
            return int(value, base)
        if isinstance(value, (int, float)):
            # Ensure no precision loss for large numbers
            result = int(value)
            if result != value:
                # Float has fractional part
                return None
            return result
        return None
    except (ValueError, TypeError, OverflowError):
        return None

def cpu_to_rom_offset(cpu_addr: int) -> int | None:
    """
    Convert SNES CPU address to ROM file offset with type safety.

    This function replicates the Lua script logic with proper type checking
    and validation to prevent integer overflow/underflow issues.

    Args:
        cpu_addr: 24-bit SNES CPU address

    Returns:
        ROM file offset or None if address is not mappable

    Raises:
        ValueError: If cpu_addr is not a valid 24-bit address
    """
    if not (0 <= cpu_addr <= 0xFFFFFF):  # 24-bit address space
        raise ValueError(f"cpu_addr must be 24-bit (0x000000-0xFFFFFF), got 0x{cpu_addr:X}")

    # Extract bank and address components with proper masking
    bank = (cpu_addr >> 16) & 0xFF  # Upper 8 bits
    addr = cpu_addr & 0xFFFF        # Lower 16 bits

    # Check for invalid address ranges
    if addr < 0x8000:
        return None  # Low RAM/registers, not ROM

    if bank in (0x7E, 0x7F):
        return None  # Extended RAM, not ROM

    # Convert LoROM mapping to ROM offset
    if bank >= 0x80:
        # Ensure arithmetic stays within bounds
        rom_bank = bank & 0x7F  # Remove mirror bit
        rom_offset_base = rom_bank * 0x8000
        addr_offset = addr - 0x8000

        # Check for potential overflow
        if rom_offset_base > 0x800000 - addr_offset:
            return None  # Would exceed maximum ROM size

        rom_offset = rom_offset_base + addr_offset

        # Final validation
        if not is_valid_offset(rom_offset):
            return None

        return rom_offset

    return None

def clamp_to_slider_range(offset: int) -> int:
    """
    Clamp ROM offset to QSlider-compatible range.

    QSlider uses 32-bit signed integers, so we must ensure
    offsets don't exceed this limit.

    Args:
        offset: ROM offset to clamp

    Returns:
        Offset clamped to QSlider range (0 to 2^31-1)
    """
    return max(0, min(offset, 0x7FFFFFFF))
