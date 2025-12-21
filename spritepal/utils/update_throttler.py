"""
Update throttling and debouncing utilities.

This module provides pure Python implementations for throttling and debouncing
updates, useful for handling rapid UI events, file system changes, and other
high-frequency update scenarios.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any, Generic, TypeVar

T = TypeVar('T')

class UpdateThrottler(Generic[T]):
    """
    Debouncing throttler with last-write-wins semantics.

    This class queues updates and only processes the most recent one after
    a delay, discarding intermediate updates. Perfect for slider movements,
    text input, and other scenarios where only the final value matters.

    Thread-safe implementation using locks.
    """

    def __init__(self, delay_ms: int = 200, callback: Callable[[T], Any] | None = None) -> None:  # pyright: ignore[reportExplicitAny] - Callback return type
        """
        Initialize the update throttler.

        Args:
            delay_ms: Delay in milliseconds before processing
            callback: Optional callback to process updates
        """
        self._delay_seconds = delay_ms / 1000.0
        self._callback = callback
        self._lock = threading.Lock()
        self._pending_value: T | None = None
        self._last_update_time = 0.0
        self._timer: threading.Timer | None = None

    def queue_update(self, value: T) -> None:
        """
        Queue an update, replacing any pending update.

        Args:
            value: The value to queue
        """
        with self._lock:
            self._pending_value = value
            self._last_update_time = time.time()

            # Cancel existing timer if any
            if self._timer is not None:
                self._timer.cancel()

            # Start new timer
            self._timer = threading.Timer(self._delay_seconds, self._process_update)
            self._timer.start()

    def process(self) -> T | None:
        """
        Process and return the pending update immediately.

        Returns:
            The pending value or None if no update pending
        """
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

            value = self._pending_value
            self._pending_value = None

            if value is not None and self._callback:
                self._callback(value)

            return value

    def _process_update(self) -> None:
        """Internal method to process update after delay."""
        with self._lock:
            self._timer = None
            value = self._pending_value
            self._pending_value = None

        # Call callback outside lock to avoid deadlocks
        if value is not None and self._callback:
            self._callback(value)

    def clear(self) -> None:
        """Clear any pending updates."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending_value = None

    def has_pending(self) -> bool:
        """
        Check if there are pending updates.

        Returns:
            True if updates are pending
        """
        with self._lock:
            return self._pending_value is not None

    def get_pending(self) -> T | None:
        """
        Get the pending value without processing it.

        Returns:
            The pending value or None
        """
        with self._lock:
            return self._pending_value

    def cancel_timer(self) -> None:
        """Cancel the timer without clearing the pending value."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

class RateLimiter:
    """
    Fixed-rate limiter for throttling actions.

    This class enforces a minimum time interval between actions,
    useful for API rate limiting, preventing spam, and ensuring
    consistent update rates.
    """

    def __init__(self, min_interval_ms: int = 100, max_burst: int = 1):
        """
        Initialize the rate limiter.

        Args:
            min_interval_ms: Minimum milliseconds between actions
            max_burst: Maximum burst size (actions without delay)
        """
        self._min_interval = min_interval_ms / 1000.0
        self._max_burst = max_burst
        self._lock = threading.Lock()
        self._last_action_time = 0.0
        self._burst_count = 0

    def can_proceed(self) -> bool:
        """
        Check if an action can proceed within rate limits.

        Returns:
            True if action can proceed
        """
        with self._lock:
            current_time = time.time()
            time_since_last = current_time - self._last_action_time

            # Allow burst
            if self._burst_count < self._max_burst:
                return True

            # Check if enough time has passed
            return time_since_last >= self._min_interval

    def record_action(self) -> bool:
        """
        Record an action and return if it was allowed.

        Returns:
            True if action was allowed and recorded
        """
        with self._lock:
            current_time = time.time()
            time_since_last = current_time - self._last_action_time

            # Reset burst count if enough time passed
            if time_since_last >= self._min_interval:
                self._burst_count = 0

            # Check if we can proceed
            if self._burst_count < self._max_burst:
                self._burst_count += 1
                self._last_action_time = current_time
                return True

            if time_since_last >= self._min_interval:
                self._burst_count = 1
                self._last_action_time = current_time
                return True

            return False

    def wait_if_needed(self) -> float:
        """
        Calculate wait time needed before next action.

        Returns:
            Seconds to wait (0 if can proceed immediately)
        """
        with self._lock:
            if self._burst_count < self._max_burst:
                return 0.0

            current_time = time.time()
            time_since_last = current_time - self._last_action_time
            wait_time = self._min_interval - time_since_last

            return max(0.0, wait_time)

    def reset(self) -> None:
        """Reset the rate limiter state."""
        with self._lock:
            self._last_action_time = 0.0
            self._burst_count = 0

class BatchUpdateCollector(Generic[T]):
    """
    Collects updates and processes them in batches.

    This class accumulates updates and processes them together after
    a delay or when a size threshold is reached. Useful for batching
    database writes, network requests, or file operations.
    """

    def __init__(
        self,
        batch_size: int = 10,
        batch_delay_ms: int = 500,
        callback: Callable[[list[T]], Any] | None = None  # pyright: ignore[reportExplicitAny] - Callback return type
    ) -> None:
        """
        Initialize the batch collector.

        Args:
            batch_size: Maximum batch size before auto-processing
            batch_delay_ms: Maximum delay before processing
            callback: Optional callback to process batches
        """
        self._batch_size = batch_size
        self._batch_delay = batch_delay_ms / 1000.0
        self._callback = callback
        self._lock = threading.Lock()
        self._queue: deque[T] = deque()
        self._timer: threading.Timer | None = None

    def add(self, item: T) -> None:
        """
        Add an item to the batch.

        Args:
            item: Item to add
        """
        with self._lock:
            self._queue.append(item)

            # Process immediately if batch is full
            if len(self._queue) >= self._batch_size:
                self._process_batch_locked()
            # Start timer if this is the first item
            elif len(self._queue) == 1 and self._timer is None:
                self._timer = threading.Timer(self._batch_delay, self.process_batch)
                self._timer.start()

    def process_batch(self) -> list[T]:
        """
        Process the current batch immediately.

        Returns:
            List of processed items
        """
        with self._lock:
            return self._process_batch_locked()

    def _process_batch_locked(self) -> list[T]:
        """Process batch while holding lock."""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

        batch = list(self._queue)
        self._queue.clear()

        # Release lock before callback to avoid deadlocks
        if batch and self._callback:
            # Create a copy to pass to callback
            batch_copy = batch.copy()
            # Temporarily release lock for callback
            self._lock.release()
            try:
                self._callback(batch_copy)
            finally:
                self._lock.acquire()

        return batch

    def clear(self) -> None:
        """Clear all pending items."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._queue.clear()

    def size(self) -> int:
        """
        Get current batch size.

        Returns:
            Number of items in current batch
        """
        with self._lock:
            return len(self._queue)

    def get_pending(self) -> list[T]:
        """
        Get pending items without processing.

        Returns:
            Copy of pending items
        """
        with self._lock:
            return list(self._queue)

class LastWriteWinsQueue(Generic[T]):
    """
    Simple queue that only keeps the last written value.

    This is a simplified version of UpdateThrottler for scenarios
    where you just need the queue behavior without timing.
    """

    def __init__(self):
        """Initialize the queue."""
        self._lock = threading.Lock()
        self._value: T | None = None

    def put(self, value: T) -> None:
        """
        Put a value in the queue, replacing any existing value.

        Args:
            value: Value to store
        """
        with self._lock:
            self._value = value

    def get(self) -> T | None:
        """
        Get and clear the queued value.

        Returns:
            The queued value or None
        """
        with self._lock:
            value = self._value
            self._value = None
            return value

    def peek(self) -> T | None:
        """
        Peek at the queued value without removing it.

        Returns:
            The queued value or None
        """
        with self._lock:
            return self._value

    def clear(self) -> None:
        """Clear the queue."""
        with self._lock:
            self._value = None

    def has_value(self) -> bool:
        """
        Check if queue has a value.

        Returns:
            True if value is queued
        """
        with self._lock:
            return self._value is not None
