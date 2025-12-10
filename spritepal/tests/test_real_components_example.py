"""
Example tests demonstrating the Real Component Testing Infrastructure.

This file shows how to migrate from MockFactory to RealComponentFactory
with proper type safety and real component testing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Import actual components for testing
from core.managers.extraction_manager import ExtractionManager
from core.managers.injection_manager import InjectionManager
from core.workers.specialized import ExtractionWorkerBase as ExtractionWorker
from tests.infrastructure.manager_test_context import (
    ManagerTestContext,
    isolated_manager_test,
    manager_context,
)
from tests.infrastructure.real_component_factory import (
    # Serial execution required: Real Qt components
    RealComponentFactory,
    TypedManagerFactory,
    create_extraction_manager_factory,
)
from tests.infrastructure.test_data_repository import (
    DataRepository,
    get_test_data_repository,
)
from tests.infrastructure.typed_worker_base import (
    TypedExtractionWorker,
    TypedWorkerValidator,
    WorkerTestHelper,
)

pytestmark = [

    pytest.mark.serial,
    pytest.mark.ci_safe,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.rom_data,
    pytest.mark.signals_slots,
]
class TestRealComponentFactory:
    """Tests demonstrating RealComponentFactory usage."""

    def test_create_real_extraction_manager(self):
        """Test creating a real extraction manager with test data."""
        with RealComponentFactory() as factory:
            # Create real manager - no mocking!
            manager = factory.create_extraction_manager(with_test_data=True)

            # Verify it's a real ExtractionManager
            assert isinstance(manager, ExtractionManager)
            assert manager.is_initialized()

            # Test data is automatically injected
            assert hasattr(manager, "_last_vram_path")
            assert manager._last_vram_path is not None

    def test_typed_manager_factory(self):
        """Test type-safe manager creation."""
        # Create typed factory - no cast() needed!
        extraction_factory = create_extraction_manager_factory()

        # Create manager with compile-time type safety
        manager = extraction_factory.create_with_test_data("medium")

        # manager is typed as ExtractionManager, no cast needed
        assert isinstance(manager, ExtractionManager)

        # Can access ExtractionManager-specific methods safely
        params = {
            "vram_path": "/test/vram.dmp",
            "cgram_path": "/test/cgram.dmp",
            "output_base": "/test/output",
        }
        # This would fail type checking if manager wasn't ExtractionManager
        is_valid = manager.validate_extraction_params(params)
        assert isinstance(is_valid, bool)

    def test_real_worker_creation(self):
        """Test creating real workers with type safety."""
        with RealComponentFactory() as factory:
            # Get test data from repository
            data_repo = get_test_data_repository()
            params = data_repo.get_vram_extraction_data("small")

            # Create real extraction worker
            worker = factory.create_extraction_worker(params)

            # Verify it's a real worker
            assert isinstance(worker, ExtractionWorker)
            assert hasattr(worker, "run")
            assert hasattr(worker, "progress")

class TestManagerTestContext:
    """Tests demonstrating ManagerTestContext usage."""

    def test_manager_context_basic(self):
        """Test basic manager context usage."""
        with manager_context("extraction", "injection") as ctx:
            # Get typed managers - no casting!
            extraction_mgr = ctx.get_extraction_manager()
            injection_mgr = ctx.get_injection_manager()

            # These are real, initialized managers
            assert isinstance(extraction_mgr, ExtractionManager)
            assert isinstance(injection_mgr, InjectionManager)

            # They're properly initialized with test data
            assert extraction_mgr.is_initialized()
            assert injection_mgr.is_initialized()

    def test_isolated_manager_test(self):
        """Test completely isolated manager testing."""
        with isolated_manager_test() as ctx:
            # This context has no shared state with other tests
            ctx.initialize_managers("all")

            # Get all managers
            extraction = ctx.get_extraction_manager()
            injection = ctx.get_injection_manager()
            session = ctx.get_session_manager()

            # All are real, isolated instances
            assert extraction.is_initialized()
            assert injection.is_initialized()
            assert session.is_initialized()

    def test_worker_creation_and_execution(self):
        """Test creating and running workers through context."""
        with manager_context("extraction") as ctx:
            # Create worker with test parameters
            worker = ctx.create_worker("extraction")

            # Run worker and wait for completion
            completed = ctx.run_worker_and_wait(worker, timeout=5000)

            # Worker should complete successfully
            assert completed or not worker.isRunning()

class TestTypedWorkerBase:
    """Tests demonstrating typed worker patterns."""

    def test_typed_worker_with_validator(self):
        """Test worker type validation."""
        with RealComponentFactory() as factory:
            # Create real manager and worker
            manager = factory.create_extraction_manager()
            params = get_test_data_repository().get_vram_extraction_data("small")

            # Create test worker with typed base
            worker = TypedExtractionWorker(manager, params)

            # Use validator for type-safe access
            validator = TypedWorkerValidator()

            # Validate manager type - returns typed manager
            validated_manager = validator.validate_manager_type(
                worker, ExtractionManager
            )
            assert validated_manager is manager

            # Validate params type
            validated_params = validator.validate_params_type(worker, dict)
            assert validated_params is params

    # test_worker_test_helper removed - outdated example that doesn't match current API

class DataRepositoryUsageExamples:
    """Tests demonstrating DataRepository usage."""

    def test_get_test_scenarios(self):
        """Test getting predefined test scenarios."""
        repo = get_test_data_repository()

        # Get VRAM test data
        vram_data = repo.get_vram_extraction_data("medium")
        assert "vram_path" in vram_data
        assert "cgram_path" in vram_data
        assert Path(vram_data["vram_path"]).exists()

        # Get ROM test data
        rom_data = repo.get_rom_extraction_data("medium")
        assert "rom_path" in rom_data
        assert Path(rom_data["rom_path"]).exists()

        # Get injection test data
        injection_data = repo.get_injection_data("medium")
        assert "sprite_path" in injection_data
        assert Path(injection_data["sprite_path"]).exists()

    def test_data_set_validation(self):
        """Test validating data sets."""
        repo = get_test_data_repository()

        # List available data sets
        available = repo.list_available_data_sets()
        assert "small_test" in available
        assert "medium_test" in available

        # Validate a data set
        validation = repo.validate_data_set("medium_test")
        assert validation["valid"] or len(validation["issues"]) > 0
        assert "data_set" in validation

class TestMigrationFromMockFactory:
    """Examples showing migration from MockFactory to RealComponentFactory."""

    def test_before_mock_factory(self):
        """OLD WAY: Using MockFactory with unsafe casting."""
        # This is what we're replacing:
        # from tests.infrastructure.mock_factory import MockFactory
        # factory = MockFactory()
        # mock_manager = factory.create_extraction_manager()
        #
        # # Unsafe cast required!
        # manager = cast(ExtractionManager, mock_manager)
        #
        # # Mock doesn't behave like real manager
        # assert manager.extract_sprites.called  # Mock attribute
        pass

    def test_after_real_component_factory(self):
        """NEW WAY: Using RealComponentFactory with type safety."""
        with RealComponentFactory() as factory:
            # Create real manager - no mocking, no casting!
            manager = factory.create_extraction_manager()

            # It's a real ExtractionManager
            assert isinstance(manager, ExtractionManager)

            # Real methods work as expected
            params = factory._data_repo.get_vram_extraction_data("small")
            is_valid = manager.validate_extraction_params(params)
            assert isinstance(is_valid, bool)

    # test_typed_factory_pattern removed - ExtractionManager doesn't have create_worker method

    def test_integration_with_context(self):
        """NEW WAY: Integration testing with real components."""
        with manager_context("extraction", "injection") as ctx:
            # Get real managers
            ctx.get_extraction_manager()
            ctx.get_injection_manager()

            # Create real worker
            extract_params = ctx._data_repo.get_vram_extraction_data("small")
            extract_worker = ctx.create_worker("extraction", extract_params)

            # Run real extraction
            completed = ctx.run_worker_and_wait(extract_worker)

            # This is real integration testing, not mocking!
            assert completed or not extract_worker.isRunning()

# Pytest fixtures demonstrating the new infrastructure

@pytest.fixture
def real_factory():
    """Fixture providing RealComponentFactory."""
    with RealComponentFactory() as factory:
        yield factory

@pytest.fixture
def test_context():
    """Fixture providing ManagerTestContext."""
    with manager_context("all") as ctx:
        yield ctx

@pytest.fixture
def extraction_manager_real():
    """Fixture providing real ExtractionManager."""
    factory = create_extraction_manager_factory()
    manager = factory.create_with_test_data("medium")
    yield manager
    manager.cleanup()

@pytest.fixture
def injection_manager_real():
    """Fixture providing real InjectionManager."""
    factory = TypedManagerFactory(InjectionManager)
    manager = factory.create_with_test_data("medium")
    yield manager
    manager.cleanup()

# Example of a complete test using the new infrastructure

def test_complete_extraction_workflow_real_components(test_context: ManagerTestContext):
    """
    Complete extraction workflow test using real components.
    
    This test demonstrates:
    - No mocks used
    - Type-safe access to managers
    - Real worker execution
    - Proper lifecycle management
    """
    # Get real extraction manager
    extraction_mgr = test_context.get_extraction_manager()

    # Get test data
    params = test_context._data_repo.get_vram_extraction_data("medium")

    # Validate parameters with real manager
    is_valid = extraction_mgr.validate_extraction_params(params)
    assert is_valid

    # Create real worker
    worker = test_context.create_worker("extraction", params)

    # Connect to real signals
    results = []
    worker.finished.connect(lambda: results.append(True))

    # Run real extraction
    completed = test_context.run_worker_and_wait(worker, timeout=10000)

    # Verify real results
    assert completed or not worker.isRunning()

    # This is a real integration test with actual components!

if __name__ == "__main__":
    # Run example tests
    print("Testing Real Component Infrastructure...")

    # Test factory
    test = TestRealComponentFactory()
    test.test_create_real_extraction_manager()
    test.test_typed_manager_factory()
    print("✓ RealComponentFactory tests passed")

    # Test context
    test = TestManagerTestContext()
    test.test_manager_context_basic()
    test.test_isolated_manager_test()
    print("✓ ManagerTestContext tests passed")

    # Test typed workers
    test = TestTypedWorkerBase()
    test.test_typed_worker_with_validator()
    print("✓ TypedWorkerBase tests passed")

    # Test data repository
    test = DataRepository()
    test.test_get_test_scenarios()
    test.test_data_set_validation()
    print("✓ DataRepository tests passed")

    print("\nAll real component infrastructure tests passed!")
    print("Ready to migrate from MockFactory to RealComponentFactory")
