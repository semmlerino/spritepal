"""
HAL compression format parser.

This module handles parsing of HAL compression streams to determine compressed block sizes
without performing full decompression.
"""

from __future__ import annotations

from utils.logging_config import get_logger

logger = get_logger(__name__)


class HALParser:
    """Parser for HAL compression format."""

    @staticmethod
    def parse_compressed_size(rom_data: bytes, offset: int) -> int:
        """
        Parse HAL compression stream to find actual compressed block size.

        HAL compression format (verified from exhal compress.c):
        - No header - starts directly with command bytes
        - Command byte determines type and length:
          - If (cmd & 0xE0) == 0xE0: Long command
            - command = (cmd >> 2) & 0x07
            - length = (((cmd & 0x03) << 8) | next_byte) + 1
          - Else: Short command
            - command = cmd >> 5
            - length = (cmd & 0x1F) + 1
        - Commands:
          - 0: Raw bytes (length bytes follow in stream)
          - 1: 8-bit RLE (1 byte follows)
          - 2: 16-bit RLE (2 bytes follow)
          - 3: Sequence RLE (1 byte follows)
          - 4,7: Forward backref (2 bytes offset follow)
          - 5: Rotated backref (2 bytes offset follow)
          - 6: Backward backref (2 bytes offset follow)
        - 0xFF terminates the stream

        Returns:
            Actual compressed block size in bytes
        """
        logger.debug(f"Parsing HAL compressed size at offset 0x{offset:X}")

        max_pos = min(offset + 0x10000, len(rom_data))  # Cap at 64KB
        pos = offset

        try:
            while pos < max_pos:
                if pos >= len(rom_data):
                    break

                cmd = rom_data[pos]
                pos += 1

                # 0xFF terminates the stream
                if cmd == 0xFF:
                    compressed_size = pos - offset
                    logger.debug(f"HAL parsing complete: compressed={compressed_size} bytes")
                    return compressed_size

                # Decode command and length
                if (cmd & 0xE0) == 0xE0:
                    # Long command
                    if pos >= len(rom_data):
                        logger.warning(f"Truncated long command at 0x{pos:X}")
                        return pos - offset
                    command = (cmd >> 2) & 0x07
                    length = (((cmd & 0x03) << 8) | rom_data[pos]) + 1
                    pos += 1
                else:
                    # Short command
                    command = cmd >> 5
                    length = (cmd & 0x1F) + 1

                # Consume data bytes based on command type
                if command == 0:
                    # Raw: length bytes follow
                    pos += length
                elif command == 1:
                    # 8-bit RLE: 1 byte follows
                    pos += 1
                elif command == 2:
                    # 16-bit RLE: 2 bytes follow
                    pos += 2
                elif command == 3:
                    # Sequence RLE: 1 byte follows
                    pos += 1
                elif command in (4, 5, 6, 7):
                    # Backreferences: 2 bytes offset follow
                    pos += 2
                else:
                    # Unknown command - treat as end
                    logger.warning(f"Unknown HAL command {command} at 0x{pos:X}")
                    break

            # No terminator found within limit
            compressed_size = pos - offset
            logger.debug(f"HAL parsing reached limit without terminator: size={compressed_size} bytes")
            return compressed_size

        except Exception as e:
            logger.warning(f"HAL parsing failed at 0x{pos:X}: {e}, falling back to heuristic")
            return HALParser.estimate_compressed_size_conservative(rom_data, offset)

    @staticmethod
    def estimate_compressed_size_conservative(rom_data: bytes, offset: int) -> int:
        """
        Conservative fallback: require longer padding runs to reduce false positives.

        Uses 64-byte runs of 0x00/0xFF to reduce the chance that legitimate
        compressed data containing white sprite regions (0xFF) or empty areas (0x00)
        triggers early termination.

        This is a fallback when HAL parsing fails - results should be treated
        as approximate and validated against actual decompression output.
        """
        logger.warning(
            f"Using conservative size estimation at offset 0x{offset:X} - HAL parsing failed, result may be inaccurate"
        )
        max_size = min(0x10000, len(rom_data) - offset)  # Max 64KB

        # Require 64 consecutive bytes of padding to avoid truncating
        # valid sprite data that contains white regions (0xFF) or empty areas
        padding_threshold = 64
        for i in range(64, max_size, 2):
            if rom_data[offset + i : offset + i + padding_threshold] == b"\xff" * padding_threshold:
                logger.debug(f"Found 0xFF padding at offset+{i}")
                return i
            if rom_data[offset + i : offset + i + padding_threshold] == b"\x00" * padding_threshold:
                logger.debug(f"Found 0x00 padding at offset+{i}")
                return i

        # Default estimate - use 8KB instead of 4KB to be more conservative
        logger.debug("Using default compressed size estimate: 8KB")
        return 0x2000  # 8KB default (was 4KB)
