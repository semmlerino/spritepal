from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from pathlib import Path



def test_editing_controller_rejects_out_of_range_indices() -> None:
    from ui.sprite_editor.controllers.editing_controller import EditingController

    controller = EditingController()
    data = np.zeros((8, 8), dtype=np.uint8)
    data[0, 0] = 20

    controller.load_image(data)

    assert not controller.is_valid_for_rom()
    assert "palette index" in " ".join(controller.get_validation_errors()).lower()


def test_validate_png_flags_out_of_range_indices(tmp_path: Path) -> None:
    from PIL import Image

    from ui.sprite_editor.services.image_converter import ImageConverter

    img = Image.new("P", (8, 8))
    # Provide a full palette to preserve indices on save.
    palette = [value for i in range(256) for value in (i, i, i)]
    img.putpalette(palette)
    img.putdata([20] * 64)

    png_path = tmp_path / "bad_index.png"
    img.save(png_path, "PNG")

    converter = ImageConverter()
    is_valid, issues = converter.validate_png(str(png_path))

    assert not is_valid
    assert any("palette index" in issue.lower() for issue in issues)


def test_validate_png_rejects_rgb_too_many_colors(tmp_path: Path) -> None:
    from PIL import Image

    from ui.sprite_editor.services.image_converter import ImageConverter

    img = Image.new("RGB", (8, 8))
    img.putdata([(i, 0, 0) for i in range(64)])

    png_path = tmp_path / "rgb_too_many.png"
    img.save(png_path, "PNG")

    converter = ImageConverter()
    is_valid, issues = converter.validate_png(str(png_path))

    assert not is_valid
    assert any("too many" in issue.lower() for issue in issues)


def test_validate_png_rejects_grayscale_too_many_values(tmp_path: Path) -> None:
    from PIL import Image

    from ui.sprite_editor.services.image_converter import ImageConverter

    img = Image.new("L", (8, 8))
    img.putdata([i % 17 for i in range(64)])

    png_path = tmp_path / "gray_too_many.png"
    img.save(png_path, "PNG")

    converter = ImageConverter()
    is_valid, issues = converter.validate_png(str(png_path))

    assert not is_valid
    assert any("too many" in issue.lower() for issue in issues)
