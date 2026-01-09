import unittest
from unittest.mock import MagicMock, patch

from core.rom_injector import ROMInjector


class TestSlackDetection(unittest.TestCase):
    def setUp(self):
        self.injector = ROMInjector()
        # Mock logger to avoid clutter
        self.injector.logger = MagicMock()
        # Mock dependencies
        self.injector.hal_compressor = MagicMock()
        # Mock internal parse method to control compressed size
        self.injector._parse_hal_compressed_size = MagicMock()

    def test_detect_slack_via_find_compressed_sprite(self):
        # Scenario: Sprite is 10 bytes compressed.
        # Data: [Compressed(10)][Slack(3)][NextData]
        
        # Setup mock return values
        self.injector.hal_compressor.decompress_from_rom.return_value = b"decompressed_data"
        self.injector._parse_hal_compressed_size.return_value = 10
        
        # Create dummy ROM data
        # 10 bytes "compressed" data + 3 bytes slack (FF) + 1 byte other data
        rom_data = bytearray(b"C" * 10 + b"\xff\xff\xff" + b"\xaa")
        
        # Call public method
        _, _, slack_size = self.injector.find_compressed_sprite(rom_data, 0)
        
        self.assertEqual(slack_size, 3)

    def test_detect_slack_zeros_via_find_compressed_sprite(self):
        # Scenario: 10 bytes compressed, 2 bytes zero padding
        self.injector.hal_compressor.decompress_from_rom.return_value = b"decompressed_data"
        self.injector._parse_hal_compressed_size.return_value = 10
        
        rom_data = bytearray(b"C" * 10 + b"\x00\x00" + b"\xaa")
        
        _, _, slack_size = self.injector.find_compressed_sprite(rom_data, 0)
        
        self.assertEqual(slack_size, 2)

    def test_detect_slack_none_via_find_compressed_sprite(self):
        # Scenario: 10 bytes compressed, no slack
        self.injector.hal_compressor.decompress_from_rom.return_value = b"decompressed_data"
        self.injector._parse_hal_compressed_size.return_value = 10
        
        rom_data = bytearray(b"C" * 10 + b"\xaa")
        
        _, _, slack_size = self.injector.find_compressed_sprite(rom_data, 0)
        
        self.assertEqual(slack_size, 0)

    def test_detect_slack_limit_via_find_compressed_sprite(self):
        # Scenario: Slack exceeds limit
        limit = ROMInjector.MAX_SLACK_SIZE
        self.injector.hal_compressor.decompress_from_rom.return_value = b"decompressed_data"
        self.injector._parse_hal_compressed_size.return_value = 10
        
        rom_data = bytearray(b"C" * 10 + b"\xff" * (limit + 50))
        
        _, _, slack_size = self.injector.find_compressed_sprite(rom_data, 0)
        
        self.assertEqual(slack_size, limit)


if __name__ == "__main__":
    unittest.main()
