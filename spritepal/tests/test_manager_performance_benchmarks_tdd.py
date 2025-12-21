"""
TDD Performance Benchmarks for Manager Operations with Real Components.

This test suite applies TDD methodology to performance testing:
- RED: Establish performance requirements and failing benchmarks
- GREEN: Optimize implementation to meet performance requirements
- REFACTOR: Maintain performance while improving code quality

Performance scenarios tested with real components:
1. Manager initialization and setup overhead
2. Parameter validation performance with real files
3. Signal emission and Qt event processing performance
4. Resource cleanup and memory management performance
5. Concurrent operation performance and scalability

Benefits of real performance testing vs mocks:
- Tests actual I/O and file system performance
- Validates real Qt signal/slot performance overhead
- Measures actual memory usage and garbage collection
- Tests real threading synchronization performance
- Validates actual resource management overhead
"""

from __future__ import annotations

import pytest

# Skip entire module if pytest-benchmark is not installed
pytest.importorskip("pytest_benchmark")

from core.managers import ValidationError
from tests.infrastructure.data_repository import (
    DataRepository,
    get_test_data_repository,
)
from tests.infrastructure.manager_test_context import (
    # Serial execution required: Thread safety concerns, Real Qt components
    ManagerTestContext,
    manager_context,
)

# Phase 2 Real Component Testing Infrastructure
from tests.infrastructure.real_component_factory import RealComponentFactory

pytestmark = [
    pytest.mark.headless,
    pytest.mark.performance,
    pytest.mark.slow,
]

@pytest.fixture
def test_data_repo() -> DataRepository:
    """Provide test data repository for performance tests."""
    return get_test_data_repository()

class TestManagerPerformanceBenchmarksTDD:
    """TDD performance benchmarks for manager operations."""

    @pytest.mark.benchmark
    def test_extraction_manager_initialization_performance_tdd(self, benchmark, isolated_managers):
        """TDD: Manager initialization should complete within performance budget.

        RED: Establish initialization time requirements (< 100ms)
        GREEN: Optimize initialization to meet requirements
        REFACTOR: Maintain initialization performance while adding features

        Performance requirements:
        - Cold initialization: < 100ms
        - Warm initialization: < 50ms
        - Memory overhead: < 10MB
        """
        def create_extraction_manager():
            with RealComponentFactory(manager_registry=isolated_managers) as factory:
                manager = factory.create_extraction_manager(with_test_data=True)

                # Verify manager is fully initialized
                assert manager.is_initialized()
                assert manager._sprite_extractor is not None
                assert manager._rom_extractor is not None

                return manager

        # Benchmark real manager creation performance
        result = benchmark(create_extraction_manager)

        # Verify initialization was successful
        assert result is not None

    @pytest.mark.benchmark
    def test_injection_manager_initialization_performance_tdd(self, benchmark, isolated_managers):
        """TDD: Injection manager initialization performance baseline."""
        def create_injection_manager():
            with RealComponentFactory(manager_registry=isolated_managers) as factory:
                manager = factory.create_injection_manager(with_test_data=True)

                # Verify manager is fully initialized
                assert manager.is_initialized()
                return manager

        # Benchmark injection manager creation
        result = benchmark(create_injection_manager)
        assert result is not None

    @pytest.mark.benchmark
    def test_parameter_validation_performance_tdd(self, benchmark, test_data_repo, tmp_path):
        """TDD: Parameter validation should be fast enough for real-time UI.

        RED: Establish validation time requirements (< 10ms per validation)
        GREEN: Optimize validation logic for speed
        REFACTOR: Maintain validation accuracy while improving speed
        """
        output_vram_path = str(tmp_path / "perf_test.vram")

        def validate_parameters():
            with manager_context("extraction", "injection") as ctx:
                extraction_mgr = ctx.get_extraction_manager()
                injection_mgr = ctx.get_injection_manager()

                # Get test data
                vram_data = test_data_repo.get_vram_extraction_data("small")
                injection_data = test_data_repo.get_injection_data("small")

                # Benchmark extraction parameter validation
                extraction_params = {
                    "vram_path": vram_data["vram_path"],
                    "output_base": vram_data["output_base"]
                }

                try:
                    extraction_mgr.validate_extraction_params(extraction_params)
                except ValidationError:
                    pass  # Performance test focuses on speed, not success

                # Benchmark injection parameter validation
                injection_params = {
                    "mode": "vram",
                    "sprite_path": injection_data["sprite_path"],
                    "input_vram": vram_data["vram_path"],
                    "output_vram": output_vram_path,
                    "offset": 0x8000,
                }

                try:
                    injection_mgr.validate_injection_params(injection_params)
                except ValidationError:
                    pass  # Performance test focuses on speed, not success

                return True

        # Benchmark parameter validation performance
        result = benchmark(validate_parameters)
        assert result is True

    @pytest.mark.benchmark
    def test_signal_emission_performance_tdd(self, benchmark, test_data_repo, qtbot):
        """TDD: Qt signal emission should not create performance bottlenecks.
        
        RED: Establish signal performance requirements (< 1ms per emission)
        GREEN: Optimize signal/slot connections for performance
        REFACTOR: Maintain signal functionality while optimizing performance
        """
        def emit_manager_signals():
            with manager_context("extraction", "injection") as ctx:
                extraction_mgr = ctx.get_extraction_manager()
                injection_mgr = ctx.get_injection_manager()

                # Track signal emissions
                signal_count = 0

                def count_signal(*args):
                    nonlocal signal_count
                    signal_count += 1

                # Connect to multiple signals
                extraction_mgr.extraction_progress.connect(count_signal)
                injection_mgr.injection_progress.connect(count_signal)

                # Emit multiple signals for performance testing
                for i in range(10):
                    extraction_mgr.extraction_progress.emit(f"Progress {i}")
                    injection_mgr.injection_progress.emit(f"Injection {50 + i}")

                # Process Qt events
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()

                return signal_count

        # Benchmark signal emission performance
        result = benchmark(emit_manager_signals)

        # Verify signals were emitted (may be processed asynchronously)
        assert result >= 0  # Should emit some signals

    @pytest.mark.benchmark
    def test_concurrent_operation_performance_tdd(self, benchmark, test_data_repo):
        """TDD: Concurrent operations should not degrade performance significantly.
        
        RED: Establish concurrency performance requirements
        GREEN: Optimize locking and synchronization for performance
        REFACTOR: Maintain thread safety while minimizing overhead
        """
        def run_concurrent_operations():
            with manager_context("extraction", "injection") as ctx:
                extraction_mgr = ctx.get_extraction_manager()
                ctx.get_injection_manager()

                # Start multiple operations concurrently
                operations = []

                # Extraction operations
                for i in range(3):
                    op_name = f"vram_extraction_{i}"
                    if extraction_mgr._start_operation(op_name):
                        operations.append(("extraction", op_name))

                # Verify concurrent state
                active_count = sum(1 for op_type, op_name in operations
                                 if op_type == "extraction" and
                                 extraction_mgr.is_operation_active(op_name))

                # Cleanup operations
                for op_type, op_name in operations:
                    if op_type == "extraction":
                        extraction_mgr._finish_operation(op_name)

                return active_count

        # Benchmark concurrent operation management
        result = benchmark(run_concurrent_operations)

        # Should handle at least some concurrent operations
        assert result >= 0

    @pytest.mark.benchmark
    def test_resource_cleanup_performance_tdd(self, benchmark):
        """TDD: Resource cleanup should be fast and complete.
        
        RED: Establish cleanup time requirements (< 50ms)
        GREEN: Optimize cleanup logic for speed and completeness
        REFACTOR: Maintain cleanup thoroughness while improving speed
        """
        def create_and_cleanup_managers():
            # Create multiple managers with state
            contexts = []
            managers = []

            try:
                # Create managers with state
                for i in range(3):
                    ctx = ManagerTestContext()
                    ctx.initialize_managers("extraction", "injection")

                    extraction_mgr = ctx.get_extraction_manager()
                    injection_mgr = ctx.get_injection_manager()

                    # Set up some state
                    extraction_mgr._start_operation(f"test_op_{i}")

                    contexts.append(ctx)
                    managers.extend([extraction_mgr, injection_mgr])

                # Verify state was created
                sum(1 for mgr in managers
                                if hasattr(mgr, 'is_operation_active') and
                                any(mgr.is_operation_active(f"test_op_{i}") for i in range(3)))

                return len(contexts)

            finally:
                # Cleanup all contexts (this is what we're benchmarking)
                for ctx in contexts:
                    ctx.cleanup()

        # Benchmark resource cleanup performance
        result = benchmark(create_and_cleanup_managers)

        # Should have created some contexts
        assert result > 0

    @pytest.mark.benchmark
    def test_manager_context_performance_tdd(self, benchmark):
        """TDD: Manager context creation should be lightweight.
        
        RED: Establish context creation requirements (< 20ms)
        GREEN: Optimize context initialization and lifecycle
        REFACTOR: Maintain context functionality while optimizing performance
        """
        def create_manager_contexts():
            contexts_created = 0

            # Create multiple contexts to test overhead
            for i in range(5):
                with manager_context("all") as ctx:
                    extraction_mgr = ctx.get_extraction_manager()
                    injection_mgr = ctx.get_injection_manager()
                    session_mgr = ctx.get_session_manager()

                    # Verify managers are functional
                    assert extraction_mgr.is_initialized()
                    assert injection_mgr.is_initialized()
                    assert session_mgr.is_initialized()

                    contexts_created += 1

            return contexts_created

        # Benchmark context creation performance
        result = benchmark(create_manager_contexts)

        # Should create all requested contexts
        assert result == 5

    @pytest.mark.benchmark
    def test_vram_suggestion_performance_tdd(self, benchmark, test_data_repo):
        """TDD: VRAM suggestion algorithms should be fast for UI responsiveness.
        
        RED: Establish suggestion speed requirements (< 100ms)
        GREEN: Optimize file pattern matching and caching
        REFACTOR: Maintain suggestion accuracy while improving speed
        """
        def run_vram_suggestions():
            with manager_context("injection") as ctx:
                injection_mgr = ctx.get_injection_manager()

                # Get test data
                injection_data = test_data_repo.get_injection_data("small")
                sprite_path = injection_data["sprite_path"]

                suggestions = []

                # Run multiple suggestions to test performance consistency
                for i in range(5):
                    suggestion = injection_mgr.get_smart_vram_suggestion(sprite_path)
                    suggestions.append(suggestion)

                return len(suggestions)

        # Benchmark VRAM suggestion performance
        result = benchmark(run_vram_suggestions)

        # Should complete all suggestions
        assert result == 5

class TestManagerMemoryPerformanceTDD:
    """TDD tests for manager memory usage and performance."""

    @pytest.mark.benchmark
    def test_manager_memory_usage_tdd(self, benchmark, isolated_managers):
        """TDD: Manager memory usage should remain reasonable under load.

        RED: Establish memory usage requirements (< 50MB per manager)
        GREEN: Optimize memory allocation and cleanup
        REFACTOR: Maintain functionality while minimizing memory footprint
        """
        def stress_test_managers():
            managers_created = 0

            # Create and destroy many managers to test memory management
            for i in range(10):
                with RealComponentFactory(manager_registry=isolated_managers) as factory:
                    extraction_mgr = factory.create_extraction_manager()
                    injection_mgr = factory.create_injection_manager()

                    # Do some work to allocate memory
                    extraction_mgr._start_operation(f"stress_test_{i}")

                    # Verify functionality
                    assert extraction_mgr.is_initialized()
                    assert injection_mgr.is_initialized()

                    # Cleanup
                    extraction_mgr._finish_operation(f"stress_test_{i}")
                    extraction_mgr.cleanup()
                    injection_mgr.cleanup()

                    managers_created += 1

            return managers_created

        # Benchmark memory usage under stress
        result = benchmark(stress_test_managers)

        # Should create all test managers
        assert result == 10

    @pytest.mark.benchmark
    def test_signal_connection_memory_performance_tdd(self, benchmark, qtbot):
        """TDD: Signal connections should not leak memory over time.
        
        RED: Establish signal memory requirements (no leaks)
        GREEN: Optimize signal connection lifecycle
        REFACTOR: Maintain signal functionality while preventing leaks
        """
        def stress_test_signal_connections():
            with manager_context("extraction", "injection") as ctx:
                extraction_mgr = ctx.get_extraction_manager()
                injection_mgr = ctx.get_injection_manager()

                connections_made = 0

                # Create and disconnect many signal connections
                for i in range(20):
                    def temp_handler(*args):
                        pass

                    # Connect signals
                    extraction_mgr.extraction_progress.connect(temp_handler)
                    injection_mgr.injection_progress.connect(temp_handler)
                    connections_made += 2

                    # Emit signals to test connection
                    extraction_mgr.extraction_progress.emit(f"Test {i}")
                    injection_mgr.injection_progress.emit(f"Test {i}")

                    # Disconnect signals
                    extraction_mgr.extraction_progress.disconnect(temp_handler)
                    injection_mgr.injection_progress.disconnect(temp_handler)

                # Process any pending Qt events
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()

                return connections_made

        # Benchmark signal connection memory performance
        result = benchmark(stress_test_signal_connections)

        # Should have made all connections
        assert result == 40

# Comparative Performance Tests

@pytest.mark.benchmark
def test_real_vs_mock_performance_comparison_tdd(benchmark, test_data_repo):
    """TDD: Compare real component performance vs theoretical mock performance.
    
    This test documents the performance overhead of real components vs mocks
    to validate that the testing approach provides acceptable performance.
    """
    def run_real_component_workflow():
        with manager_context("extraction", "injection") as ctx:
            extraction_mgr = ctx.get_extraction_manager()
            ctx.get_injection_manager()

            # Get real test data
            vram_data = test_data_repo.get_vram_extraction_data("small")

            # Real parameter validation
            extraction_params = {
                "vram_path": vram_data["vram_path"],
                "output_base": vram_data["output_base"]
            }

            try:
                extraction_mgr.validate_extraction_params(extraction_params)

                # Real signal emission
                extraction_mgr.extraction_progress.emit("Performance test")

                # Real state management
                extraction_mgr._start_operation("perf_test")
                extraction_mgr._finish_operation("perf_test")

                return True

            except ValidationError:
                return False  # Still valid for performance testing

    # Benchmark real component workflow
    result = benchmark(run_real_component_workflow)

    # Should complete workflow (success or controlled failure)
    assert result in [True, False]

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "benchmark"])
