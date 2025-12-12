"""
Thread-Safe Singleton Base Classes.

DEPRECATED: This module re-exports from core.thread_safe_singleton for backward
compatibility. New code should import directly from core.thread_safe_singleton.
"""
from __future__ import annotations

# Re-export all from the canonical location
from core.thread_safe_singleton import (
    LazyThreadSafeSingleton,
    QtThreadSafeSingleton,
    ThreadSafeSingleton,
    create_qt_singleton,
    create_simple_singleton,
)

__all__ = [
    "ThreadSafeSingleton",
    "QtThreadSafeSingleton",
    "LazyThreadSafeSingleton",
    "create_simple_singleton",
    "create_qt_singleton",
]
