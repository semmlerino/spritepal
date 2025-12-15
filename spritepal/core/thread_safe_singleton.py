"""
Thread-Safe Singleton Base Classes

Provides thread-safe singleton patterns for both Qt and non-Qt objects.
Ensures proper synchronization and Qt thread affinity checking.

Moved from utils/thread_safe_singleton.py to fix layer boundary violations
(utils should be stdlib-only per docs/architecture.md).
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Generic, TypeVar, override

from PySide6.QtCore import QObject, QThread
from PySide6.QtWidgets import QApplication

try:
    from utils.logging_config import get_logger
except ImportError:
    import logging

    def get_logger(module_name: str) -> logging.Logger:
        return logging.getLogger(module_name)


logger = get_logger(__name__)

T = TypeVar("T")
TSingleton = TypeVar("TSingleton")
TQt = TypeVar("TQt")
TLazy = TypeVar("TLazy")
TFactory = TypeVar("TFactory")
TResult = TypeVar("TResult")  # For safe_qt_call return type


class ThreadSafeSingleton(Generic[T]):
    """
    Thread-safe singleton base class using double-checked locking pattern.

    This class provides a thread-safe singleton pattern that can be subclassed
    to create thread-safe singleton instances of any type.

    Example:
        class MyManager:
            def __init__(self):
                self.data = "initialized"

        class MyManagerSingleton(ThreadSafeSingleton[MyManager]):
            _instance: MyManager | None = None
            _lock = threading.Lock()

            @classmethod
            def _create_instance(cls) -> MyManager:
                return MyManager()

        # Usage
        manager = MyManagerSingleton.get()
    """

    _instance: T | None = None
    _lock: threading.Lock = threading.Lock()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Ensure each subclass gets its own instance and lock."""
        super().__init_subclass__(**kwargs)
        # Each subclass needs its own _instance and _lock to avoid sharing
        if "_instance" not in cls.__dict__:
            cls._instance = None
        if "_lock" not in cls.__dict__:
            cls._lock = threading.Lock()

    @classmethod
    def get(cls, *args: Any, **kwargs: Any) -> T:
        """
        Get or create the singleton instance (thread-safe).

        Uses double-checked locking pattern for optimal performance:
        - Fast path: Check instance without lock
        - Slow path: Acquire lock, double-check, then create if needed

        Args:
            *args: Arguments to pass to _create_instance
            **kwargs: Keyword arguments to pass to _create_instance

        Returns:
            The singleton instance
        """
        # Fast path - check without lock
        if cls._instance is not None:
            return cls._instance

        # Slow path - create with lock
        with cls._lock:
            # Double-check pattern - instance might have been created
            # by another thread while we were waiting for the lock
            if cls._instance is None:
                logger.debug(f"Creating new singleton instance of {cls.__name__}")
                cls._instance = cls._create_instance(*args, **kwargs)
            return cls._instance

    @classmethod
    def _create_instance(cls, *args: Any, **kwargs: Any) -> T:
        """
        Create a new instance of the singleton.

        This method must be overridden by subclasses to define
        how to create the singleton instance.

        Args:
            *args: Arguments for instance creation
            **kwargs: Keyword arguments for instance creation

        Returns:
            New instance of type T

        Raises:
            NotImplementedError: If not overridden by subclass
        """
        raise NotImplementedError("Subclasses must implement _create_instance")

    @classmethod
    def reset(cls) -> None:
        """
        Reset the singleton instance (thread-safe).

        This is primarily useful for testing scenarios where you need
        to clear the singleton state between tests.
        """
        with cls._lock:
            if cls._instance is not None:
                logger.debug(f"Resetting singleton instance of {cls.__name__}")
                # Allow subclasses to perform cleanup before reset
                cls._cleanup_instance(cls._instance)
            cls._instance = None

    @classmethod
    def _cleanup_instance(cls, instance: T) -> None:
        """
        Perform cleanup before resetting instance.

        Override this method in subclasses if cleanup is needed
        before the singleton instance is reset.

        Args:
            instance: The instance being cleaned up
        """
        # Default: no cleanup needed

    @classmethod
    def is_initialized(cls) -> bool:
        """
        Check if the singleton instance has been created (thread-safe).

        Returns:
            True if instance exists, False otherwise
        """
        return cls._instance is not None


class QtThreadSafeSingleton(ThreadSafeSingleton[TQt]):
    """
    Thread-safe singleton for Qt objects with thread affinity checking.

    This singleton ensures that:
    1. Instance creation is thread-safe
    2. Qt method calls only happen on the main thread
    3. Proper cleanup of Qt objects

    Example:
        from PySide6.QtWidgets import QDialog

        class MyDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)

        class MyDialogSingleton(QtThreadSafeSingleton[MyDialog]):
            _instance: MyDialog | None = None
            _lock = threading.Lock()

            @classmethod
            def _create_instance(cls, parent=None) -> MyDialog:
                cls._ensure_main_thread()
                return MyDialog(parent)

        # Usage
        dialog = MyDialogSingleton.get()
    """

    @classmethod
    def _ensure_main_thread(cls) -> None:
        """
        Ensure that the current thread is the main Qt thread.

        Raises:
            RuntimeError: If called from a non-main thread
        """
        if QApplication.instance() is None:
            logger.warning("No Qt application instance found")
            return

        current_thread = QThread.currentThread()
        app_instance = QApplication.instance()
        if app_instance is None:
            return  # No Qt application running
        main_thread = app_instance.thread()

        if current_thread != main_thread:
            raise RuntimeError(
                f"Qt object method called from wrong thread. "
                f"Current: {current_thread}, Main: {main_thread}. "
                f"Qt objects must only be accessed from the main thread."
            )

    @classmethod
    def safe_qt_call(cls, qt_method: Callable[[], TResult]) -> TResult | None:
        """
        Safely call a Qt method, returning None if not on main thread.

        This method allows you to safely call Qt methods that might be
        called from worker threads, returning None instead of crashing.

        Args:
            qt_method: A callable that invokes a Qt method

        Returns:
            Result of qt_method if on main thread, None otherwise

        Example:
            result = MyDialogSingleton.safe_qt_call(lambda: dialog.isVisible())
        """
        try:
            cls._ensure_main_thread()
            return qt_method()
        except RuntimeError as e:
            logger.warning(f"Qt method call skipped due to thread affinity: {e}")
            return None

    @classmethod
    @override
    def _cleanup_instance(cls, instance: TQt) -> None:
        """
        Cleanup Qt object instance.

        For Qt objects, we should call deleteLater() if it's a QObject
        to ensure proper cleanup in the Qt event loop.

        Args:
            instance: The Qt instance being cleaned up
        """
        if isinstance(instance, QObject):
            try:
                cls._ensure_main_thread()
                instance.deleteLater()
                logger.debug(f"Scheduled Qt object deletion for {type(instance).__name__}")
            except RuntimeError:
                logger.warning(
                    f"Could not schedule deletion for {type(instance).__name__} (wrong thread)"
                )


class LazyThreadSafeSingleton(ThreadSafeSingleton[TLazy]):
    """
    Thread-safe singleton with lazy initialization support.

    Provides additional functionality for singletons that need
    deferred initialization or conditional creation.
    """

    _initialized: bool = False
    _initialization_lock: threading.Lock = threading.Lock()

    @classmethod
    def get_if_initialized(cls) -> TLazy | None:
        """
        Get the singleton instance only if it's already been initialized.

        Returns:
            The singleton instance if initialized, None otherwise
        """
        return cls._instance if cls._initialized else None

    @classmethod
    def initialize(cls, *args: Any, **kwargs: Any) -> TLazy:
        """
        Explicitly initialize the singleton instance.

        This allows for controlled initialization separate from first access.

        Args:
            *args: Arguments for instance creation
            **kwargs: Keyword arguments for instance creation

        Returns:
            The initialized singleton instance
        """
        # Use _lock (same as get()) to prevent race between initialize() and get()
        with cls._lock:
            if not cls._initialized:
                cls._instance = cls._create_instance(*args, **kwargs)
                cls._initialized = True
                logger.debug(f"Initialized singleton instance of {cls.__name__}")
            return cls._instance  # type: ignore[return-value]  # Instance is guaranteed to exist after initialization

    @classmethod
    @override
    def reset(cls) -> None:
        """Reset both the instance and initialization state."""
        with cls._lock:
            if cls._instance is not None:
                cls._cleanup_instance(cls._instance)
            cls._instance = None
            cls._initialized = False


# Convenience functions for common patterns


def create_simple_singleton(
    instance_type: type[TFactory],
) -> type[ThreadSafeSingleton[TFactory]]:
    """
    Create a simple thread-safe singleton class for a given type.

    Args:
        instance_type: The type to create a singleton for

    Returns:
        A singleton class for the given type

    Example:
        MyManager = SomeManagerClass
        MyManagerSingleton = create_simple_singleton(MyManager)
        manager = MyManagerSingleton.get()
    """

    class SimpleSingleton(ThreadSafeSingleton[TFactory]):  # type: ignore[misc]
        _instance: TFactory | None = None
        _lock = threading.Lock()

        @classmethod
        def _create_instance(cls, *args, **kwargs) -> TFactory:  # type: ignore[misc]
            return instance_type(*args, **kwargs)

    SimpleSingleton.__name__ = f"{instance_type.__name__}Singleton"
    return SimpleSingleton


def create_qt_singleton(
    qt_type: type[TFactory],
) -> type[QtThreadSafeSingleton[TFactory]]:
    """
    Create a thread-safe Qt singleton class for a given Qt type.

    Args:
        qt_type: The Qt type to create a singleton for

    Returns:
        A Qt singleton class for the given type

    Example:
        MyDialog = SomeDialogClass
        MyDialogSingleton = create_qt_singleton(MyDialog)
        dialog = MyDialogSingleton.get()
    """

    class QtSingleton(QtThreadSafeSingleton[TFactory]):  # type: ignore[misc]
        _instance: TFactory | None = None
        _lock = threading.Lock()

        @classmethod
        def _create_instance(cls, *args, **kwargs) -> TFactory:  # type: ignore[misc]
            cls._ensure_main_thread()
            return qt_type(*args, **kwargs)

    QtSingleton.__name__ = f"{qt_type.__name__}Singleton"
    return QtSingleton
