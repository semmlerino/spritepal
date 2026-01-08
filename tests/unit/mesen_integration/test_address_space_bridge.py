"""
Unit tests for address_space_bridge module.

Tests SA-1 ↔ S-CPU address normalization for the Mesen integration pipeline.
"""

from __future__ import annotations

import pytest

from core.mesen_integration.address_space_bridge import (
    BankRegisters,
    CanonicalAddress,
    CanonicalRange,
    addresses_match,
    is_bwram_staging,
    is_iram_staging,
    is_wram_staging,
    normalize_dma_source,
    sa1_to_canonical,
    scpu_to_canonical,
)


# =============================================================================
# BankRegisters Tests
# =============================================================================


class TestBankRegisters:
    """Tests for BankRegisters dataclass."""

    def test_default_values(self) -> None:
        """Default bank registers match power-on state."""
        regs = BankRegisters()
        assert regs.cxb == 0x00
        assert regs.dxb == 0x01
        assert regs.exb == 0x02
        assert regs.fxb == 0x03
        assert regs.bmaps == 0x00
        assert regs.bmap == 0x00

    def test_parse_from_log_valid(self) -> None:
        """Parse valid SA1_BANKS log line."""
        log_line = (
            "SA1_BANKS (init): frame=0 run=idle "
            "cxb=0x04 dxb=0x05 exb=0x06 fxb=0x07 bmaps=0x1F bmap=0x0A"
        )
        regs = BankRegisters.parse_from_log(log_line)
        assert regs is not None
        assert regs.cxb == 0x04
        assert regs.dxb == 0x05
        assert regs.exb == 0x06
        assert regs.fxb == 0x07
        assert regs.bmaps == 0x1F
        assert regs.bmap == 0x0A

    def test_parse_from_log_lowercase(self) -> None:
        """Parse log line with lowercase hex values."""
        log_line = "cxb=0xab dxb=0xcd exb=0xef fxb=0x12 bmaps=0x34 bmap=0x56"
        regs = BankRegisters.parse_from_log(log_line)
        assert regs is not None
        assert regs.cxb == 0xAB
        assert regs.dxb == 0xCD
        assert regs.exb == 0xEF
        assert regs.fxb == 0x12

    def test_parse_from_log_invalid(self) -> None:
        """Return None for invalid log line."""
        assert BankRegisters.parse_from_log("no banks here") is None
        assert BankRegisters.parse_from_log("") is None
        assert BankRegisters.parse_from_log("cxb=0x00 dxb=0x01") is None  # Incomplete

    def test_parse_from_log_extra_whitespace(self) -> None:
        """Handle extra whitespace in log line."""
        log_line = (
            "cxb=0x00   dxb=0x01   exb=0x02   fxb=0x03   bmaps=0x00   bmap=0x00"
        )
        regs = BankRegisters.parse_from_log(log_line)
        assert regs is not None
        assert regs.cxb == 0x00


# =============================================================================
# CanonicalAddress Tests
# =============================================================================


class TestCanonicalAddress:
    """Tests for CanonicalAddress dataclass."""

    def test_str_representation(self) -> None:
        """String representation shows region and hex offset."""
        addr = CanonicalAddress("WRAM", 0x1234)
        assert str(addr) == "WRAM:$01234"

        addr = CanonicalAddress("ROM", 0xABCDE)
        assert str(addr) == "ROM:$ABCDE"

    def test_frozen_dataclass(self) -> None:
        """CanonicalAddress is immutable."""
        addr = CanonicalAddress("ROM", 0x1000)
        with pytest.raises(AttributeError):
            addr.offset = 0x2000  # type: ignore[misc]

    def test_equality(self) -> None:
        """Two addresses with same region/offset are equal."""
        addr1 = CanonicalAddress("ROM", 0x1000)
        addr2 = CanonicalAddress("ROM", 0x1000)
        assert addr1 == addr2

    def test_inequality_different_region(self) -> None:
        """Addresses with different regions are not equal."""
        addr1 = CanonicalAddress("ROM", 0x1000)
        addr2 = CanonicalAddress("WRAM", 0x1000)
        assert addr1 != addr2

    def test_inequality_different_offset(self) -> None:
        """Addresses with different offsets are not equal."""
        addr1 = CanonicalAddress("ROM", 0x1000)
        addr2 = CanonicalAddress("ROM", 0x2000)
        assert addr1 != addr2

    def test_from_scpu_delegates(self) -> None:
        """from_scpu() delegates to scpu_to_canonical()."""
        # WRAM at $7E:1234
        addr = CanonicalAddress.from_scpu(0x7E1234)
        assert addr.region == "WRAM"
        assert addr.offset == 0x1234

    def test_from_sa1_delegates(self) -> None:
        """from_sa1() delegates to sa1_to_canonical()."""
        # I-RAM at $00:0100
        addr = CanonicalAddress.from_sa1(0x000100)
        assert addr.region == "IRAM"
        assert addr.offset == 0x0100


# =============================================================================
# scpu_to_canonical Tests
# =============================================================================


class TestScpuToCanonical:
    """Tests for S-CPU bus address to canonical conversion."""

    # WRAM tests ($7E:xxxx, $7F:xxxx)

    def test_wram_bank_7e(self) -> None:
        """WRAM bank $7E maps to WRAM offset 0-64KB."""
        addr = scpu_to_canonical(0x7E0000)
        assert addr.region == "WRAM"
        assert addr.offset == 0x0000

        addr = scpu_to_canonical(0x7EFFFF)
        assert addr.region == "WRAM"
        assert addr.offset == 0xFFFF

    def test_wram_bank_7f(self) -> None:
        """WRAM bank $7F maps to WRAM offset 64KB-128KB."""
        addr = scpu_to_canonical(0x7F0000)
        assert addr.region == "WRAM"
        assert addr.offset == 0x10000

        addr = scpu_to_canonical(0x7FFFFF)
        assert addr.region == "WRAM"
        assert addr.offset == 0x1FFFF

    # I-RAM tests ($00:3000-$37FF)

    def test_iram_scpu_view(self) -> None:
        """I-RAM at $00:3000-$37FF (S-CPU view)."""
        addr = scpu_to_canonical(0x003000)
        assert addr.region == "IRAM"
        assert addr.offset == 0x0000

        addr = scpu_to_canonical(0x0037FF)
        assert addr.region == "IRAM"
        assert addr.offset == 0x07FF

    def test_iram_boundary_before(self) -> None:
        """Address just before I-RAM range is not I-RAM."""
        addr = scpu_to_canonical(0x002FFF)
        assert addr.region == "UNKNOWN"

    def test_iram_boundary_after(self) -> None:
        """Address just after I-RAM range is not I-RAM."""
        addr = scpu_to_canonical(0x003800)
        assert addr.region != "IRAM"

    # BW-RAM tests ($40:xxxx)

    def test_bwram_scpu(self) -> None:
        """BW-RAM at $40:0000-$FFFF."""
        addr = scpu_to_canonical(0x400000)
        assert addr.region == "BWRAM"
        assert addr.offset == 0x0000

        addr = scpu_to_canonical(0x40FFFF)
        assert addr.region == "BWRAM"
        assert addr.offset == 0xFFFF

    # ROM tests (LoROM and HiROM patterns)

    def test_rom_lorom_lower_banks(self) -> None:
        """ROM in LoROM lower banks ($00-$3F:$8000-$FFFF)."""
        # Bank $00, offset $8000 -> ROM offset 0
        addr = scpu_to_canonical(0x008000)
        assert addr.region == "ROM"
        assert addr.offset == 0x0000

        # Bank $00, offset $FFFF -> ROM offset 0x7FFF
        addr = scpu_to_canonical(0x00FFFF)
        assert addr.region == "ROM"
        assert addr.offset == 0x7FFF

        # Bank $01, offset $8000 -> ROM offset 0x8000
        addr = scpu_to_canonical(0x018000)
        assert addr.region == "ROM"
        assert addr.offset == 0x8000

        # Bank $3F, offset $FFFF -> ROM offset (0x3F << 15) + 0x7FFF
        addr = scpu_to_canonical(0x3FFFFF)
        assert addr.region == "ROM"
        assert addr.offset == (0x3F << 15) | 0x7FFF

    def test_rom_lorom_upper_mirror(self) -> None:
        """ROM mirror in upper banks ($80-$BF:$8000-$FFFF)."""
        # Bank $80 mirrors bank $00
        addr = scpu_to_canonical(0x808000)
        assert addr.region == "ROM"
        assert addr.offset == 0x0000

        # Bank $BF mirrors bank $3F
        addr = scpu_to_canonical(0xBFFFFF)
        assert addr.region == "ROM"
        assert addr.offset == (0x3F << 15) | 0x7FFF

    def test_rom_linear_banks(self) -> None:
        """ROM in linear banks ($C0-$FF)."""
        # Bank $C0 -> linear offset 0
        addr = scpu_to_canonical(0xC00000)
        assert addr.region == "ROM"
        assert addr.offset == 0x0000

        addr = scpu_to_canonical(0xC0FFFF)
        assert addr.region == "ROM"
        assert addr.offset == 0xFFFF

        # Bank $C1 -> linear offset 0x10000
        addr = scpu_to_canonical(0xC10000)
        assert addr.region == "ROM"
        assert addr.offset == 0x10000

        # Bank $FF max
        addr = scpu_to_canonical(0xFFFFFF)
        assert addr.region == "ROM"
        assert addr.offset == (0x3F << 16) | 0xFFFF

    def test_rom_boundary_lorom(self) -> None:
        """Address below $8000 in LoROM bank is not ROM."""
        addr = scpu_to_canonical(0x007FFF)
        assert addr.region != "ROM"

    # UNKNOWN region tests

    def test_unknown_address(self) -> None:
        """Unmapped addresses return UNKNOWN region."""
        # Low memory in bank $00 (not I-RAM)
        addr = scpu_to_canonical(0x000000)
        assert addr.region == "UNKNOWN"

        # Hardware registers
        addr = scpu_to_canonical(0x002100)
        assert addr.region == "UNKNOWN"


# =============================================================================
# sa1_to_canonical Tests
# =============================================================================


class TestSa1ToCanonical:
    """Tests for SA-1 bus address to canonical conversion."""

    # I-RAM tests ($00:0000-$07FF)

    def test_iram_sa1_view(self) -> None:
        """I-RAM at $00:0000-$07FF (SA-1 view)."""
        addr = sa1_to_canonical(0x000000)
        assert addr.region == "IRAM"
        assert addr.offset == 0x0000

        addr = sa1_to_canonical(0x0007FF)
        assert addr.region == "IRAM"
        assert addr.offset == 0x07FF

    def test_iram_boundary_after(self) -> None:
        """Address just after I-RAM range is not I-RAM."""
        addr = sa1_to_canonical(0x000800)
        assert addr.region != "IRAM"

    # BW-RAM via page mapping ($00:6000-$7FFF)

    def test_bwram_page_mapping_default(self) -> None:
        """BW-RAM via $00:6000-$7FFF with default BMAP=0."""
        addr = sa1_to_canonical(0x006000)
        assert addr.region == "BWRAM"
        assert addr.offset == 0x0000

        addr = sa1_to_canonical(0x007FFF)
        assert addr.region == "BWRAM"
        assert addr.offset == 0x1FFF

    def test_bwram_page_mapping_with_bmap(self) -> None:
        """BW-RAM page selection via BMAP register."""
        regs = BankRegisters(bmap=0x05)  # Page 5
        addr = sa1_to_canonical(0x006000, regs)
        assert addr.region == "BWRAM"
        # Page 5 * 8KB (0x2000) + offset 0
        assert addr.offset == (0x05 << 13) | 0x0000

    def test_bwram_page_mapping_max_page(self) -> None:
        """BW-RAM max page (BMAP=0x1F)."""
        regs = BankRegisters(bmap=0x1F)  # Page 31
        addr = sa1_to_canonical(0x006000, regs)
        assert addr.region == "BWRAM"
        assert addr.offset == (0x1F << 13) | 0x0000

    # BW-RAM direct ($40-$4F)

    def test_bwram_direct(self) -> None:
        """BW-RAM direct at $40-$4F banks."""
        addr = sa1_to_canonical(0x400000)
        assert addr.region == "BWRAM"
        assert addr.offset == 0x0000

        addr = sa1_to_canonical(0x4FFFFF)
        assert addr.region == "BWRAM"
        assert addr.offset == (0x0F << 16) | 0xFFFF

    def test_bwram_direct_mid_bank(self) -> None:
        """BW-RAM direct in middle bank ($45)."""
        addr = sa1_to_canonical(0x451234)
        assert addr.region == "BWRAM"
        assert addr.offset == (0x05 << 16) | 0x1234

    # ROM with bank register mapping

    def test_rom_cxb_default(self) -> None:
        """ROM $C0-$CF with default CXB=0."""
        addr = sa1_to_canonical(0xC00000)
        assert addr.region == "ROM"
        assert addr.offset == 0x0000

        addr = sa1_to_canonical(0xCFFFFF)
        assert addr.region == "ROM"
        assert addr.offset == (0x0F << 16) | 0xFFFF

    def test_rom_cxb_nonzero(self) -> None:
        """ROM $C0-$CF with CXB=2 (2MB offset)."""
        regs = BankRegisters(cxb=0x02)
        addr = sa1_to_canonical(0xC00000, regs)
        assert addr.region == "ROM"
        # CXB=2 -> 2MB base (0x02 << 20)
        assert addr.offset == 0x200000

    def test_rom_dxb(self) -> None:
        """ROM $D0-$DF with DXB mapping."""
        # Default DXB=1
        addr = sa1_to_canonical(0xD00000)
        assert addr.region == "ROM"
        assert addr.offset == (0x01 << 20) | 0x0000

    def test_rom_exb(self) -> None:
        """ROM $E0-$EF with EXB mapping."""
        # Default EXB=2
        addr = sa1_to_canonical(0xE00000)
        assert addr.region == "ROM"
        assert addr.offset == (0x02 << 20) | 0x0000

    def test_rom_fxb(self) -> None:
        """ROM $F0-$FF with FXB mapping."""
        # Default FXB=3
        addr = sa1_to_canonical(0xF00000)
        assert addr.region == "ROM"
        assert addr.offset == (0x03 << 20) | 0x0000

        addr = sa1_to_canonical(0xFFFFFF)
        assert addr.region == "ROM"
        assert addr.offset == (0x03 << 20) | (0x0F << 16) | 0xFFFF

    def test_rom_lorom_sa1_lower(self) -> None:
        """SA-1 LoROM access $00-$1F:$8000-$FFFF uses CXB."""
        regs = BankRegisters(cxb=0x00)
        addr = sa1_to_canonical(0x008000, regs)
        assert addr.region == "ROM"
        # CXB=0 base + bank 0 + offset 0
        assert addr.offset == 0x0000

    def test_rom_lorom_sa1_upper(self) -> None:
        """SA-1 LoROM access $20-$3F:$8000-$FFFF uses DXB."""
        regs = BankRegisters(dxb=0x01)
        addr = sa1_to_canonical(0x208000, regs)
        assert addr.region == "ROM"
        # DXB=1 base + bank 0x20 + offset 0
        assert addr.offset == (0x01 << 20) | (0x20 << 15) | 0x0000

    # UNKNOWN region

    def test_unknown_address(self) -> None:
        """Unmapped SA-1 addresses return UNKNOWN region."""
        # Hardware registers at $00:2200
        addr = sa1_to_canonical(0x002200)
        assert addr.region == "UNKNOWN"


# =============================================================================
# Cross-CPU Address Matching Tests
# =============================================================================


class TestAddressesMatch:
    """Tests for addresses_match function."""

    def test_same_address(self) -> None:
        """Identical addresses match."""
        addr1 = CanonicalAddress("ROM", 0x1000)
        addr2 = CanonicalAddress("ROM", 0x1000)
        assert addresses_match(addr1, addr2)

    def test_different_region(self) -> None:
        """Addresses in different regions don't match."""
        addr1 = CanonicalAddress("ROM", 0x1000)
        addr2 = CanonicalAddress("WRAM", 0x1000)
        assert not addresses_match(addr1, addr2)

    def test_different_offset(self) -> None:
        """Addresses with different offsets don't match."""
        addr1 = CanonicalAddress("ROM", 0x1000)
        addr2 = CanonicalAddress("ROM", 0x2000)
        assert not addresses_match(addr1, addr2)

    def test_iram_scpu_sa1_same_location(self) -> None:
        """I-RAM from S-CPU and SA-1 views map to same canonical address."""
        # S-CPU: I-RAM at $00:3000
        scpu_addr = scpu_to_canonical(0x003000)
        # SA-1: I-RAM at $00:0000
        sa1_addr = sa1_to_canonical(0x000000)

        assert scpu_addr.region == "IRAM"
        assert sa1_addr.region == "IRAM"
        assert addresses_match(scpu_addr, sa1_addr)

    def test_wram_different_views(self) -> None:
        """WRAM addresses preserve offset correctly."""
        addr1 = scpu_to_canonical(0x7E1234)
        addr2 = scpu_to_canonical(0x7E1234)
        assert addresses_match(addr1, addr2)


# =============================================================================
# DMA Normalization Tests
# =============================================================================


class TestNormalizeDmaSource:
    """Tests for normalize_dma_source function."""

    def test_wram_dma_source(self) -> None:
        """DMA from WRAM ($7E bank)."""
        addr = normalize_dma_source(0x1234, 0x7E)
        assert addr.region == "WRAM"
        assert addr.offset == 0x1234

    def test_rom_dma_source(self) -> None:
        """DMA from ROM (linear bank $C0)."""
        addr = normalize_dma_source(0x5000, 0xC0)
        assert addr.region == "ROM"
        assert addr.offset == 0x5000

    def test_zero_bank_dma(self) -> None:
        """DMA from bank $00 with address in I-RAM range."""
        addr = normalize_dma_source(0x3100, 0x00)
        assert addr.region == "IRAM"
        assert addr.offset == 0x0100


# =============================================================================
# Staging Area Predicates Tests
# =============================================================================


class TestStagingPredicates:
    """Tests for staging area predicate functions."""

    def test_is_wram_staging(self) -> None:
        """is_wram_staging identifies WRAM region."""
        assert is_wram_staging(CanonicalAddress("WRAM", 0x1000))
        assert not is_wram_staging(CanonicalAddress("ROM", 0x1000))
        assert not is_wram_staging(CanonicalAddress("IRAM", 0x100))

    def test_is_iram_staging(self) -> None:
        """is_iram_staging identifies IRAM region."""
        assert is_iram_staging(CanonicalAddress("IRAM", 0x100))
        assert not is_iram_staging(CanonicalAddress("WRAM", 0x100))
        assert not is_iram_staging(CanonicalAddress("ROM", 0x100))

    def test_is_bwram_staging(self) -> None:
        """is_bwram_staging identifies BWRAM region."""
        assert is_bwram_staging(CanonicalAddress("BWRAM", 0x1000))
        assert not is_bwram_staging(CanonicalAddress("WRAM", 0x1000))
        assert not is_bwram_staging(CanonicalAddress("ROM", 0x1000))


# =============================================================================
# CanonicalRange Tests
# =============================================================================


class TestCanonicalRange:
    """Tests for CanonicalRange dataclass."""

    def test_end_offset(self) -> None:
        """end_offset property calculates correctly."""
        range_ = CanonicalRange("ROM", 0x1000, 0x100)
        assert range_.end_offset == 0x1100

    def test_contains_inside(self) -> None:
        """Address inside range returns True."""
        range_ = CanonicalRange("ROM", 0x1000, 0x100)
        addr = CanonicalAddress("ROM", 0x1050)
        assert range_.contains(addr)

    def test_contains_start_boundary(self) -> None:
        """Address at start boundary is contained."""
        range_ = CanonicalRange("ROM", 0x1000, 0x100)
        addr = CanonicalAddress("ROM", 0x1000)
        assert range_.contains(addr)

    def test_contains_end_boundary(self) -> None:
        """Address at end boundary is not contained (exclusive)."""
        range_ = CanonicalRange("ROM", 0x1000, 0x100)
        addr = CanonicalAddress("ROM", 0x1100)
        assert not range_.contains(addr)

    def test_contains_outside(self) -> None:
        """Address outside range returns False."""
        range_ = CanonicalRange("ROM", 0x1000, 0x100)
        addr = CanonicalAddress("ROM", 0x2000)
        assert not range_.contains(addr)

    def test_contains_different_region(self) -> None:
        """Address in different region returns False."""
        range_ = CanonicalRange("ROM", 0x1000, 0x100)
        addr = CanonicalAddress("WRAM", 0x1050)
        assert not range_.contains(addr)

    def test_overlaps_full(self) -> None:
        """Fully overlapping ranges overlap."""
        range1 = CanonicalRange("ROM", 0x1000, 0x100)
        range2 = CanonicalRange("ROM", 0x1000, 0x100)
        assert range1.overlaps(range2)

    def test_overlaps_partial(self) -> None:
        """Partially overlapping ranges overlap."""
        range1 = CanonicalRange("ROM", 0x1000, 0x100)
        range2 = CanonicalRange("ROM", 0x1050, 0x100)
        assert range1.overlaps(range2)

    def test_overlaps_adjacent_not(self) -> None:
        """Adjacent (non-overlapping) ranges don't overlap."""
        range1 = CanonicalRange("ROM", 0x1000, 0x100)
        range2 = CanonicalRange("ROM", 0x1100, 0x100)
        assert not range1.overlaps(range2)

    def test_overlaps_different_region(self) -> None:
        """Ranges in different regions don't overlap."""
        range1 = CanonicalRange("ROM", 0x1000, 0x100)
        range2 = CanonicalRange("WRAM", 0x1000, 0x100)
        assert not range1.overlaps(range2)

    def test_from_dma(self) -> None:
        """from_dma creates range from DMA parameters."""
        range_ = CanonicalRange.from_dma(0x5000, 0xC0, 0x200)
        assert range_.region == "ROM"
        assert range_.start_offset == 0x5000
        assert range_.size == 0x200


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_max_wram_offset(self) -> None:
        """Maximum WRAM offset (128KB - 1)."""
        addr = scpu_to_canonical(0x7FFFFF)
        assert addr.region == "WRAM"
        assert addr.offset == 0x1FFFF

    def test_max_iram_offset(self) -> None:
        """Maximum I-RAM offset (2KB - 1)."""
        addr = scpu_to_canonical(0x0037FF)
        assert addr.region == "IRAM"
        assert addr.offset == 0x07FF

    def test_address_zero(self) -> None:
        """Address 0 handling."""
        scpu_addr = scpu_to_canonical(0x000000)
        assert scpu_addr.region == "UNKNOWN"

        sa1_addr = sa1_to_canonical(0x000000)
        assert sa1_addr.region == "IRAM"
        assert sa1_addr.offset == 0

    def test_max_address(self) -> None:
        """Maximum 24-bit address."""
        addr = scpu_to_canonical(0xFFFFFF)
        assert addr.region == "ROM"

        addr = sa1_to_canonical(0xFFFFFF)
        assert addr.region == "ROM"

    def test_range_zero_size(self) -> None:
        """Range with zero size."""
        range_ = CanonicalRange("ROM", 0x1000, 0)
        assert range_.end_offset == 0x1000
        assert not range_.contains(CanonicalAddress("ROM", 0x1000))

    def test_canonical_address_hashable(self) -> None:
        """CanonicalAddress can be used in sets/dicts."""
        addr1 = CanonicalAddress("ROM", 0x1000)
        addr2 = CanonicalAddress("ROM", 0x1000)
        addr3 = CanonicalAddress("ROM", 0x2000)

        addr_set = {addr1, addr2, addr3}
        assert len(addr_set) == 2  # addr1 and addr2 are equal

    def test_bank_registers_none_uses_defaults(self) -> None:
        """Passing None for bank_regs uses defaults."""
        addr_with_none = sa1_to_canonical(0xC00000, None)
        addr_with_default = sa1_to_canonical(0xC00000, BankRegisters())
        assert addr_with_none == addr_with_default
