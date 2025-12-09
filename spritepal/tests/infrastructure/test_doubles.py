"""
Test Doubles for External Dependencies

This module provides test doubles for external dependencies to replace
excessive patch.object usage. Following the principle of mocking at
system boundaries, not internal methods.

Usage:
    # BAD - Mocking internal methods
    with patch.object(manager, '_internal_method'):
        ...

    # GOOD - Test double for external dependency
    manager._hal_compressor = MockHALCompressor()
    manager._rom_file = MockROMFile(test_data)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .mock_hal import MockHALCompressor


class MockROMFile:
    """
    Test double for ROM file operations.
    
    Provides in-memory ROM data without file system dependencies.
    """

    def __init__(self, size: int = 0x400000, data: bytes | None = None):
        """
        Initialize mock ROM file.
        
        Args:
            size: ROM size in bytes (default 4MB)
            data: Optional ROM data, will generate if not provided
        """
        self.size = size
        self.path = "/mock/rom/path.sfc"
        self._data = data if data is not None else self._generate_mock_data()
        self._is_open = False
        self._position = 0  # Track file position for seek/read operations

    def _generate_mock_data(self) -> bytes:
        """Generate deterministic mock ROM data."""
        # Create pattern-based data for testing
        data = bytearray(self.size)

        # Fill with pattern based on position
        for i in range(self.size):
            data[i] = (i % 256)

        # Add some "sprite-like" data at common offsets
        sprite_offsets = [0x200000, 0x210000, 0x220000, 0x240000]
        for offset in sprite_offsets:
            if offset + 0x1000 < self.size:
                # Add recognizable sprite data pattern
                for j in range(0x1000):
                    data[offset + j] = (j % 64) + 128  # Sprite-like values

        return bytes(data)

    def open(self, mode: str = 'rb'):
        """Mock file open, resets position to start."""
        self._is_open = True
        self._position = 0  # Reset position on open
        return self

    def close(self):
        """Mock file close."""
        self._is_open = False

    def read(self, size: int = -1) -> bytes:
        """Mock file read from current position.
        
        Args:
            size: Number of bytes to read, -1 for all remaining data.
            
        Returns:
            Bytes read from current position.
        """
        if not self._is_open:
            raise ValueError("I/O operation on closed file")
        if size == -1:
            result = self._data[self._position:]
            self._position = len(self._data)
        else:
            result = self._data[self._position:self._position + size]
            self._position += len(result)
        return result

    def seek(self, position: int, whence: int = 0) -> int:
        """Mock file seek to position.
        
        Args:
            position: Offset to seek to.
            whence: Reference point (0=start, 1=current, 2=end).
            
        Returns:
            New absolute position.
        """
        if not self._is_open:
            raise ValueError("I/O operation on closed file")
        if whence == 0:  # SEEK_SET
            self._position = position
        elif whence == 1:  # SEEK_CUR
            self._position += position
        elif whence == 2:  # SEEK_END
            self._position = len(self._data) + position
        # Clamp to valid range
        self._position = max(0, min(self._position, len(self._data)))
        return self._position

    def tell(self) -> int:
        """Return current file position."""
        if not self._is_open:
            raise ValueError("I/O operation on closed file")
        return self._position  # Simplified for testing

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

class MockProgressDialog:
    """
    Test double for progress dialogs.
    
    Provides progress tracking without Qt widget overhead.
    """

    def __init__(self, title: str = "Processing", parent=None):
        self.title = title
        self.parent = parent
        self.value = 0
        self.maximum = 100
        self.minimum = 0
        self.visible = False
        self.cancelled = False
        self.label_text = ""

        # Track method calls for verification
        self.call_log = []

    def show(self):
        """Show progress dialog."""
        self.visible = True
        self.call_log.append("show")

    def hide(self):
        """Hide progress dialog."""
        self.visible = False
        self.call_log.append("hide")

    def close(self):
        """Close progress dialog."""
        self.visible = False
        self.call_log.append("close")

    def setValue(self, value: int):
        """Set progress value."""
        self.value = value
        self.call_log.append(f"setValue({value})")

    def setMaximum(self, maximum: int):
        """Set maximum progress value."""
        self.maximum = maximum
        self.call_log.append(f"setMaximum({maximum})")

    def setLabelText(self, text: str):
        """Set progress dialog text."""
        self.label_text = text
        self.call_log.append(f"setLabelText('{text}')")

    def wasCanceled(self) -> bool:
        """Check if dialog was cancelled."""
        return self.cancelled

    def cancel(self):
        """Cancel the progress dialog."""
        self.cancelled = True
        self.call_log.append("cancel")

class MockMessageBox:
    """
    Test double for message boxes.
    
    Provides configurable responses without Qt dialogs.
    """

    # Standard button responses
    class StandardButton:
        Ok = 1
        Cancel = 2
        Yes = 4
        No = 8

    def __init__(self):
        self.call_log = []
        self._responses = {}  # Map method names to responses

    def configure_response(self, method: str, response: Any):
        """Configure response for a specific method."""
        self._responses[method] = response

    def question(self, parent, title: str, text: str,
                buttons=None, default_button=None) -> int:
        """Mock question dialog."""
        self.call_log.append(f"question('{title}', '{text}')")
        return self._responses.get('question', self.StandardButton.Yes)

    def information(self, parent, title: str, text: str,
                   buttons=None, default_button=None) -> int:
        """Mock information dialog."""
        self.call_log.append(f"information('{title}', '{text}')")
        return self._responses.get('information', self.StandardButton.Ok)

    def warning(self, parent, title: str, text: str,
               buttons=None, default_button=None) -> int:
        """Mock warning dialog."""
        self.call_log.append(f"warning('{title}', '{text}')")
        return self._responses.get('warning', self.StandardButton.Ok)

    def critical(self, parent, title: str, text: str,
                buttons=None, default_button=None) -> int:
        """Mock critical dialog."""
        self.call_log.append(f"critical('{title}', '{text}')")
        return self._responses.get('critical', self.StandardButton.Ok)

class MockGalleryWidget:
    """
    Test double for sprite gallery widgets.
    
    Provides gallery functionality without Qt widget overhead.
    """

    def __init__(self):
        self.sprites = []
        self.selected_sprites = []
        self.call_log = []

    def clear(self):
        """Clear all sprites."""
        self.sprites.clear()
        self.selected_sprites.clear()
        self.call_log.append("clear")

    def addSprite(self, sprite_data: dict[str, Any]):
        """Add sprite to gallery."""
        self.sprites.append(sprite_data)
        self.call_log.append(f"addSprite(offset=0x{sprite_data.get('offset', 0):X})")

    def setSprites(self, sprites: list[dict[str, Any]]):
        """Set all sprites at once."""
        self.sprites = sprites.copy()
        self.call_log.append(f"setSprites(count={len(sprites)})")

    def getSelectedSprites(self) -> list[dict[str, Any]]:
        """Get currently selected sprites."""
        return self.selected_sprites.copy()

    def selectSprite(self, index: int):
        """Select sprite by index."""
        if 0 <= index < len(self.sprites):
            if self.sprites[index] not in self.selected_sprites:
                self.selected_sprites.append(self.sprites[index])
            self.call_log.append(f"selectSprite({index})")

    def refresh(self):
        """Refresh gallery display."""
        self.call_log.append("refresh")

    def updateThumbnail(self, sprite_data: dict[str, Any], thumbnail_path: str):
        """Update sprite thumbnail."""
        self.call_log.append(f"updateThumbnail(offset=0x{sprite_data.get('offset', 0):X})")

class MockSpriteFinderExternal:
    """
    Test double for external SpriteFinder operations.
    
    This mocks the parts of SpriteFinder that interact with external
    systems (ROM files, HAL compression) while keeping internal logic real.
    """

    def __init__(self, mock_sprites: list[dict[str, Any | None]] | None = None):
        self.mock_sprites = mock_sprites or []
        self.call_log = []
        self._sprite_index = 0

    def find_sprite_at_offset(self, rom_path: str, offset: int) -> dict[str, Any | None]:
        """Mock finding sprite at specific offset."""
        self.call_log.append(f"find_sprite_at_offset(0x{offset:X})")

        # Return mock sprite if available
        if self._sprite_index < len(self.mock_sprites):
            sprite = self.mock_sprites[self._sprite_index].copy()
            sprite['offset'] = offset  # Update offset to match request
            self._sprite_index += 1
            return sprite

        return None

    def find_sprites_in_range(self, rom_path: str, start_offset: int,
                            end_offset: int) -> list[dict[str, Any]]:
        """Mock finding sprites in range."""
        self.call_log.append(f"find_sprites_in_range(0x{start_offset:X}-0x{end_offset:X})")

        # Return mock sprites within range
        sprites = []
        for sprite in self.mock_sprites:
            if start_offset <= sprite.get('offset', 0) <= end_offset:
                sprites.append(sprite.copy())

        return sprites

    def reset(self):
        """Reset mock state."""
        self._sprite_index = 0
        self.call_log.clear()

class MockCacheManager:
    """
    Test double for cache operations.
    
    Provides in-memory caching without file system dependencies.
    """

    def __init__(self):
        self._cache_data = {}
        self.call_log = []

    def get_cache_path(self, rom_path: str) -> Path:
        """Get cache path for ROM."""
        cache_name = f"cache_{hash(rom_path) % 10000}.json"
        return Path(f"/mock/cache/{cache_name}")

    def save_cache(self, rom_path: str, data: dict[str, Any]):
        """Save cache data."""
        cache_key = str(self.get_cache_path(rom_path))
        self._cache_data[cache_key] = data.copy()
        self.call_log.append(f"save_cache({Path(rom_path).name})")

    def load_cache(self, rom_path: str) -> dict[str, Any | None]:
        """Load cache data."""
        cache_key = str(self.get_cache_path(rom_path))
        self.call_log.append(f"load_cache({Path(rom_path).name})")
        return self._cache_data.get(cache_key)

    def cache_exists(self, rom_path: str) -> bool:
        """Check if cache exists."""
        cache_key = str(self.get_cache_path(rom_path))
        return cache_key in self._cache_data

    def clear_cache(self, rom_path: str | None = None):
        """Clear cache data."""
        if rom_path:
            cache_key = str(self.get_cache_path(rom_path))
            self._cache_data.pop(cache_key, None)
            self.call_log.append(f"clear_cache({Path(rom_path).name})")
        else:
            self._cache_data.clear()
            self.call_log.append("clear_cache(all)")

class DoubleFactory:
    """
    Factory for creating configured test doubles.
    
    Provides common configurations for test scenarios.
    """

    @staticmethod
    def create_hal_compressor(deterministic: bool = True) -> MockHALCompressor:
        """Create configured HAL compressor."""
        compressor = MockHALCompressor()
        compressor.set_deterministic_mode(deterministic)
        return compressor

    @staticmethod
    def create_rom_file(rom_type: str = "standard") -> MockROMFile:
        """Create ROM file with standard test data."""
        if rom_type == "large":
            return MockROMFile(size=0x800000)  # 8MB
        elif rom_type == "small":
            return MockROMFile(size=0x100000)  # 1MB
        else:
            return MockROMFile(size=0x400000)  # 4MB standard

    @staticmethod
    def create_progress_dialog(auto_complete: bool = False) -> MockProgressDialog:
        """Create progress dialog with optional auto-completion."""
        dialog = MockProgressDialog()
        if auto_complete:
            # Configure to simulate automatic completion
            dialog.value = dialog.maximum
        return dialog

    @staticmethod
    def create_message_box(default_responses: dict[str, int] | None = None) -> MockMessageBox:
        """Create message box with default responses."""
        message_box = MockMessageBox()

        if default_responses:
            for method, response in default_responses.items():
                message_box.configure_response(method, response)
        else:
            # Default "Yes" responses for common scenarios
            message_box.configure_response('question', MockMessageBox.StandardButton.Yes)
            message_box.configure_response('information', MockMessageBox.StandardButton.Ok)

        return message_box

    @staticmethod
    def create_gallery_widget(sprite_count: int = 0) -> MockGalleryWidget:
        """Create gallery widget with mock sprites."""
        gallery = MockGalleryWidget()

        # Add mock sprites if requested
        for i in range(sprite_count):
            sprite_data = {
                'offset': 0x200000 + (i * 0x1000),
                'tile_count': 32 + (i % 32),
                'width': 16,
                'height': 16
            }
            gallery.addSprite(sprite_data)

        return gallery

    @staticmethod
    def create_sprite_finder(sprite_scenarios: str = "standard") -> MockSpriteFinderExternal:
        """Create sprite finder with predefined scenarios."""
        if sprite_scenarios == "many":
            mock_sprites = [
                {'offset': 0x200000, 'tile_count': 32, 'width': 16, 'height': 16},
                {'offset': 0x201000, 'tile_count': 64, 'width': 32, 'height': 16},
                {'offset': 0x202000, 'tile_count': 48, 'width': 24, 'height': 16},
            ]
        elif sprite_scenarios == "few":
            mock_sprites = [
                {'offset': 0x200000, 'tile_count': 32, 'width': 16, 'height': 16},
            ]
        elif sprite_scenarios == "none":
            mock_sprites = []
        else:  # "standard"
            mock_sprites = [
                {'offset': 0x200000, 'tile_count': 32, 'width': 16, 'height': 16},
                {'offset': 0x210000, 'tile_count': 64, 'width': 32, 'height': 16},
            ]

        return MockSpriteFinderExternal(mock_sprites)

# Convenience functions for common test double setups
def setup_hal_mocking(manager_instance, deterministic: bool = True):
    """Set up HAL mocking on a manager instance."""
    manager_instance._hal_compressor = DoubleFactory.create_hal_compressor(deterministic)


def setup_rom_mocking(manager_instance, rom_type: str = "standard"):
    """Set up ROM file mocking on a manager instance."""
    manager_instance._rom_file = DoubleFactory.create_rom_file(rom_type)


def setup_ui_mocking(instance, components: list[str]):
    """Set up UI component mocking on an instance."""
    factory = DoubleFactory()

    for component in components:
        if component == "progress_dialog":
            instance.progress_dialog = factory.create_progress_dialog()
        elif component == "gallery_widget":
            instance.gallery_widget = factory.create_gallery_widget()
        elif component == "message_box":
            # For global message box usage
            import builtins
            builtins.QMessageBox = factory.create_message_box()
