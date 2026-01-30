"""Repository layer for frame mapping persistence.

Handles serialization, atomic writes, and version migration for frame mapping projects.
"""

from core.repositories.capture_result_repository import CaptureResultRepository

__all__ = ["CaptureResultRepository"]
