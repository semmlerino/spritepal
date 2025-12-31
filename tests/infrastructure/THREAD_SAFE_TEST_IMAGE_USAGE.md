# ThreadSafeTestImage Usage Guide

## Overview

`ThreadSafeTestImage` is a critical component for preventing Qt threading violations in SpritePal tests. It provides a thread-safe alternative to `QPixmap` by using `QImage` internally, following Qt's canonical threading pattern.

## The Problem

Qt has strict threading rules that cause "Fatal Python error: Aborted" crashes:

| Class | Thread Safety | Usage |
|-------|---------------|--------|
| **QPixmap** | ❌ **Main GUI thread ONLY** | Display, UI rendering |
| **QImage** | ✅ **Any thread** | Image processing, workers |

### Crash Symptoms
```python
# ❌ FATAL ERROR - Creates QPixmap in worker thread
def worker():
    pixmap = QPixmap(100, 100)  # CRASH: "Fatal Python error: Aborted"

thread = threading.Thread(target=worker)
thread.start()  # Will crash Python
```

## The Solution

Use `ThreadSafeTestImage` instead of `QPixmap` in worker threads:

```python
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage

# ✅ SAFE - ThreadSafeTestImage uses QImage internally
def worker():
    image = ThreadSafeTestImage(100, 100)  # Thread-safe
    image.fill(QColor(255, 0, 0))
```

## Basic Usage

### Creating Images
```python
# Default size (100x100)
image = ThreadSafeTestImage()

# Custom size
image = ThreadSafeTestImage(200, 150)

# Fill with color
image.fill(QColor(255, 0, 0))  # Red
image.fill(QColor(0, 255, 0))  # Green
image.fill()                   # White (default)
```

### QPixmap-Compatible Interface
```python
# All standard QPixmap-like methods are available
image = ThreadSafeTestImage(120, 80)

assert image.width() == 120
assert image.height() == 80
assert image.size() == QSize(120, 80)
assert not image.isNull()
assert image.sizeInBytes() > 0
```

### Getting Internal QImage
```python
# Access the internal QImage for advanced operations
image = ThreadSafeTestImage(100, 100)
qimage = image.toImage()  # Returns QImage instance
```

## Thread Safety Examples

### Concurrent Image Creation
```python
import threading
from concurrent.futures import ThreadPoolExecutor

def process_image(thread_id):
    """Safe to call from any thread."""
    image = ThreadSafeTestImage(100, 100)
    image.fill(QColor(thread_id * 50 % 255, 100, 150))
    return image

# Multiple threads can safely create images
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = []
    for i in range(10):
        future = executor.submit(process_image, i)
        futures.append(future)
    
    # All threads complete without crashes
    images = [future.result() for future in futures]
```

### Thread-Safe Cache Simulation
```python
import threading

cache = {}
cache_lock = threading.Lock()

def cache_worker(worker_id, keys):
    for key in keys:
        # Create thread-safe image
        image = ThreadSafeTestImage(64, 64)
        image.fill(QColor(worker_id * 60 % 255, 120, 200))
        
        # Thread-safe cache update
        with cache_lock:
            cache[key] = image
```

## Integration with Mocking

When mocking Qt operations, mock `QImage` operations, not `QPixmap`:

```python
from unittest.mock import patch

# ✅ CORRECT - Mock QImage operations
def test_cache_threading():
    with patch('cache_manager.QImage') as mock_qimage:
        mock_qimage.return_value = mock_image_instance
        
        def worker():
            image = ThreadSafeTestImage(100, 100)
            result = cache_manager.process(image)
        
        threading.Thread(target=worker).start()
```

## Testing Patterns

### Unit Tests with Thread Safety
```python
def test_concurrent_operations():
    """Test that avoids Qt threading violations."""
    results = []
    errors = []
    
    def worker(thread_id):
        try:
            # ✅ SAFE - Use ThreadSafeTestImage
            image = ThreadSafeTestImage(100, 100)
            image.fill(QColor(255, 0, 0))
            results.append(thread_id)
        except Exception as e:
            errors.append((thread_id, str(e)))
    
    # Start multiple threads
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # Verify no threading violations
    assert len(errors) == 0
    assert len(results) == 5
```

### Integration Tests with Real Worker Threads
```python
def test_worker_image_processing():
    """Test real worker thread with ThreadSafeTestImage."""
    
    class ImageWorker(QThread):
        result_ready = pyqtSignal(object)
        
        def run(self):
            # Safe to create images in QThread
            image = ThreadSafeTestImage(200, 200)
            image.fill(QColor(100, 200, 100))
            
            # Process image...
            result = self.process_image(image)
            self.result_ready.emit(result)
    
    worker = ImageWorker()
    
    # Use qtbot to test signals safely
    with qtbot.waitSignal(worker.result_ready, timeout=5000) as blocker:
        worker.start()
    
    # Verify result
    assert blocker.args[0] is not None
```

## Debugging and Thread Tracking

ThreadSafeTestImage includes debugging features:

```python
image = ThreadSafeTestImage(100, 100)

# Check which thread created the image
thread_id = image.created_in_thread()
print(f"Image created in thread: {thread_id}")

# String representations for debugging
print(str(image))   # ThreadSafeTestImage(100x100, thread_id=..., null=False)
print(repr(image))  # ThreadSafeTestImage(width=100, height=100, format=..., bytes=...)
```

## Best Practices

1. **Always use ThreadSafeTestImage in worker threads** - Never create QPixmap in worker threads
2. **Mock QImage operations** - When mocking, patch QImage, not QPixmap
3. **Track thread IDs for debugging** - Use created_in_thread() to debug threading issues
4. **Test both single-threaded and multi-threaded scenarios** - Ensure code works in all contexts

## Error Handling

ThreadSafeTestImage includes proper error handling:

```python
# Validation of input parameters
try:
    image = ThreadSafeTestImage(0, 100)  # Invalid dimensions
except ValueError as e:
    print(f"Error: {e}")  # "Image dimensions must be positive"

# Memory handling for large images
try:
    image = ThreadSafeTestImage(10000, 10000)  # Very large
except MemoryError:
    print("Insufficient memory for large image")
```

## Summary

ThreadSafeTestImage is essential for:
- ✅ Preventing Qt threading violation crashes
- ✅ Enabling safe image operations in worker threads
- ✅ Providing QPixmap-compatible interface
- ✅ Optimizing performance with image pooling
- ✅ Supporting comprehensive testing patterns

Use it whenever your tests involve image operations in worker threads to avoid "Fatal Python error: Aborted" crashes.