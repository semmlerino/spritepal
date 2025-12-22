"""
Golden HAL tests - verify compression behavior against recorded checksums.

These tests do NOT require real exhal/inhal binaries. They verify that:
1. Mock HAL produces deterministic output
2. Real HAL (when available) produces expected output matching recorded checksums

Usage:
    # Run golden tests with mocks (always available)
    uv run pytest tests/test_hal_golden.py -m golden_hal -v

    # Regenerate golden data with real HAL
    SPRITEPAL_EXHAL_PATH=/path/to/exhal uv run pytest tests/test_hal_golden.py --regenerate-golden -v
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pytest import FixtureRequest

pytestmark = [
    pytest.mark.golden_hal,
    pytest.mark.headless,
    pytest.mark.allows_registry_state(reason="Golden tests are stateless"),
    pytest.mark.no_qt,
]


def pytest_addoption(parser: Any) -> None:
    """Add --regenerate-golden option."""
    try:
        parser.addoption(
            "--regenerate-golden",
            action="store_true",
            default=False,
            help="Regenerate golden HAL test data (requires real exhal/inhal)",
        )
    except ValueError:
        # Option already added by another module
        pass


@pytest.fixture
def regenerate_golden(request: FixtureRequest) -> bool:
    """Check if --regenerate-golden was passed."""
    return request.config.getoption("--regenerate-golden", default=False)


class TestMockHALDeterminism:
    """Verify mock HAL produces deterministic output."""

    def test_mock_compression_deterministic(self, hal_compressor: Any, tmp_path: Path) -> None:
        """Verify mock HAL produces deterministic output for same input."""
        from tests.infrastructure.mock_hal import MockHALCompressor

        # Only run for mock compressor
        if not isinstance(hal_compressor, MockHALCompressor):
            pytest.skip("Test only applies to mock HAL")

        test_data = b"Test data for compression" * 100

        # Compress same data twice
        output1 = tmp_path / "output1.bin"
        output2 = tmp_path / "output2.bin"

        size1 = hal_compressor.compress_to_file(test_data, str(output1))
        size2 = hal_compressor.compress_to_file(test_data, str(output2))

        # Both should produce identical results
        assert size1 == size2, "Mock compression should be deterministic"
        assert output1.read_bytes() == output2.read_bytes(), "Output files should be identical"

    def test_mock_decompression_deterministic(self, hal_compressor: Any, tmp_path: Path) -> None:
        """Verify mock HAL decompression is deterministic."""
        from tests.infrastructure.mock_hal import MockHALCompressor

        if not isinstance(hal_compressor, MockHALCompressor):
            pytest.skip("Test only applies to mock HAL")

        # Create minimal ROM file
        rom_path = tmp_path / "test.rom"
        rom_path.write_bytes(b"\x00" * 0x10000)

        # Decompress same offset twice
        data1 = hal_compressor.decompress_from_rom(str(rom_path), 0x1000)
        data2 = hal_compressor.decompress_from_rom(str(rom_path), 0x1000)

        assert data1 == data2, "Mock decompression should be deterministic"

    def test_different_inputs_produce_different_outputs(
        self, hal_compressor: Any, hal_test_data: dict[str, bytes], tmp_path: Path
    ) -> None:
        """Verify different inputs produce different compressed outputs."""
        from tests.infrastructure.mock_hal import MockHALCompressor

        if not isinstance(hal_compressor, MockHALCompressor):
            pytest.skip("Test only applies to mock HAL")

        outputs: dict[str, bytes] = {}
        for name, data in hal_test_data.items():
            output_path = tmp_path / f"{name}_output.bin"
            hal_compressor.compress_to_file(data, str(output_path))
            outputs[name] = output_path.read_bytes()

        # Verify outputs are different (at least checksums differ)
        checksums = {name: hashlib.sha256(data).hexdigest() for name, data in outputs.items()}
        unique_checksums = set(checksums.values())

        # Not all outputs need to be unique (e.g., zeros and ones might compress similarly)
        # but we should have more than 1 unique output
        assert len(unique_checksums) > 1, "Different inputs should produce different outputs"


class TestGoldenHALChecksums:
    """Verify HAL compression against recorded golden checksums."""

    @pytest.mark.real_hal
    def test_real_hal_matches_golden_checksums(
        self,
        hal_compressor: Any,
        hal_golden_data: dict[str, dict],
        tmp_path: Path,
    ) -> None:
        """Verify real HAL output matches recorded golden checksums."""
        from tests.infrastructure.mock_hal import MockHALCompressor

        # Skip if we got mock instead of real
        if isinstance(hal_compressor, MockHALCompressor):
            pytest.skip("Real HAL not available")

        if not hal_golden_data:
            pytest.skip("No golden data recorded - run with --regenerate-golden first")

        for name, entry in hal_golden_data.items():
            output_path = tmp_path / f"{name}_output.bin"

            size = hal_compressor.compress_to_file(
                entry["input_data"],
                str(output_path),
            )

            # Verify size matches recorded
            expected_size = entry.get("expected_size")
            if expected_size is not None:
                assert size == expected_size, (
                    f"{name}: size {size} != expected {expected_size}"
                )

            # Verify checksum matches recorded
            expected_sha256 = entry.get("expected_sha256")
            if expected_sha256:
                actual_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()
                assert actual_sha256 == expected_sha256, (
                    f"{name}: checksum mismatch\n"
                    f"  expected: {expected_sha256}\n"
                    f"  actual:   {actual_sha256}"
                )


class TestRegenerateGolden:
    """Regenerate golden test data (only runs with --regenerate-golden)."""

    @pytest.mark.real_hal
    def test_regenerate_golden_data(
        self,
        hal_compressor: Any,
        hal_test_data: dict[str, bytes],
        tmp_path: Path,
        regenerate_golden: bool,
    ) -> None:
        """Regenerate golden checksums from real HAL output."""
        from tests.infrastructure.mock_hal import MockHALCompressor

        if not regenerate_golden:
            pytest.skip("Use --regenerate-golden to regenerate golden data")

        if isinstance(hal_compressor, MockHALCompressor):
            pytest.fail(
                "Cannot regenerate golden data with mock HAL. "
                "Set SPRITEPAL_EXHAL_PATH and SPRITEPAL_INHAL_PATH environment variables."
            )

        golden_dir = Path(__file__).parent / "fixtures" / "golden_data" / "hal"
        golden_dir.mkdir(parents=True, exist_ok=True)

        checksums: dict[str, Any] = {
            "version": 1,
            "generated_by": "real_hal",
            "generated_date": __import__("datetime").date.today().isoformat(),
            "entries": {},
        }

        for name, input_data in hal_test_data.items():
            input_file = golden_dir / f"test_{name}_input.bin"
            output_file = tmp_path / f"test_{name}_output.bin"

            # Write input file
            input_file.write_bytes(input_data)

            # Compress with real HAL
            size = hal_compressor.compress_to_file(input_data, str(output_file))

            # Record checksums
            checksums["entries"][f"test_{name}"] = {
                "input_file": input_file.name,
                "input_sha256": hashlib.sha256(input_data).hexdigest(),
                "input_size": len(input_data),
                "output_sha256": hashlib.sha256(output_file.read_bytes()).hexdigest(),
                "output_size": size,
                "compression_ratio": round(size / len(input_data), 4) if input_data else 0,
            }

        # Write checksums file
        checksums_file = golden_dir / "checksums.json"
        with checksums_file.open("w") as f:
            json.dump(checksums, f, indent=2)

        print(f"\nGolden data regenerated at: {golden_dir}")
        print(f"Entries: {list(checksums['entries'].keys())}")
