import numpy as np
import pytest

from core.injector import encode_4bpp_tile
from core.tile_utils import decode_4bpp_tile


def test_bitplane_round_trip_random():
    """Verify that random 4bpp data survives a full encode/decode round trip."""
    # Test 100 random iterations
    for i in range(100):
        # Generate random 8x8 pixels (0-15)
        original_pixels = np.random.randint(0, 16, (8, 8), dtype=np.uint8)

        # Encode (requires flattening)
        encoded_bytes = encode_4bpp_tile(original_pixels.flatten())

        # Decode
        decoded_pixels_list = decode_4bpp_tile(encoded_bytes)
        decoded_pixels = np.array(decoded_pixels_list, dtype=np.uint8)

        # Verify
        np.testing.assert_array_equal(original_pixels, decoded_pixels, err_msg=f"Failed on iteration {i}")


@pytest.mark.parametrize(
    "name, pattern_gen",
    [
        ("All Zeros", lambda: np.zeros((8, 8), dtype=np.uint8)),
        ("All Fifteens", lambda: np.full((8, 8), 15, dtype=np.uint8)),
        ("Checkerboard", lambda: np.array([[(r + c) % 2 * 15 for c in range(8)] for r in range(8)], dtype=np.uint8)),
        ("Gradient", lambda: np.array([[(r + c) for c in range(8)] for r in range(8)], dtype=np.uint8)),
    ],
)
def test_bitplane_round_trip_patterns(name, pattern_gen):
    """Verify specific edge-case patterns survive encode/decode."""
    pixels = pattern_gen()

    encoded = encode_4bpp_tile(pixels.flatten())
    decoded_list = decode_4bpp_tile(encoded)
    decoded = np.array(decoded_list, dtype=np.uint8)

    np.testing.assert_array_equal(pixels, decoded, err_msg=f"Failed on pattern: {name}")
