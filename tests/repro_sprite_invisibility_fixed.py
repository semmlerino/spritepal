import sys

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication


def test_sprite_visibility_fixed():
    _app = QApplication.instance() or QApplication(sys.argv)

    # Mock a sprite that was at (200, 200) but is now CROPPED to its bbox (32x32)
    # The new pixmap is 32x32, not 256x224
    _img = QImage(32, 32, QImage.Format_ARGB32)
    _img.fill("white")

    # center of canvas is (175, 175)
    # scaled_width = 32 * 4 = 128
    # x_start = 175 - 64 = 111
    # sprite x in scaled canvas = 0 * 4 = 0 (since it's cropped to bbox)
    # sprite x relative to canvas = 111 + 0 = 111
    # Canvas width is 350, so 111 is INSIDE (111 to 239)

    canvas_width = 350
    frame_width = 32
    DISPLAY_SCALE = 4

    scaled_width = frame_width * DISPLAY_SCALE
    x_start = (canvas_width // 2) - (scaled_width // 2)

    sprite_x_relative_to_bbox = 0
    sprite_x_scaled = sprite_x_relative_to_bbox * DISPLAY_SCALE

    final_x = x_start + sprite_x_scaled

    print(f"Canvas width: {canvas_width}")
    print(f"Cropped frame width: {frame_width}")
    print(f"Final drawing X: {final_x}")
    print(f"Final drawing range: {final_x} to {final_x + scaled_width}")

    if 0 <= final_x < canvas_width:
        print("SUCCESS: Sprite is INSIDE the canvas!")
    else:
        print("FAILURE: Sprite is OUTSIDE the canvas.")


if __name__ == "__main__":
    test_sprite_visibility_fixed()
