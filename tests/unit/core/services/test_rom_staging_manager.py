"""Tests for ROMStagingManager."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.services.rom_staging_manager import ROMStagingManager, StagingSession


class TestStagingSession:
    """Tests for StagingSession dataclass."""

    def test_valid_staging_path(self, tmp_path: Path) -> None:
        """Valid staging path accepted."""
        session = StagingSession(
            staging_path=tmp_path / "test.sfc.staging",
            target_path=tmp_path / "test.sfc",
        )
        assert session.committed is False

    def test_invalid_staging_path_raises(self, tmp_path: Path) -> None:
        """Staging path without .staging suffix raises."""
        with pytest.raises(ValueError, match="must end with .staging"):
            StagingSession(
                staging_path=tmp_path / "test.sfc",
                target_path=tmp_path / "test.sfc",
            )


class TestROMStagingManagerCreateInjectionCopy:
    """Tests for create_injection_copy method."""

    def test_creates_numbered_copy(self, tmp_path: Path) -> None:
        """Creates ROM copy with _injected_1 suffix."""
        rom_path = tmp_path / "game.sfc"
        rom_path.write_bytes(b"ROM DATA")

        manager = ROMStagingManager()
        result = manager.create_injection_copy(rom_path)

        assert result is not None
        assert result.name == "game_injected_1.sfc"
        assert result.read_bytes() == b"ROM DATA"

    def test_increments_counter_for_existing(self, tmp_path: Path) -> None:
        """Increments counter when numbered copies exist."""
        rom_path = tmp_path / "game.sfc"
        rom_path.write_bytes(b"ROM DATA")
        (tmp_path / "game_injected_1.sfc").write_bytes(b"OLD")
        (tmp_path / "game_injected_2.sfc").write_bytes(b"OLD")

        manager = ROMStagingManager()
        result = manager.create_injection_copy(rom_path)

        assert result is not None
        assert result.name == "game_injected_3.sfc"

    def test_strips_modified_suffix(self, tmp_path: Path) -> None:
        """Strips _modified suffix from base name."""
        rom_path = tmp_path / "game_modified.sfc"
        rom_path.write_bytes(b"ROM DATA")

        manager = ROMStagingManager()
        result = manager.create_injection_copy(rom_path)

        assert result is not None
        assert result.name == "game_injected_1.sfc"

    def test_strips_existing_injected_suffix(self, tmp_path: Path) -> None:
        """Strips existing _injected_N suffix."""
        rom_path = tmp_path / "game_injected_5.sfc"
        rom_path.write_bytes(b"ROM DATA")

        manager = ROMStagingManager()
        result = manager.create_injection_copy(rom_path)

        assert result is not None
        assert result.name == "game_injected_1.sfc"

    def test_uses_output_path_directory(self, tmp_path: Path) -> None:
        """Uses output_path directory when provided."""
        rom_path = tmp_path / "source" / "game.sfc"
        rom_path.parent.mkdir()
        rom_path.write_bytes(b"ROM DATA")

        output_dir = tmp_path / "output"
        output_dir.mkdir()
        output_path = output_dir / "custom.sfc"

        manager = ROMStagingManager()
        result = manager.create_injection_copy(rom_path, output_path)

        assert result is not None
        assert result.parent == output_dir
        assert result.name == "custom_injected_1.sfc"

    def test_returns_none_on_copy_failure(self, tmp_path: Path) -> None:
        """Returns None when copy fails."""
        rom_path = tmp_path / "nonexistent.sfc"

        manager = ROMStagingManager()
        result = manager.create_injection_copy(rom_path)

        assert result is None


class TestROMStagingManagerCreateStaging:
    """Tests for create_staging method."""

    def test_creates_staging_copy(self, tmp_path: Path) -> None:
        """Creates .staging copy of target file."""
        target_path = tmp_path / "game.sfc"
        target_path.write_bytes(b"ROM DATA")

        manager = ROMStagingManager()
        session = manager.create_staging(target_path)

        assert session is not None
        assert session.staging_path == target_path.with_suffix(".sfc.staging")
        assert session.target_path == target_path
        assert session.committed is False
        assert session.staging_path.read_bytes() == b"ROM DATA"

    def test_returns_none_on_failure(self, tmp_path: Path) -> None:
        """Returns None when target doesn't exist."""
        target_path = tmp_path / "nonexistent.sfc"

        manager = ROMStagingManager()
        session = manager.create_staging(target_path)

        assert session is None


class TestROMStagingManagerCommit:
    """Tests for commit method."""

    def test_commit_replaces_target(self, tmp_path: Path) -> None:
        """Commit atomically replaces target with staging."""
        target_path = tmp_path / "game.sfc"
        target_path.write_bytes(b"ORIGINAL")

        manager = ROMStagingManager()
        session = manager.create_staging(target_path)
        assert session is not None

        # Modify staging
        session.staging_path.write_bytes(b"MODIFIED")

        # Commit
        result = manager.commit(session)

        assert result is True
        assert session.committed is True
        assert target_path.read_bytes() == b"MODIFIED"
        assert not session.staging_path.exists()

    def test_commit_idempotent(self, tmp_path: Path) -> None:
        """Commit returns True if already committed."""
        target_path = tmp_path / "game.sfc"
        target_path.write_bytes(b"DATA")

        manager = ROMStagingManager()
        session = manager.create_staging(target_path)
        assert session is not None

        manager.commit(session)
        result = manager.commit(session)  # Second commit

        assert result is True


class TestROMStagingManagerRollback:
    """Tests for rollback method."""

    def test_rollback_deletes_staging(self, tmp_path: Path) -> None:
        """Rollback deletes staging file."""
        target_path = tmp_path / "game.sfc"
        target_path.write_bytes(b"ORIGINAL")

        manager = ROMStagingManager()
        session = manager.create_staging(target_path)
        assert session is not None

        staging_path = session.staging_path
        manager.rollback(session)

        assert not staging_path.exists()
        assert target_path.read_bytes() == b"ORIGINAL"  # Unchanged

    def test_rollback_none_safe(self) -> None:
        """Rollback with None doesn't raise."""
        manager = ROMStagingManager()
        manager.rollback(None)  # Should not raise

    def test_rollback_committed_noop(self, tmp_path: Path) -> None:
        """Rollback on committed session is no-op."""
        target_path = tmp_path / "game.sfc"
        target_path.write_bytes(b"DATA")

        manager = ROMStagingManager()
        session = manager.create_staging(target_path)
        assert session is not None

        manager.commit(session)
        manager.rollback(session)  # Should not raise

    def test_rollback_missing_file_safe(self, tmp_path: Path) -> None:
        """Rollback when staging file already deleted is safe."""
        session = StagingSession(
            staging_path=tmp_path / "nonexistent.sfc.staging",
            target_path=tmp_path / "game.sfc",
        )

        manager = ROMStagingManager()
        manager.rollback(session)  # Should not raise


class TestROMStagingManagerDetectRawSlotSize:
    """Tests for detect_raw_slot_size method."""

    def test_detects_zero_boundary(self) -> None:
        """Detects slot ending with all-zero tile."""
        # 3 tiles of data, then all-zero tile
        tile1 = bytes(range(32))
        tile2 = bytes(range(32, 64))
        tile3 = bytes(range(64, 96))
        zero_tile = bytes(32)
        rom_data = tile1 + tile2 + tile3 + zero_tile

        manager = ROMStagingManager()
        result = manager.detect_raw_slot_size(rom_data, 0)

        assert result == 3

    def test_detects_ff_boundary(self) -> None:
        """Detects slot ending with all-0xFF tile."""
        tile1 = bytes(range(32))
        tile2 = bytes(range(32, 64))
        ff_tile = bytes([0xFF] * 32)
        rom_data = tile1 + tile2 + ff_tile

        manager = ROMStagingManager()
        result = manager.detect_raw_slot_size(rom_data, 0)

        assert result == 2

    def test_accounts_for_smc_header(self) -> None:
        """Accounts for 512-byte SMC header."""
        # SMC header + tiles
        smc_header = bytes(512)
        tile1 = bytes(range(32))
        tile2 = bytes(range(32, 64))
        zero_tile = bytes(32)
        rom_data = smc_header + tile1 + tile2 + zero_tile

        # ROM size with header: 512 + 96 = 608
        # 608 % 0x8000 = 608, which is not 512, so no header detected
        # Let me create proper size ROM

        # Create ROM that triggers SMC header detection
        # 0x8000 * N + 512 bytes
        padding = bytes(0x8000 - len(tile1 + tile2 + zero_tile))
        rom_data = smc_header + tile1 + tile2 + zero_tile + padding

        manager = ROMStagingManager()
        result = manager.detect_raw_slot_size(rom_data, 0)

        assert result == 2

    def test_returns_none_for_out_of_bounds_offset(self) -> None:
        """Returns None for offset beyond ROM size."""
        rom_data = bytes(100)

        manager = ROMStagingManager()
        result = manager.detect_raw_slot_size(rom_data, 0x10000)

        assert result is None

    def test_returns_none_when_no_boundary(self) -> None:
        """Returns None when no boundary found within max_tiles."""
        # All non-zero, non-FF data
        rom_data = bytes(range(256)) * 40  # 10240 bytes = 320 tiles

        manager = ROMStagingManager()
        result = manager.detect_raw_slot_size(rom_data, 0, max_tiles=10)

        assert result is None

    def test_returns_none_for_boundary_at_start(self) -> None:
        """Returns None if first tile is boundary (zero tiles found)."""
        zero_tile = bytes(32)
        tile1 = bytes(range(32))
        rom_data = zero_tile + tile1

        manager = ROMStagingManager()
        result = manager.detect_raw_slot_size(rom_data, 0)

        assert result is None

    def test_respects_max_tiles_limit(self) -> None:
        """Respects max_tiles limit."""
        # 100 tiles of non-boundary data
        rom_data = bytes(range(256)) * 20

        manager = ROMStagingManager()
        result = manager.detect_raw_slot_size(rom_data, 0, max_tiles=5)

        assert result is None


class TestROMStagingManagerCleanupOnFailure:
    """Tests for cleanup_on_failure method."""

    def test_cleanup_rolls_back_staging(self, tmp_path: Path) -> None:
        """cleanup_on_failure rolls back staging."""
        target_path = tmp_path / "game.sfc"
        target_path.write_bytes(b"DATA")

        manager = ROMStagingManager()
        session = manager.create_staging(target_path)
        assert session is not None

        manager.cleanup_on_failure(session, None, False)

        assert not session.staging_path.exists()

    def test_cleanup_deletes_injection_copy_when_created(self, tmp_path: Path) -> None:
        """Deletes injection copy when not reusing existing output."""
        injection_path = tmp_path / "game_injected_1.sfc"
        injection_path.write_bytes(b"DATA")

        manager = ROMStagingManager()
        manager.cleanup_on_failure(None, injection_path, was_existing_output=False)

        assert not injection_path.exists()

    def test_cleanup_preserves_existing_output(self, tmp_path: Path) -> None:
        """Preserves injection copy when reusing existing output."""
        injection_path = tmp_path / "game_injected_1.sfc"
        injection_path.write_bytes(b"DATA")

        manager = ROMStagingManager()
        manager.cleanup_on_failure(None, injection_path, was_existing_output=True)

        assert injection_path.exists()  # Not deleted

    def test_cleanup_handles_none_gracefully(self) -> None:
        """Handles None values gracefully."""
        manager = ROMStagingManager()
        manager.cleanup_on_failure(None, None, False)  # Should not raise


class TestROMStagingManagerIntegration:
    """Integration tests for full staging workflow."""

    def test_full_workflow_success(self, tmp_path: Path) -> None:
        """Full workflow: create copy, stage, modify, commit."""
        rom_path = tmp_path / "original.sfc"
        rom_path.write_bytes(b"ORIGINAL ROM DATA")

        manager = ROMStagingManager()

        # Step 1: Create injection copy
        injection_path = manager.create_injection_copy(rom_path)
        assert injection_path is not None
        assert injection_path.name == "original_injected_1.sfc"

        # Step 2: Create staging
        session = manager.create_staging(injection_path)
        assert session is not None

        # Step 3: Modify staging (simulate injection)
        session.staging_path.write_bytes(b"MODIFIED ROM DATA")

        # Step 4: Commit
        success = manager.commit(session)
        assert success is True

        # Verify: injection copy has modified data, staging deleted
        assert injection_path.read_bytes() == b"MODIFIED ROM DATA"
        assert not session.staging_path.exists()
        # Original unchanged
        assert rom_path.read_bytes() == b"ORIGINAL ROM DATA"

    def test_full_workflow_failure(self, tmp_path: Path) -> None:
        """Full workflow with rollback on failure."""
        rom_path = tmp_path / "original.sfc"
        rom_path.write_bytes(b"ORIGINAL ROM DATA")

        manager = ROMStagingManager()

        # Step 1: Create injection copy
        injection_path = manager.create_injection_copy(rom_path)
        assert injection_path is not None

        # Step 2: Create staging
        session = manager.create_staging(injection_path)
        assert session is not None

        # Step 3: Modify staging
        session.staging_path.write_bytes(b"MODIFIED BUT FAILED")

        # Step 4: Rollback (simulating failure)
        manager.cleanup_on_failure(session, injection_path, was_existing_output=False)

        # Verify: staging deleted, injection copy deleted
        assert not session.staging_path.exists()
        assert not injection_path.exists()
        # Original unchanged
        assert rom_path.read_bytes() == b"ORIGINAL ROM DATA"
