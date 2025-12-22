"""Tests for manager initialization order validation.

These tests verify that MANAGED_CLASSES order satisfies MANAGER_DEPENDENCIES,
and that the validation logic correctly detects invalid orderings.
"""

from __future__ import annotations

import pytest

from core.managers.registry import (
    MANAGER_DEPENDENCIES,
    MANAGER_TO_PROTOCOLS,
    InitializationError,
    ManagerRegistry,
    _ensure_dependency_maps,
    _get_protocols_for_manager,
    validate_manager_order,
)


class TestDependencyMapsInitialization:
    """Tests for lazy initialization of dependency maps."""

    def test_dependency_maps_are_populated_after_ensure(self) -> None:
        """_ensure_dependency_maps populates the global dicts."""
        _ensure_dependency_maps()

        # Should have entries for all managers in MANAGED_CLASSES
        for manager_class in ManagerRegistry.MANAGED_CLASSES:
            assert manager_class in MANAGER_DEPENDENCIES, (
                f"{manager_class.__name__} missing from MANAGER_DEPENDENCIES"
            )
            assert manager_class in MANAGER_TO_PROTOCOLS, (
                f"{manager_class.__name__} missing from MANAGER_TO_PROTOCOLS"
            )

    def test_application_state_manager_has_no_dependencies(self) -> None:
        """ApplicationStateManager should have no dependencies (always first)."""
        _ensure_dependency_maps()

        from core.managers.application_state_manager import ApplicationStateManager

        deps = MANAGER_DEPENDENCIES.get(ApplicationStateManager, [])
        assert deps == [], (
            f"ApplicationStateManager should have no dependencies, but has {deps}"
        )

    def test_core_operations_manager_depends_on_state_protocol(self) -> None:
        """CoreOperationsManager depends on ApplicationStateManagerProtocol."""
        _ensure_dependency_maps()

        from core.managers.core_operations_manager import CoreOperationsManager
        from core.protocols.manager_protocols import ApplicationStateManagerProtocol

        deps = MANAGER_DEPENDENCIES.get(CoreOperationsManager, [])
        assert ApplicationStateManagerProtocol in deps, (
            "CoreOperationsManager should depend on ApplicationStateManagerProtocol"
        )


class TestGetProtocolsForManager:
    """Tests for _get_protocols_for_manager helper."""

    def test_application_state_manager_provides_its_protocol(self) -> None:
        """ApplicationStateManager registers ApplicationStateManagerProtocol."""
        from core.managers.application_state_manager import ApplicationStateManager
        from core.protocols.manager_protocols import ApplicationStateManagerProtocol

        protocols = _get_protocols_for_manager(ApplicationStateManager)
        assert ApplicationStateManagerProtocol in protocols

    def test_core_operations_manager_provides_extraction_and_injection(self) -> None:
        """CoreOperationsManager registers both extraction and injection protocols."""
        from core.managers.core_operations_manager import CoreOperationsManager
        from core.protocols.manager_protocols import (
            ExtractionManagerProtocol,
            InjectionManagerProtocol,
        )

        protocols = _get_protocols_for_manager(CoreOperationsManager)
        assert ExtractionManagerProtocol in protocols
        assert InjectionManagerProtocol in protocols

    def test_unknown_manager_returns_empty_list(self) -> None:
        """Unknown manager class returns empty protocol list."""

        class UnknownManager:
            pass

        protocols = _get_protocols_for_manager(UnknownManager)
        assert protocols == []


class TestValidateManagerOrder:
    """Tests for validate_manager_order function."""

    def test_current_managed_classes_order_is_valid(self) -> None:
        """The current MANAGED_CLASSES order satisfies all dependencies."""
        # Should not raise
        validate_manager_order()

    def test_valid_order_with_explicit_list(self) -> None:
        """Passing a valid explicit list does not raise."""
        from core.managers.application_state_manager import ApplicationStateManager
        from core.managers.core_operations_manager import CoreOperationsManager

        # Same as MANAGED_CLASSES - should pass
        valid_order = [ApplicationStateManager, CoreOperationsManager]
        validate_manager_order(valid_order)

    def test_invalid_order_core_before_state_raises(self) -> None:
        """Putting CoreOperationsManager before ApplicationStateManager raises."""
        from core.managers.application_state_manager import ApplicationStateManager
        from core.managers.core_operations_manager import CoreOperationsManager

        invalid_order = [CoreOperationsManager, ApplicationStateManager]

        with pytest.raises(InitializationError) as exc_info:
            validate_manager_order(invalid_order)

        # Error message should mention the missing dependency
        assert "CoreOperationsManager" in str(exc_info.value)
        assert "ApplicationStateManagerProtocol" in str(exc_info.value)

    def test_missing_dependency_declaration_raises(self) -> None:
        """Manager not in MANAGER_DEPENDENCIES raises InitializationError."""

        class UndeclaredManager:
            pass

        invalid_order = [UndeclaredManager]

        with pytest.raises(InitializationError) as exc_info:
            validate_manager_order(invalid_order)

        assert "UndeclaredManager" in str(exc_info.value)
        assert "MANAGER_DEPENDENCIES" in str(exc_info.value)

    def test_empty_list_is_valid(self) -> None:
        """Empty manager list is valid (no dependencies to check)."""
        validate_manager_order([])


class TestInitializationErrorException:
    """Tests for InitializationError exception class."""

    def test_initialization_error_is_manager_error(self) -> None:
        """InitializationError inherits from ManagerError."""
        from core.exceptions import ManagerError

        assert issubclass(InitializationError, ManagerError)

    def test_initialization_error_can_be_raised_with_message(self) -> None:
        """InitializationError can be raised with a custom message."""
        msg = "Test error message"
        with pytest.raises(InitializationError, match=msg):
            raise InitializationError(msg)


class TestManagerDependencyDocumentation:
    """Tests that verify dependency documentation is complete."""

    def test_all_managed_classes_have_dependency_entry(self) -> None:
        """Every manager in MANAGED_CLASSES has a MANAGER_DEPENDENCIES entry."""
        _ensure_dependency_maps()

        for manager_class in ManagerRegistry.MANAGED_CLASSES:
            assert manager_class in MANAGER_DEPENDENCIES, (
                f"{manager_class.__name__} is in MANAGED_CLASSES but not in "
                f"MANAGER_DEPENDENCIES. Add it to document its dependencies."
            )

    def test_all_managed_classes_have_protocol_entry(self) -> None:
        """Every manager in MANAGED_CLASSES has a MANAGER_TO_PROTOCOLS entry."""
        _ensure_dependency_maps()

        for manager_class in ManagerRegistry.MANAGED_CLASSES:
            assert manager_class in MANAGER_TO_PROTOCOLS, (
                f"{manager_class.__name__} is in MANAGED_CLASSES but not in "
                f"MANAGER_TO_PROTOCOLS. Add it to document its protocols."
            )
