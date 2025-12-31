"""
Validation utilities for parameter and component validation.

These functions provide common validation patterns used throughout
the codebase. They were extracted from BaseManager to enable reuse
without requiring inheritance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from core.exceptions import ValidationError

if TYPE_CHECKING:
    from collections.abc import Mapping


T = TypeVar("T")


def validate_required_params(params: Mapping[str, object], required: list[str]) -> None:
    """
    Validate that required parameters are present and not None.

    Args:
        params: Parameters to validate
        required: List of required parameter names

    Raises:
        ValidationError: If required parameters are missing or None
    """
    missing = [key for key in required if key not in params or params[key] is None]
    if missing:
        raise ValidationError(f"Missing required parameters: {', '.join(missing)}")


def validate_type(value: object, name: str, expected_type: type[object]) -> None:
    """
    Validate that a value has the expected type.

    Args:
        value: Value to validate
        name: Parameter name for error messages
        expected_type: Expected type

    Raises:
        ValidationError: If type doesn't match
    """
    if not isinstance(value, expected_type):
        raise ValidationError(
            f"Invalid type for '{name}': expected {expected_type.__name__}, got {type(value).__name__}"
        )


def validate_range(
    value: int | float,
    name: str,
    min_val: int | float | None = None,
    max_val: int | float | None = None,
) -> None:
    """
    Validate that a numeric value is within the specified range.

    Args:
        value: Value to validate
        name: Parameter name for error messages
        min_val: Minimum allowed value (inclusive), or None for no minimum
        max_val: Maximum allowed value (inclusive), or None for no maximum

    Raises:
        ValidationError: If value is out of range
    """
    if min_val is not None and value < min_val:
        raise ValidationError(f"{name} must be >= {min_val}, got {value}")
    if max_val is not None and value > max_val:
        raise ValidationError(f"{name} must be <= {max_val}, got {value}")


def ensure_component(
    component: T | None,
    name: str,
    error_type: type[Exception] = RuntimeError,
) -> T:
    """
    Ensure a component is initialized and return it.

    This is a helper for the common pattern of checking if a component
    is None and raising an error if so.

    Args:
        component: The component to check (may be None)
        name: Human-readable name for error messages
        error_type: Exception type to raise if component is None

    Returns:
        The component if it's not None

    Raises:
        error_type: If component is None

    Example:
        sprite_extractor = ensure_component(
            self._sprite_extractor,
            "Sprite extractor",
            ExtractionError
        )
    """
    if component is None:
        raise error_type(f"{name} not initialized")
    return component
