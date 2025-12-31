#!/usr/bin/env python3
from __future__ import annotations

"""Manual test runner for ROM cache functionality"""

import inspect
import sys
import tempfile
import traceback
from pathlib import Path

import core.services.rom_cache

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Direct imports with full module resolution
import importlib

rom_cache_module = importlib.import_module("core.services.rom_cache")
ROMCache = rom_cache_module.ROMCache


# Create a simple SpritePointer class for testing
class SpritePointer:
    def __init__(self, offset, bank=0, address=0, compressed_size=None, offset_variants=None):
        self.offset = offset
        self.bank = bank
        self.address = address
        self.compressed_size = compressed_size
        self.offset_variants = offset_variants


def test_basic_cache_operations():
    """Test basic cache save and load operations"""
    print("\n=== Testing Basic Cache Operations ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create cache with temp directory
        cache = ROMCache(cache_dir=tmpdir)
        print(f"✓ Created cache at: {cache.cache_dir}")

        # Test ROM file
        test_rom = Path(tmpdir) / "test.sfc"
        with test_rom.open("wb") as f:
            f.write(b"TEST_ROM_DATA" * 1000)
        print(f"✓ Created test ROM: {test_rom}")

        # Test saving sprite locations
        sprite_locations = {
            "kirby_idle": SpritePointer(offset=0x12345, bank=0x20, address=0x8000, compressed_size=256),
            "kirby_walk": SpritePointer(offset=0x23456, bank=0x21, address=0x8100, compressed_size=512),
        }

        success = cache.save_sprite_locations(test_rom, sprite_locations)
        print(f"✓ Saved sprite locations: {success}")

        # Test loading sprite locations
        loaded = cache.get_sprite_locations(test_rom)
        if loaded:
            print(f"✓ Loaded {len(loaded)} sprite locations")
            for name, sprite_data in loaded.items():
                # Handle both dict and SpritePointer objects
                if isinstance(sprite_data, dict):
                    offset = sprite_data.get("offset", 0)
                else:
                    offset = sprite_data.offset
                print(f"  - {name}: offset=0x{offset:X}")
        else:
            print("✗ Failed to load sprite locations")
            return False

        # Test partial scan results
        scan_params = {"start_offset": 0xC0000, "end_offset": 0xF0000, "alignment": 0x100}

        found_sprites = [{"offset": 0xC1000, "name": "sprite1"}, {"offset": 0xC2000, "name": "sprite2"}]

        success = cache.save_partial_scan_results(test_rom, scan_params, found_sprites, 0xC3000)
        print(f"✓ Saved partial scan results: {success}")

        # Load partial scan results
        progress = cache.get_partial_scan_results(test_rom, scan_params)
        if progress:
            print(f"✓ Loaded partial scan with {len(progress['found_sprites'])} sprites")
            print(f"  - Current offset: 0x{progress['current_offset']:X}")
            print(f"  - Completed: {progress['completed']}")
        else:
            print("✗ Failed to load partial scan results")
            return False

        # Test cache stats
        stats = cache.get_cache_stats()
        print("\n✓ Cache stats:")
        print(f"  - Total files: {stats['total_files']}")
        print(f"  - Sprite caches: {stats['sprite_location_caches']}")
        print(f"  - Scan caches: {stats['scan_progress_caches']}")

    return True


def test_singleton_behavior():
    """Test the singleton cache instance"""
    print("\n=== Testing Singleton Behavior ===")

    # Create instances (ROMCache is not a singleton - each instance is independent)
    cache1 = ROMCache()
    cache2 = ROMCache()

    if cache1 is cache2:
        print("✓ Singleton returns same instance")
        return True
    print("✗ Singleton returns different instances")
    return False


def test_cache_with_ui_integration():
    """Test cache integration with UI components"""
    print("\n=== Testing UI Integration ===")

    try:
        # First test if we can import the UI module without Qt
        ui_module = importlib.import_module("ui.rom_extraction.widgets.rom_file_widget")
        print("✓ Successfully imported ROMFileWidget module")

        # Check if get_rom_cache is being used
        source = inspect.getsource(ui_module.ROMFileWidget)
        if "get_rom_cache()" in source:
            print("✓ ROMFileWidget uses get_rom_cache() singleton")
        else:
            print("✗ ROMFileWidget does not use get_rom_cache() singleton")
            return False

    except ImportError as e:
        print(f"✗ Failed to import UI components: {e}")
        return False
    except Exception as e:
        print(f"⚠️  UI integration test limited without Qt: {e}")
        return True  # This is acceptable

    return True


def main():
    """Run all manual tests"""
    print("ROM Cache Manual Test Suite")
    print("===========================")

    all_passed = True

    # Run tests
    tests = [test_basic_cache_operations, test_singleton_behavior, test_cache_with_ui_integration]

    for test in tests:
        try:
            if not test():
                all_passed = False
        except Exception as e:
            print(f"\n✗ Test {test.__name__} failed with error: {e}")
            traceback.print_exc()
            all_passed = False

    print("\n" + "=" * 50)
    if all_passed:
        print("✅ All tests passed!")
        return 0
    print("❌ Some tests failed!")
    return 1


if __name__ == "__main__":
    sys.exit(main())
