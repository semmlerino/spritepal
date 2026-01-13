from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def test_preview_cache_invalidation(tmp_path: Path) -> None:
    from ui.common.smart_preview_coordinator import SmartPreviewCoordinator

    rom_path = tmp_path / "test.sfc"
    rom_path.write_bytes(b"\x00" * 1024)

    coordinator = SmartPreviewCoordinator()
    coordinator.set_rom_data_provider(lambda: (str(rom_path), object()))

    offset = 0x1234
    cache_key = coordinator._cache.make_key(str(rom_path), offset)
    # Cache format: (tile_data, width, height, sprite_name, compressed_size, slack_size, actual_offset, hal_succeeded, header_bytes)
    preview_data = (b"\x01" * 32, 8, 8, "sprite", 16, 0, offset, True, b"")
    coordinator._cache.put(cache_key, preview_data)

    assert len(coordinator._cache) == 1

    coordinator.invalidate_preview_cache(offset)

    assert len(coordinator._cache) == 0
