"""
Timing-related constants for SpritePal.

Provides standardized timing values for animations, timeouts, delays, and
polling intervals throughout the application.
"""

# Animation and UI update timings
REFRESH_RATE_60FPS = 16  # 16ms for ~60fps updates
UI_UPDATE_INTERVAL = 50  # 50ms for UI updates during operations
ANIMATION_DEBOUNCE_DELAY = 16  # 16ms debounce delay for UI changes

# Thread and worker timeouts
WORKER_TIMEOUT_SHORT = 500  # 500ms for quick operations
WORKER_TIMEOUT_MEDIUM = 1000  # 1000ms for medium operations
WORKER_TIMEOUT_LONG = 2000  # 2000ms for long operations
WORKER_TIMEOUT_EXTENDED = 5000  # 5000ms for extended operations
WORKER_TIMEOUT_MAXIMUM = 10000  # 10000ms maximum timeout
EXTRACTION_TIMEOUT = 15000  # 15000ms for full extraction chain

# Sleep and delay durations (in seconds)
SLEEP_TINY = 0.01  # 10ms sleep for tight loops
SLEEP_SHORT = 0.02  # 20ms sleep for short delays
SLEEP_MEDIUM = 0.05  # 50ms sleep for medium delays
SLEEP_WORKER = 0.1  # 100ms sleep for worker threads

# Test framework timeouts
TEST_TIMEOUT_SHORT = 100  # 100ms for quick tests
TEST_TIMEOUT_MEDIUM = 1000  # 1000ms for medium tests
TEST_TIMEOUT_LONG = 5000  # 5000ms for long tests
TEST_TIMEOUT_EXTENDED = 10000  # 10000ms for extended test operations

# Progress and status update intervals
STATUS_UPDATE_INTERVAL = 100  # 100ms for status updates
PROGRESS_UPDATE_INTERVAL = 100  # 100ms for progress bar updates
CACHE_OPERATION_TIMEOUT = 5000  # 5000ms for cache operations

# Qt event processing
QT_EVENT_TIMEOUT = 100  # 100ms for Qt event processing
QT_SIGNAL_TIMEOUT = 100  # 100ms for Qt signal timeouts
