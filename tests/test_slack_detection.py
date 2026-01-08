import unittest
from unittest.mock import MagicMock

from core.rom_injector import ROMInjector


class TestSlackDetection(unittest.TestCase):
    def setUp(self):
        self.injector = ROMInjector()
        # Mock logger to avoid clutter
        self.injector.logger = MagicMock()

    def test_detect_slack_simple(self):
        # Data: [Sprite...][FF][FF][FF][Data...]
        # Sprite ends at 10. Slack starts at 10.
        # 3 bytes of slack.
        data = bytearray(b"\x00" * 10 + b"\xff\xff\xff" + b"\xaa")
        slack = self.injector._detect_slack_space(data, 10)
        self.assertEqual(slack, 3)

    def test_detect_slack_zeros(self):
        # Data: [Sprite...][00][00][Data...]
        data = bytearray(b"\x00" * 10 + b"\x00\x00" + b"\xaa")
        slack = self.injector._detect_slack_space(data, 10)
        self.assertEqual(slack, 2)

    def test_detect_slack_none(self):
        # Data: [Sprite...][AA][Data...]
        data = bytearray(b"\x00" * 10 + b"\xaa")
        slack = self.injector._detect_slack_space(data, 10)
        self.assertEqual(slack, 0)

    def test_detect_slack_mixed_stop(self):
        # Data: [Sprite...][FF][00][FF]...
        # Should stop at change?
        # The code uses: pad_char = rom_data[start_offset]
        # Then loops checking if rom_data[i] == pad_char.
        # So mixed 00/FF is NOT allowed.
        data = bytearray(b"\x00" * 10 + b"\xff\x00\xff")
        slack = self.injector._detect_slack_space(data, 10)
        self.assertEqual(slack, 1)  # Only the first FF matches

    def test_detect_slack_limit(self):
        # Data: [Sprite...][FF] * 300
        # Limit is 256.
        data = bytearray(b"\x00" * 10 + b"\xff" * 300)
        slack = self.injector._detect_slack_space(data, 10)
        self.assertEqual(slack, 256)


if __name__ == "__main__":
    unittest.main()
