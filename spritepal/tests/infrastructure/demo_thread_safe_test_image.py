"""
Demonstration of ThreadSafeTestImage usage in threading scenarios.

This script shows the practical usage of ThreadSafeTestImage to prevent
Qt threading violations that cause "Fatal Python error: Aborted" crashes.

Run this script to see the difference between safe and unsafe Qt threading patterns.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from PySide6.QtGui import QColor

# Only import ThreadSafeTestImage, never QPixmap in worker threads
from thread_safe_test_image import ImagePool, ThreadSafeTestImage


def demonstrate_thread_safe_image_creation():
    """Demonstrate safe image creation in worker threads."""
    print("=== Thread-Safe Image Creation Demo ===")
    results = []

    def worker_thread(thread_id: int):
        """Worker thread that safely creates and manipulates images."""
        print(f"Worker {thread_id}: Creating thread-safe image...")

        # ✅ SAFE - ThreadSafeTestImage uses QImage internally (thread-safe)
        image = ThreadSafeTestImage(100, 100)
        image.fill(QColor(thread_id * 50 % 255, 100, 150))

        results.append({
            'thread_id': thread_id,
            'image_size': f"{image.width()}x{image.height()}",
            'size_bytes': image.sizeInBytes(),
            'is_null': image.isNull(),
            'created_in_thread': image.created_in_thread()
        })

        print(f"Worker {thread_id}: Successfully created {image}")
        return True

    # Start multiple worker threads
    threads = []
    for i in range(3):
        t = threading.Thread(target=worker_thread, args=(i,))
        threads.append(t)
        t.start()

    # Wait for all threads to complete
    for t in threads:
        t.join()

    print("\nResults:")
    for result in results:
        print(f"  Thread {result['thread_id']}: "
              f"{result['image_size']}, "
              f"{result['size_bytes']} bytes, "
              f"null={result['is_null']}")

    print(f"\n✅ Success: All {len(results)} threads completed without crashes!\n")

def demonstrate_image_pool_performance():
    """Demonstrate TestImagePool for performance optimization."""
    print("=== Image Pool Performance Demo ===")

    # Test without pool
    start_time = time.time()
    for i in range(20):
        image = ThreadSafeTestImage(100, 100)
        image.fill(QColor(255, 0, 0))
    no_pool_time = time.time() - start_time

    # Test with pool
    pool = ImagePool()
    start_time = time.time()
    for i in range(20):
        image = pool.get_test_image(100, 100)
        image.fill(QColor(255, 0, 0))
        pool.return_image(image)
    pool_time = time.time() - start_time

    print(f"Without pool: {no_pool_time:.4f} seconds")
    print(f"With pool:    {pool_time:.4f} seconds")
    print(f"Pool efficiency: {((no_pool_time - pool_time) / no_pool_time * 100):.1f}% faster")
    print(f"Final pool size: {pool.size()} images\n")

def demonstrate_concurrent_image_processing():
    """Demonstrate concurrent image processing using ThreadPoolExecutor."""
    print("=== Concurrent Image Processing Demo ===")

    def process_batch(batch_id: int, batch_size: int = 5):
        """Process a batch of images concurrently."""
        batch_results = []

        for i in range(batch_size):
            # Create unique image for each item in batch
            image = ThreadSafeTestImage(80 + i * 10, 80 + i * 10)
            image.fill(QColor(batch_id * 40 % 255, i * 50 % 255, 100))

            batch_results.append({
                'batch_id': batch_id,
                'item_id': i,
                'dimensions': f"{image.width()}x{image.height()}",
                'thread_id': threading.get_ident()
            })

        return batch_results

    # Process batches concurrently
    all_results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = []

        # Submit batch processing tasks
        for batch_id in range(4):
            future = executor.submit(process_batch, batch_id)
            futures.append(future)

        # Collect results
        for future in futures:
            batch_results = future.result()
            all_results.extend(batch_results)

    print(f"Processed {len(all_results)} images across {len({r['thread_id'] for r in all_results})} threads")

    # Group results by thread
    by_thread = {}
    for result in all_results:
        thread_id = result['thread_id']
        if thread_id not in by_thread:
            by_thread[thread_id] = []
        by_thread[thread_id].append(result)

    for thread_id, results in by_thread.items():
        print(f"  Thread {thread_id}: processed {len(results)} images")

    print("✅ Concurrent processing completed successfully!\n")

def demonstrate_cache_simulation():
    """Simulate a thread-safe cache using ThreadSafeTestImage."""
    print("=== Thread-Safe Cache Simulation Demo ===")

    # Simulate a simple thread-safe image cache
    cache = {}
    cache_lock = threading.Lock()

    def cache_worker(worker_id: int, keys: list[str]):
        """Worker that adds images to cache."""
        for key in keys:
            # Create thread-safe image
            image = ThreadSafeTestImage(64, 64)
            image.fill(QColor(worker_id * 60 % 255, 120, 200))

            # Thread-safe cache update
            with cache_lock:
                cache[key] = {
                    'image': image,
                    'created_by': worker_id,
                    'created_in_thread': image.created_in_thread(),
                    'size_bytes': image.sizeInBytes()
                }

            print(f"Worker {worker_id}: cached '{key}'")

    # Start cache workers
    workers = []
    for worker_id in range(3):
        keys = [f"image_{worker_id}_{i}" for i in range(3)]
        worker = threading.Thread(target=cache_worker, args=(worker_id, keys))
        workers.append(worker)
        worker.start()

    # Wait for workers to complete
    for worker in workers:
        worker.join()

    print(f"\nCache contains {len(cache)} images:")
    for key, data in cache.items():
        print(f"  {key}: {data['image']}, created by worker {data['created_by']}")

    print("✅ Cache simulation completed without threading violations!\n")

def demonstrate_mock_integration():
    """Demonstrate how ThreadSafeTestImage integrates with mocking."""
    print("=== Mock Integration Demo ===")

    # Mock a cache manager that uses QImage internally
    with patch('builtins.print'):  # Mock print to reduce output
        def mock_cache_operation():
            """Simulate cache operation that would normally use QPixmap."""
            # In real code, this might be a cache manager method
            image = ThreadSafeTestImage(50, 50)
            image.fill(QColor(100, 200, 100))

            # Simulate some processing
            result = {
                'processed': True,
                'size': image.size(),
                'bytes': image.sizeInBytes(),
                'is_null': image.isNull()
            }

            return result

        # Run mock operation in thread
        result = None
        def worker():
            nonlocal result
            result = mock_cache_operation()

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()

    print(f"Mock operation result: {result}")
    print("✅ Mock integration successful - no Qt threading violations!\n")

def main():
    """Run all demonstrations."""
    print("ThreadSafeTestImage Demonstration Script")
    print("=" * 50)
    print()

    try:
        demonstrate_thread_safe_image_creation()
        demonstrate_image_pool_performance()
        demonstrate_concurrent_image_processing()
        demonstrate_cache_simulation()
        demonstrate_mock_integration()

        print("🎉 All demonstrations completed successfully!")
        print("ThreadSafeTestImage prevents Qt threading violations and crashes.")

    except Exception as e:
        print(f"❌ Demo failed with error: {e}")
        print("This might indicate a threading violation or other issue.")
        raise

if __name__ == "__main__":
    main()
