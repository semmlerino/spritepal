#!/usr/bin/env python3
from __future__ import annotations

"""
Direct runner for integration tests that bypasses pytest collection issues.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Set environment to allow GUI tests
os.environ["DISPLAY"] = ":99"
os.environ["QT_QPA_PLATFORM"] = "xcb"  # Use X11 backend


def run_tests():
    """Run the integration tests directly."""
    print("=" * 60)
    print("RUNNING SPRITE GALLERY INTEGRATION TESTS")
    print("=" * 60)

    try:
        from PySide6.QtWidgets import QApplication

        # Create QApplication
        QApplication.instance() or QApplication(sys.argv)

        # Test results
        passed = 0
        failed = 0
        errors = []

        # Helper to run test methods
        def run_test_class(test_class, test_methods):
            nonlocal passed, failed, errors

            for method_name in test_methods:
                try:
                    print(f"\n📝 Running {test_class.__name__}.{method_name}...")

                    # Create test instance
                    test_instance = test_class()

                    # Create mock qtbot
                    from unittest.mock import MagicMock

                    qtbot = MagicMock()
                    qtbot.wait = lambda ms: None
                    qtbot.addWidget = lambda w: None

                    # Get the test method
                    test_method = getattr(test_instance, method_name)

                    # Check method signature to see what fixtures it needs
                    import inspect

                    sig = inspect.signature(test_method)
                    params = list(sig.parameters.keys())

                    # Run test with appropriate fixtures
                    if "qtbot" in params:
                        # Most tests need qtbot
                        from tests.conftest import (
                            gallery_tab,
                            gallery_with_sprites,
                            test_sprites,
                        )

                        if "gallery_tab" in params:
                            tab = gallery_tab(qtbot)
                            test_method(tab)
                        elif "gallery_with_sprites" in params:
                            tab = gallery_tab(qtbot)
                            sprites = test_sprites()
                            gallery = gallery_with_sprites(tab, sprites)
                            test_method(gallery, qtbot)
                        elif "test_sprites" in params:
                            sprites = test_sprites()
                            test_method(qtbot, sprites)
                        else:
                            test_method(qtbot)
                    else:
                        # Simple tests without fixtures
                        test_method()

                    print("  ✅ PASSED")
                    passed += 1

                except Exception as e:
                    print(f"  ❌ FAILED: {e!s}")
                    failed += 1
                    errors.append(f"{test_class.__name__}.{method_name}: {e!s}")

        # Run TestSpriteGalleryTab tests
        print("\n" + "=" * 40)
        print("Testing SpriteGalleryTab")
        print("=" * 40)

        # Create simple inline test
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap

        from ui.tabs.sprite_gallery_tab import SpriteGalleryTab
        from ui.windows.detached_gallery_window import DetachedGalleryWindow

        try:
            print("\n📝 Testing gallery initialization...")
            tab = SpriteGalleryTab()
            assert tab.gallery_widget is not None
            assert tab.toolbar is not None
            assert tab.detached_window is None
            print("  ✅ PASSED")
            passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1
            errors.append(f"Gallery initialization: {e}")

        try:
            print("\n📝 Testing sprite loading...")
            tab = SpriteGalleryTab()
            sprites = []
            for i in range(17):
                sprites.append(
                    {
                        "offset": i * 0x1000,
                        "decompressed_size": 2048,
                        "tile_count": 64,
                        "compressed": i % 3 == 0,
                    }
                )
            tab.sprites_data = sprites
            tab.gallery_widget.set_sprites(sprites)
            assert len(tab.gallery_widget.thumbnails) == 17
            print("  ✅ PASSED")
            passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1
            errors.append(f"Sprite loading: {e}")

        try:
            print("\n📝 Testing detached gallery window...")
            tab = SpriteGalleryTab()
            tab.rom_path = "test.smc"
            tab.rom_size = 4 * 1024 * 1024

            # Add mock extractor
            from unittest.mock import MagicMock

            tab.rom_extractor = MagicMock()

            # Set sprites
            sprites = []
            for i in range(10):
                sprites.append({"offset": i * 0x1000, "decompressed_size": 1024})
            tab.sprites_data = sprites
            tab.gallery_widget.set_sprites(sprites)

            # Generate thumbnails
            for sprite in sprites:
                offset = sprite["offset"]
                if offset in tab.gallery_widget.thumbnails:
                    pixmap = QPixmap(128, 128)
                    pixmap.fill(Qt.GlobalColor.darkGray)
                    thumbnail = tab.gallery_widget.thumbnails[offset]
                    thumbnail.set_sprite_data(pixmap, sprite)

            # Open detached gallery
            tab._open_detached_gallery()

            assert tab.detached_window is not None
            assert isinstance(tab.detached_window, DetachedGalleryWindow)
            if tab.detached_window.gallery_widget:
                assert len(tab.detached_window.gallery_widget.thumbnails) == 10

            # Check thumbnails were copied
            valid_count = 0
            if tab.detached_window.gallery_widget:
                for thumbnail in tab.detached_window.gallery_widget.thumbnails.values():
                    if hasattr(thumbnail, "sprite_pixmap") and thumbnail.sprite_pixmap:
                        if not thumbnail.sprite_pixmap.isNull():
                            valid_count += 1

            assert valid_count == 10, f"Expected 10 copied pixmaps, got {valid_count}"

            # Close window
            tab.detached_window.close()
            tab._on_detached_closed()
            assert tab.detached_window is None

            print("  ✅ PASSED")
            passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1
            errors.append(f"Detached gallery: {e}")

        try:
            print("\n📝 Testing layout fixes...")
            from PySide6.QtWidgets import QSizePolicy

            from ui.widgets.sprite_gallery_widget import SpriteGalleryWidget

            gallery = SpriteGalleryWidget()

            # Check embedded gallery doesn't stretch
            assert gallery.widgetResizable() == False, "Embedded gallery should have setWidgetResizable(False)"

            container = gallery.container_widget
            assert container is not None

            policy = container.sizePolicy()
            v_policy = policy.verticalPolicy()
            assert v_policy == QSizePolicy.Policy.Minimum, f"Container should have Minimum policy, has {v_policy.name}"

            print("  ✅ PASSED")
            passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1
            errors.append(f"Layout fixes: {e}")

        try:
            print("\n📝 Testing detached window scrolling...")
            # Get dependencies from AppContext
            from core.app_context import get_app_context

            ctx = get_app_context()
            core_ops_manager = ctx.core_operations_manager
            settings_manager = ctx.application_state_manager
            rom_cache = ctx.rom_cache
            window = DetachedGalleryWindow(
                extraction_manager=core_ops_manager,
                settings_manager=settings_manager,
                rom_cache=rom_cache,
            )

            sprites = []
            for i in range(5):
                sprites.append({"offset": i * 0x1000})
            window.set_sprites(sprites)

            detached_gallery = window.gallery_widget

            # Check proper scrolling setup
            if detached_gallery:
                assert detached_gallery.widgetResizable() == True, "Detached should have setWidgetResizable(True)"

                gallery_policy = detached_gallery.sizePolicy()
                v_policy = gallery_policy.verticalPolicy()
                assert v_policy == QSizePolicy.Policy.Expanding, "Detached gallery should expand"

            window.close()

            print("  ✅ PASSED")
            passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1
            errors.append(f"Detached scrolling: {e}")

        # Print summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")

        if errors:
            print("\nFailures:")
            for error in errors:
                print(f"  - {error}")

        if failed == 0:
            print("\n🎉 ALL INTEGRATION TESTS PASSED!")

        return 0 if failed == 0 else 1

    except Exception as e:
        print(f"\n❌ Test runner error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
