"""
DataRepository: Centralized real test data management.

Provides consistent access to real test data files (VRAM, ROM, CGRAM, etc.)
instead of creating temporary mock data in each test. This improves test
reliability and ensures tests use realistic data patterns.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.no_qt,
    pytest.mark.rom_data,
    pytest.mark.ci_safe,
    pytest.mark.slow,
]

@dataclass
class DataSet:
    """Represents a complete set of test data for extraction/injection testing."""
    name: str
    description: str
    vram_path: str | None = None
    cgram_path: str | None = None
    oam_path: str | None = None
    rom_path: str | None = None
    sprite_images: list[str] = None
    metadata_files: list[str] = None

    def __post_init__(self):
        if self.sprite_images is None:
            self.sprite_images = []
        if self.metadata_files is None:
            self.metadata_files = []

class DataRepository:
    """
    Centralized repository for test data management.

    This repository provides:
    - Consistent access to real test data files
    - Creation of realistic test data when real files aren't available
    - Temporary file management with proper cleanup
    - Test data validation and integrity checking
    """

    def __init__(self, base_test_data_dir: str | None = None):
        """
        Initialize the test data repository.

        Args:
            base_test_data_dir: Base directory for test data files
        """
        # Set up base directories
        if base_test_data_dir:
            self.base_dir = Path(base_test_data_dir)
        else:
            # Look for test data in standard locations
            current_dir = Path(__file__).parent.parent.parent
            potential_dirs = [
                current_dir / "test_data",
                current_dir / "archive" / "obsolete_legacy",
                current_dir.parent / "archive" / "obsolete_test_images",
            ]

            self.base_dir = None
            for dir_path in potential_dirs:
                if dir_path.exists():
                    self.base_dir = dir_path
                    break

            if self.base_dir is None:
                # Create temporary test data directory
                self.base_dir = Path(tempfile.mkdtemp(prefix="spritepal_test_data_"))

        # Track temporary files for cleanup
        self._temp_files: list[str] = []
        self._temp_dirs: list[str] = []

        # Initialize data sets
        self._data_sets: dict[str, DataSet] = {}
        self._initialize_data_sets()

    def _initialize_data_sets(self) -> None:
        """Initialize available test data sets."""
        # Real data sets (if available)
        self._register_real_data_sets()

        # Generated data sets (always available)
        self._register_generated_data_sets()

    def _register_real_data_sets(self) -> None:
        """Register real test data sets if available."""
        # Look for real VRAM dumps
        vram_candidates = [
            self.base_dir / "VRAM.dmp",
            self.base_dir / "Cave.SnesVideoRam.dmp",
        ]

        cgram_candidates = [
            self.base_dir / "CGRAM.dmp",
            self.base_dir / "Cave.SnesCgRam.dmp",
        ]

        rom_candidates = [
            self.base_dir / "kirby.sfc",
            self.base_dir / "test.sfc",
        ]

        # Find available real data
        real_vram = self._find_existing_file(vram_candidates)
        real_cgram = self._find_existing_file(cgram_candidates)
        real_rom = self._find_existing_file(rom_candidates)

        if real_vram or real_cgram or real_rom:
            self._data_sets["real_kirby"] = DataSet(
                name="real_kirby",
                description="Real Kirby Super Star data files",
                vram_path=str(real_vram) if real_vram else None,
                cgram_path=str(real_cgram) if real_cgram else None,
                rom_path=str(real_rom) if real_rom else None,
            )

    def _register_generated_data_sets(self) -> None:
        """Register generated test data sets."""
        # Small test data set
        self._data_sets["small_test"] = DataSet(
            name="small_test",
            description="Small generated test data for unit tests"
        )

        # Medium test data set
        self._data_sets["medium_test"] = DataSet(
            name="medium_test",
            description="Medium generated test data for integration tests"
        )

        # Comprehensive test data set
        self._data_sets["comprehensive_test"] = DataSet(
            name="comprehensive_test",
            description="Comprehensive generated test data for full workflow testing"
        )

    def get_data_set(self, name: str) -> DataSet | None:
        """
        Get a test data set by name.

        Args:
            name: Name of the data set

        Returns:
            TestDataSet instance or None if not found
        """
        if name not in self._data_sets:
            return None

        data_set = self._data_sets[name]

        # Generate files if they don't exist
        self._ensure_data_set_files(data_set)

        return data_set

    def get_vram_extraction_data(self, size: str = "medium") -> dict[str, Any]:
        """
        Get VRAM extraction test data.

        Args:
            size: Size of test data ("small", "medium", "comprehensive")

        Returns:
            Dictionary with VRAM extraction parameters
        """
        data_set_name = f"{size}_test"
        if size == "real" and "real_kirby" in self._data_sets:
            data_set_name = "real_kirby"

        data_set = self.get_data_set(data_set_name)
        if not data_set:
            raise ValueError(f"Data set '{data_set_name}' not available")

        return {
            "vram_path": data_set.vram_path,
            "cgram_path": data_set.cgram_path,
            "oam_path": data_set.oam_path,
            "output_base": self._get_temp_output_path("extraction"),
            "vram_offset": 0xC000,
            "sprite_size": (8, 8),
            "create_metadata": True,
            "create_grayscale": True,
        }

    def get_rom_extraction_data(self, size: str = "medium") -> dict[str, Any]:
        """
        Get ROM extraction test data.

        Args:
            size: Size of test data ("small", "medium", "comprehensive")

        Returns:
            Dictionary with ROM extraction parameters
        """
        data_set_name = f"{size}_test"
        if size == "real" and "real_kirby" in self._data_sets:
            data_set_name = "real_kirby"

        data_set = self.get_data_set(data_set_name)
        if not data_set:
            raise ValueError(f"Data set '{data_set_name}' not available")

        return {
            "rom_path": data_set.rom_path,
            "offset": 0x200000,
            "output_base": self._get_temp_output_path("rom_extraction"),
            "sprite_size": (16, 16),
            "create_metadata": True,
        }

    def get_injection_data(self, size: str = "medium") -> dict[str, Any]:
        """
        Get injection test data.

        Args:
            size: Size of test data ("small", "medium", "comprehensive")

        Returns:
            Dictionary with injection test data
        """
        data_set = self.get_data_set(f"{size}_test")
        if not data_set:
            raise ValueError(f"Data set '{size}_test' not available")

        # Create test sprite if needed
        sprite_path = self._create_test_sprite(f"{size}_sprite")

        return {
            "sprite_path": sprite_path,
            "vram_input": data_set.vram_path,
            "vram_output": self._get_temp_output_path("vram_injection.dmp"),
            "rom_input": data_set.rom_path,
            "rom_output": self._get_temp_output_path("rom_injection.sfc"),
            "vram_offset": 0xC000,
            "rom_offset": 0x200000,
        }

    def _ensure_data_set_files(self, data_set: DataSet) -> None:
        """Ensure all files in a data set exist, creating them if necessary."""
        if data_set.name.endswith("_test"):
            # Generate files for test data sets
            self._generate_test_files(data_set)

    def _generate_test_files(self, data_set: DataSet) -> None:
        """Generate test files for a data set."""
        size_map = {
            "small_test": {"vram_size": 0x10000, "rom_size": 0x100000},  # 64KB VRAM (minimum required), 1MB ROM
            "medium_test": {"vram_size": 0x10000, "rom_size": 0x400000},  # 64KB VRAM, 4MB ROM
            "comprehensive_test": {"vram_size": 0x20000, "rom_size": 0x600000},  # 128KB VRAM, 6MB ROM
        }

        config = size_map.get(data_set.name, size_map["medium_test"])

        # Generate VRAM file
        if not data_set.vram_path:
            data_set.vram_path = self._create_vram_file(
                f"{data_set.name}_vram.dmp",
                config["vram_size"]
            )

        # Generate CGRAM file
        if not data_set.cgram_path:
            data_set.cgram_path = self._create_cgram_file(f"{data_set.name}_cgram.dmp")

        # Generate OAM file
        if not data_set.oam_path:
            data_set.oam_path = self._create_oam_file(f"{data_set.name}_oam.dmp")

        # Generate ROM file
        if not data_set.rom_path:
            data_set.rom_path = self._create_rom_file(
                f"{data_set.name}_rom.sfc",
                config["rom_size"]
            )

    def _create_vram_file(self, filename: str, size: int) -> str:
        """Create a realistic VRAM file with sprite-like data patterns."""
        filepath = self._get_temp_file_path(filename)

        vram_data = bytearray(size)

        # Add realistic sprite data at sprite offset
        sprite_offset = 0xC000 if size >= 0xC000 + 0x1000 else 0
        sprite_size = min(0x1000, size - sprite_offset)

        for i in range(sprite_size):
            # Create 4bpp sprite data pattern
            vram_data[sprite_offset + i] = self._generate_sprite_byte(i)

        with open(filepath, "wb") as f:
            f.write(vram_data)

        self._temp_files.append(filepath)
        return filepath

    def _create_cgram_file(self, filename: str) -> str:
        """Create a realistic CGRAM file with palette data."""
        filepath = self._get_temp_file_path(filename)

        cgram_data = bytearray(512)  # 512 bytes for CGRAM

        # Generate realistic palette colors (BGR555 format)
        palette_colors = [
            0x0000,  # Black
            0x001F,  # Red
            0x03E0,  # Green
            0x7C00,  # Blue
            0x7FFF,  # White
            0x39CE,  # Gray
            0x4631,  # Brown
            0x7FE0,  # Cyan
        ]

        # Fill sprite palettes (8-15)
        for pal_idx in range(8, 16):
            base_offset = pal_idx * 32  # 16 colors * 2 bytes
            for color_idx, color in enumerate(palette_colors):
                if base_offset + color_idx * 2 + 1 < len(cgram_data):
                    cgram_data[base_offset + color_idx * 2] = color & 0xFF
                    cgram_data[base_offset + color_idx * 2 + 1] = (color >> 8) & 0xFF

        with open(filepath, "wb") as f:
            f.write(cgram_data)

        self._temp_files.append(filepath)
        return filepath

    def _create_oam_file(self, filename: str) -> str:
        """Create a realistic OAM file."""
        filepath = self._get_temp_file_path(filename)

        # OAM data (544 bytes)
        oam_data = bytearray(544)

        # Add some realistic OAM entries
        for i in range(min(128, len(oam_data) // 4)):
            base = i * 4
            oam_data[base] = (i * 8) % 256      # X position
            oam_data[base + 1] = (i * 8) % 240  # Y position
            oam_data[base + 2] = i % 256        # Tile number
            oam_data[base + 3] = 0x20 | (i % 8) # Attributes (palette, etc.)

        with open(filepath, "wb") as f:
            f.write(oam_data)

        self._temp_files.append(filepath)
        return filepath

    def _create_rom_file(self, filename: str, size: int) -> str:
        """Create a realistic ROM file with header and sprite data."""
        filepath = self._get_temp_file_path(filename)

        rom_data = bytearray(size)

        # Add ROM header
        header_offset = 0x7FC0
        if size > header_offset + 32:
            rom_data[header_offset:header_offset + 21] = b"SPRITEPAL TEST ROM   "
            rom_data[header_offset + 21] = 0x30  # ROM type
            rom_data[header_offset + 22] = 0x0C  # ROM size
            rom_data[header_offset + 23] = 0x00  # SRAM size

        # Add sprite data at common offsets
        sprite_offsets = [0x200000, 0x300000, 0x380000]
        for offset in sprite_offsets:
            if offset + 0x800 < size:
                for i in range(0x800):  # 2KB of sprite data
                    rom_data[offset + i] = self._generate_sprite_byte(i)

        with open(filepath, "wb") as f:
            f.write(rom_data)

        self._temp_files.append(filepath)
        return filepath

    def _create_test_sprite(self, name: str) -> str:
        """Create a test sprite image."""
        filepath = self._get_temp_file_path(f"{name}.png")

        # Create 64x64 indexed sprite
        sprite = Image.new("P", (64, 64), 0)

        # Create simple palette
        palette = []
        for i in range(16):
            # Generate grayscale palette
            gray_value = i * 16
            palette.extend([gray_value, gray_value, gray_value])

        # Fill rest with black
        for i in range(16, 256):
            palette.extend([0, 0, 0])

        sprite.putpalette(palette)

        # Create sprite pattern
        pixels = []
        for y in range(64):
            for x in range(64):
                # Create a checkerboard-like pattern
                value = ((x // 8) + (y // 8)) % 16
                pixels.append(value)

        sprite.putdata(pixels)
        sprite.save(filepath)

        self._temp_files.append(filepath)
        return filepath

    def _generate_sprite_byte(self, index: int) -> int:
        """Generate a realistic sprite data byte."""
        # Create 4bpp tile data pattern
        return ((index * 7) ^ (index >> 2)) % 256

    def _find_existing_file(self, candidates: list[Path]) -> Path | None:
        """Find the first existing file from a list of candidates."""
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _get_temp_file_path(self, filename: str) -> str:
        """Get path for a temporary file."""
        temp_dir = tempfile.mkdtemp(prefix="spritepal_test_")
        self._temp_dirs.append(temp_dir)
        return os.path.join(temp_dir, filename)

    def _get_temp_output_path(self, name: str) -> str:
        """Get path for temporary output."""
        temp_dir = tempfile.mkdtemp(prefix="spritepal_output_")
        self._temp_dirs.append(temp_dir)
        return os.path.join(temp_dir, name)

    def list_available_data_sets(self) -> list[str]:
        """List all available data set names."""
        return list(self._data_sets.keys())

    def validate_data_set(self, name: str) -> dict[str, Any]:
        """
        Validate a data set and return status information.

        Args:
            name: Name of data set to validate

        Returns:
            Dictionary with validation results
        """
        if name not in self._data_sets:
            return {"valid": False, "error": f"Data set '{name}' not found"}

        data_set = self._data_sets[name]
        issues = []

        # Check file existence
        if data_set.vram_path and not os.path.exists(data_set.vram_path):
            issues.append(f"VRAM file missing: {data_set.vram_path}")

        if data_set.cgram_path and not os.path.exists(data_set.cgram_path):
            issues.append(f"CGRAM file missing: {data_set.cgram_path}")

        if data_set.rom_path and not os.path.exists(data_set.rom_path):
            issues.append(f"ROM file missing: {data_set.rom_path}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "data_set": {
                "name": data_set.name,
                "description": data_set.description,
                "has_vram": data_set.vram_path is not None,
                "has_cgram": data_set.cgram_path is not None,
                "has_rom": data_set.rom_path is not None,
            }
        }

    def cleanup(self) -> None:
        """Clean up all temporary files and directories."""
        # Remove temporary files
        for filepath in self._temp_files:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception:
                pass  # Ignore cleanup errors

        # Remove temporary directories
        for dirpath in self._temp_dirs:
            try:
                if os.path.exists(dirpath):
                    shutil.rmtree(dirpath)
            except Exception:
                pass  # Ignore cleanup errors

        self._temp_files.clear()
        self._temp_dirs.clear()

class _DataRepositorySingleton:
    """Singleton holder for DataRepository."""
    _instance: DataRepository | None = None

    @classmethod
    def get(cls) -> DataRepository:
        """Get the global test data repository instance."""
        if cls._instance is None:
            cls._instance = DataRepository()
        return cls._instance

    @classmethod
    def cleanup(cls) -> None:
        """Clean up the global test data repository."""
        if cls._instance is not None:
            cls._instance.cleanup()
            cls._instance = None

def get_test_data_repository() -> DataRepository:
    """Get the global test data repository instance."""
    return _DataRepositorySingleton.get()

def cleanup_test_data_repository() -> None:
    """Clean up the global test data repository."""
    _DataRepositorySingleton.cleanup()


def get_isolated_data_repository(tmp_path: Path) -> DataRepository:
    """Get an isolated DataRepository instance backed by tmp_path.

    Unlike the singleton from get_test_data_repository(), this returns a
    fresh instance with all generated files stored in the test's tmp_path
    directory. This provides true parallel isolation:
    - Each test gets its own DataRepository
    - Generated files don't conflict between tests
    - Auto-cleaned by pytest's tmp_path fixture

    Args:
        tmp_path: pytest tmp_path fixture for this test

    Returns:
        A new DataRepository instance using tmp_path as its base directory

    Example:
        def test_extraction(tmp_path):
            repo = get_isolated_data_repository(tmp_path)
            data = repo.get_vram_extraction_data("small")
            # Files are stored in tmp_path, auto-cleaned after test
    """
    return DataRepository(base_test_data_dir=str(tmp_path))


# Convenience functions
def get_vram_test_data(size: str = "medium") -> dict[str, Any]:
    """Get VRAM test data."""
    return get_test_data_repository().get_vram_extraction_data(size)

def get_rom_test_data(size: str = "medium") -> dict[str, Any]:
    """Get ROM test data."""
    return get_test_data_repository().get_rom_extraction_data(size)

def get_injection_test_data(size: str = "medium") -> dict[str, Any]:
    """Get injection test data."""
    return get_test_data_repository().get_injection_data(size)
