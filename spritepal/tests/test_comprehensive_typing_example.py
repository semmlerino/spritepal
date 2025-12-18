"""
Comprehensive example of proper type annotations for test files.

This module demonstrates best practices for typing in pytest test files,
including fixtures, parametrized tests, mock objects, and Qt components.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias
from unittest.mock import Mock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from tests.infrastructure.test_protocols import (
        MockExtractionManagerProtocol,
        MockMainWindowProtocol,
        MockQtBotProtocol,
    )

# Type aliases for clarity
TestDataDict: TypeAlias = dict[str, Any]
ParameterSet: TypeAlias = tuple[Any, ...]

# Module-level marker to allow registry state (these tests don't use managers)
pytestmark = pytest.mark.allows_registry_state


class TestComprehensiveTypingExample:
    """Demonstrate comprehensive typing patterns in test classes."""

    @pytest.fixture
    def sample_test_data(self) -> TestDataDict:
        """Provide sample test data with proper typing."""
        return {
            "vram_size": 0x10000,
            "sprite_count": 8,
            "palette_entries": 256,
            "tile_dimensions": (8, 8),
            "output_formats": ["png", "bmp"],
        }

    @pytest.fixture
    def mock_main_window(self) -> MockMainWindowProtocol:
        """Create a properly typed mock main window."""
        mock = Mock()
        mock.extract_requested = Mock()
        mock.extract_requested.emit = Mock()
        return mock  # type: ignore[return-value]

    @pytest.fixture
    def real_extraction_manager(self) -> MockExtractionManagerProtocol:
        """Create a properly typed mock extraction manager."""
        mock = Mock()
        mock.extract_sprites = Mock(return_value=True)
        mock.validate_extraction_params = Mock(return_value=True)
        return mock  # type: ignore[return-value]

    @pytest.fixture
    def test_file_factory(self, tmp_path: Path) -> Callable[[bytes, str], Path]:
        """Factory for creating test files with proper typing."""
        def _create_file(content: bytes, filename: str) -> Path:
            file_path = tmp_path / filename
            file_path.write_bytes(content)
            return file_path
        return _create_file

    @pytest.fixture
    def widget_setup(
        self,
        qapp: QApplication,
        qtbot: MockQtBotProtocol,
    ) -> Iterator[tuple[QApplication, MockQtBotProtocol]]:
        """Set up Qt widgets with proper cleanup and typing."""
        # Setup code here
        yield qapp, qtbot
        # Cleanup code here

    @pytest.mark.parametrize(
        ("input_size", "expected_tiles", "format_type"),
        [
            (0x1000, 32, "4bpp"),
            (0x2000, 64, "4bpp"),
            (0x4000, 128, "8bpp"),
        ],
        ids=["small-4bpp", "medium-4bpp", "large-8bpp"],
    )
    def test_parametrized_with_types(
        self,
        input_size: int,
        expected_tiles: int,
        format_type: str,
        sample_test_data: TestDataDict,
    ) -> None:
        """Test parametrized function with proper type annotations."""
        assert input_size > 0
        assert expected_tiles > 0
        assert format_type in ("4bpp", "8bpp")
        assert sample_test_data["vram_size"] >= input_size

    @pytest.mark.parametrize(
        "test_params",
        [
            {"offset": 0x1000, "size": 0x800, "valid": True},
            {"offset": 0x2000, "size": 0x1000, "valid": True},
            {"offset": 0xFFFF, "size": 0x1000, "valid": False},
        ],
        ids=["valid-small", "valid-large", "invalid-overflow"],
    )
    def test_dict_parameters_with_types(
        self,
        test_params: TestDataDict,
        real_extraction_manager: MockExtractionManagerProtocol,
    ) -> None:
        """Test dictionary parameters with proper type annotations."""
        offset: int = test_params["offset"]
        size: int = test_params["size"]
        valid: bool = test_params["valid"]

        # Mock manager validation
        real_extraction_manager.validate_extraction_params.return_value = valid

        # Test the validation
        result = real_extraction_manager.validate_extraction_params({
            "offset": offset,
            "size": size,
        })
        assert result == valid

    def test_mock_objects_with_protocols(
        self,
        mock_main_window: MockMainWindowProtocol,
        real_extraction_manager: MockExtractionManagerProtocol,
    ) -> None:
        """Test mock objects using protocol types."""
        # Test signal emission
        mock_main_window.extract_requested.emit("test_request")
        mock_main_window.extract_requested.emit.assert_called_with("test_request")

        # Test manager methods
        real_extraction_manager.extract_sprites.return_value = True
        result = real_extraction_manager.extract_sprites({})
        assert result is True

    @pytest.mark.qt_real
    def test_real_qt_components_with_types(
        self,
        qapp: QApplication,
        qtbot: MockQtBotProtocol,
        widget_setup: tuple[QApplication, MockQtBotProtocol],
    ) -> None:
        """Test real Qt components with proper typing."""
        app, bot = widget_setup
        assert app is not None
        assert app == qapp

        # Widget creation with proper typing
        from PySide6.QtWidgets import QPushButton

        button = QPushButton("Test")
        bot.addWidget(button)

        # Type-safe property access
        button.setText("Updated Text")
        assert button.text() == "Updated Text"

    def test_file_operations_with_types(
        self,
        test_file_factory: Callable[[bytes, str], Path],
        tmp_path: Path,
    ) -> None:
        """Test file operations with proper typing."""
        # Create test file
        test_content = b"test sprite data"
        test_file = test_file_factory(test_content, "test.dmp")

        # Verify file exists and has correct content
        assert test_file.exists()
        assert test_file.read_bytes() == test_content
        assert test_file.parent == tmp_path

    def test_context_managers_with_types(
        self,
        real_extraction_manager: MockExtractionManagerProtocol,
    ) -> None:
        """Test context managers with proper typing."""
        with patch.object(
            real_extraction_manager,
            "extract_sprites",
            return_value=True
        ) as mock_extract:
            result = real_extraction_manager.extract_sprites({"test": "data"})
            assert result is True
            mock_extract.assert_called_once_with({"test": "data"})

    @pytest.mark.parametrize(
        "error_scenarios",
        [
            FileNotFoundError("Test file not found"),
            ValueError("Invalid sprite format"),
            RuntimeError("Extraction failed"),
        ],
        ids=["file-not-found", "invalid-format", "extraction-error"],
    )
    def test_exception_handling_with_types(
        self,
        error_scenarios: Exception,
        real_extraction_manager: MockExtractionManagerProtocol,
    ) -> None:
        """Test exception handling with proper typing."""
        # Configure mock to raise specific exception
        real_extraction_manager.extract_sprites.side_effect = error_scenarios

        # Test that the exception is raised
        with pytest.raises(type(error_scenarios)):
            real_extraction_manager.extract_sprites({})

    def test_collections_with_types(
        self,
        sample_test_data: TestDataDict,
    ) -> None:
        """Test working with collections using proper typing."""
        # Sequence operations
        formats: list[str] = sample_test_data["output_formats"]
        assert isinstance(formats, list)
        assert len(formats) == 2
        assert "png" in formats

        # Tuple operations
        dimensions: tuple[int, int] = sample_test_data["tile_dimensions"]
        width, height = dimensions
        assert width == 8
        assert height == 8

    @pytest.fixture
    def async_test_data(self) -> Iterator[dict[str, Any]]:
        """Demonstrate async fixture patterns with proper typing."""
        data = {"async_operation": "setup"}
        yield data
        # Cleanup async resources here

    def test_fixture_dependencies_with_types(
        self,
        sample_test_data: TestDataDict,
        async_test_data: dict[str, Any],
        mock_main_window: MockMainWindowProtocol,
    ) -> None:
        """Test fixture dependencies with proper typing."""
        assert sample_test_data["vram_size"] > 0
        assert async_test_data["async_operation"] == "setup"
        assert hasattr(mock_main_window, "extract_requested")

# Module-level fixture for standalone tests
@pytest.fixture
def real_extraction_manager() -> MockExtractionManagerProtocol:
    """Create a properly typed mock extraction manager for standalone tests."""
    mock = Mock()
    mock.extract_sprites = Mock(return_value=True)
    mock.validate_extraction_params = Mock(return_value=True)
    return mock  # type: ignore[return-value]


# Standalone test functions with proper typing
def test_standalone_function_with_types(
    real_extraction_manager: MockExtractionManagerProtocol,
) -> None:
    """Test standalone function with proper type annotations."""
    real_extraction_manager.validate_extraction_params.return_value = True
    result = real_extraction_manager.validate_extraction_params({})
    assert result is True

@pytest.mark.parametrize(
    ("input_data", "expected_output"),
    [
        (b"\x00" * 32, 32),
        (b"\xFF" * 64, 64),
        (bytearray(range(128)), 128),
    ],
    ids=["zeros", "ones", "sequence"],
)
def test_standalone_parametrized_with_types(
    input_data: bytes | bytearray,
    expected_output: int,
) -> None:
    """Test standalone parametrized function with proper typing."""
    assert len(input_data) == expected_output
    assert isinstance(input_data, (bytes, bytearray))

# Type-safe helper functions
def create_test_sprite_data(
    size: int,
    pattern: int = 0x55,
) -> bytearray:
    """Create test sprite data with proper typing."""
    return bytearray([pattern] * size)

def validate_sprite_format(
    data: bytes | bytearray,
    expected_size: int,
) -> bool:
    """Validate sprite format with proper typing."""
    return len(data) == expected_size and all(isinstance(b, int) for b in data)

# Demonstrate Protocol usage in test helpers
class TestSpriteValidator:
    """Test helper class using protocols."""

    def validate_sprite_data(
        self,
        data: bytes | bytearray,
        validator: Callable[[bytes | bytearray], bool],
    ) -> bool:
        """Validate sprite data using a validator protocol."""
        return validator(data)

# Example test using the helper class
def test_protocol_usage_with_types() -> None:
    """Test protocol usage with proper typing."""
    validator = TestSpriteValidator()
    test_data = create_test_sprite_data(32)

    def simple_validator(data: bytes | bytearray) -> bool:
        return len(data) > 0

    assert validator.validate_sprite_data(test_data, simple_validator)
