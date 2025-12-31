"""
Address Space Bridge for SA-1 ↔ S-CPU Address Normalization.

The SA-1 coprocessor and S-CPU have different views of memory. SNES DMA source
addresses are in S-CPU bus space, while CCDMA addresses are in SA-1 bus space.
This module normalizes both to a canonical form for correlation.

Memory Regions:
    WRAM    - Standard SNES work RAM ($7E/$7F, 128KB)
    IRAM    - SA-1 internal RAM (2KB)
              S-CPU view: $00:3000-$37FF
              SA-1 view: $00:0000-$07FF
    BWRAM   - Battery-backed work RAM (up to 256KB)
              Mapping controlled by BMAPS ($2224) for S-CPU
              Mapping controlled by BMAP ($2225) for SA-1
    ROM     - Program ROM
              SA-1 view: Banks $C0-$FF (configurable via $2220-$2223)

Usage:
    from core.mesen_integration.address_space_bridge import (
        scpu_to_canonical,
        sa1_to_canonical,
        addresses_match,
    )

    # Normalize S-CPU DMA source address
    scpu_addr = CanonicalAddress.from_scpu(0x7EF382)  # WRAM staging buffer

    # Normalize SA-1 CCDMA destination address
    sa1_addr = CanonicalAddress.from_sa1(0x003000)  # I-RAM

    # Check if addresses refer to same memory
    if addresses_match(scpu_addr, sa1_addr):
        ...
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, override

# Memory region types
MemoryRegion = Literal["WRAM", "IRAM", "BWRAM", "ROM", "UNKNOWN"]


@dataclass
class BankRegisters:
    """
    SA-1 bank mapping registers.

    These registers control how both CPUs see ROM and BW-RAM.
    """

    cxb: int = 0x00  # $2220: ROM bank for $C0-$CF (SA-1) / $00-$1F (S-CPU)
    dxb: int = 0x01  # $2221: ROM bank for $D0-$DF (SA-1) / $20-$3F (S-CPU)
    exb: int = 0x02  # $2222: ROM bank for $E0-$EF (SA-1) / $80-$9F (S-CPU)
    fxb: int = 0x03  # $2223: ROM bank for $F0-$FF (SA-1) / $A0-$BF (S-CPU)
    bmaps: int = 0x00  # $2224: BW-RAM mapping (S-CPU side)
    bmap: int = 0x00  # $2225: BW-RAM mapping (SA-1 side)

    @classmethod
    def parse_from_log(cls, log_line: str) -> BankRegisters | None:
        """
        Parse bank registers from SA1_BANKS log line.

        Format: SA1_BANKS (init): frame=0 run=... cxb=0x00 dxb=0x01 ...
        """
        import re

        pattern = (
            r"cxb=0x(?P<cxb>[0-9A-Fa-f]{2})\s+"
            r"dxb=0x(?P<dxb>[0-9A-Fa-f]{2})\s+"
            r"exb=0x(?P<exb>[0-9A-Fa-f]{2})\s+"
            r"fxb=0x(?P<fxb>[0-9A-Fa-f]{2})\s+"
            r"bmaps=0x(?P<bmaps>[0-9A-Fa-f]{2})\s+"
            r"bmap=0x(?P<bmap>[0-9A-Fa-f]{2})"
        )
        match = re.search(pattern, log_line)
        if not match:
            return None

        return cls(
            cxb=int(match.group("cxb"), 16),
            dxb=int(match.group("dxb"), 16),
            exb=int(match.group("exb"), 16),
            fxb=int(match.group("fxb"), 16),
            bmaps=int(match.group("bmaps"), 16),
            bmap=int(match.group("bmap"), 16),
        )


@dataclass(frozen=True)
class CanonicalAddress:
    """
    Normalized memory address in canonical form.

    Two addresses are equivalent if they have the same region and offset,
    regardless of which CPU's bus space they originated from.
    """

    region: MemoryRegion
    offset: int  # Offset within region

    @override
    def __str__(self) -> str:
        return f"{self.region}:${self.offset:05X}"

    @classmethod
    def from_scpu(
        cls,
        addr: int,
        bank_regs: BankRegisters | None = None,
    ) -> CanonicalAddress:
        """
        Normalize S-CPU bus address to canonical form.

        Args:
            addr: 24-bit S-CPU bus address (bank in bits 16-23)
            bank_regs: Optional bank register state for BW-RAM mapping

        Returns:
            Canonical address with region and offset
        """
        return scpu_to_canonical(addr, bank_regs)

    @classmethod
    def from_sa1(
        cls,
        addr: int,
        bank_regs: BankRegisters | None = None,
    ) -> CanonicalAddress:
        """
        Normalize SA-1 bus address to canonical form.

        Args:
            addr: 24-bit SA-1 bus address (bank in bits 16-23)
            bank_regs: Optional bank register state for ROM/BW-RAM mapping

        Returns:
            Canonical address with region and offset
        """
        return sa1_to_canonical(addr, bank_regs)


def scpu_to_canonical(
    addr: int,
    bank_regs: BankRegisters | None = None,
) -> CanonicalAddress:
    """
    Translate S-CPU bus address to canonical form.

    S-CPU Memory Map (relevant regions):
        $00:3000-$37FF  - I-RAM (SA-1 internal RAM mirror)
        $7E:0000-$FFFF  - WRAM bank 0 (64KB)
        $7F:0000-$FFFF  - WRAM bank 1 (64KB)
        $40:0000-$43FF  - BW-RAM (base, mapped via BMAPS)
        $00:8000-$FFFF  - ROM (LoROM, lower banks)
        $80:8000-$FFFF  - ROM (LoROM, upper banks)

    Args:
        addr: 24-bit S-CPU bus address
        bank_regs: Optional bank register state

    Returns:
        CanonicalAddress with region and offset
    """
    bank = (addr >> 16) & 0xFF
    addr_low = addr & 0xFFFF

    # WRAM: Banks $7E-$7F
    if bank == 0x7E:
        return CanonicalAddress("WRAM", addr_low)
    if bank == 0x7F:
        return CanonicalAddress("WRAM", 0x10000 + addr_low)

    # I-RAM: $00:3000-$37FF (S-CPU view)
    if bank == 0x00 and 0x3000 <= addr_low < 0x3800:
        return CanonicalAddress("IRAM", addr_low - 0x3000)

    # BW-RAM: $40:0000-$43FF (base mapping, 1KB pages via BMAPS)
    # Full mapping depends on BMAPS register
    if bank == 0x40 and addr_low < 0x10000:
        # Simplified: treat as linear BW-RAM offset
        # Full implementation would use BMAPS for page selection
        return CanonicalAddress("BWRAM", addr_low)

    # ROM: Banks $00-$3F, $80-$BF (upper half only in LoROM)
    if bank <= 0x3F and addr_low >= 0x8000:
        # LoROM: each bank has 32KB ROM at $8000-$FFFF
        rom_offset = (bank << 15) | (addr_low - 0x8000)
        return CanonicalAddress("ROM", rom_offset)
    if 0x80 <= bank <= 0xBF and addr_low >= 0x8000:
        # LoROM mirror in upper banks
        effective_bank = bank - 0x80
        rom_offset = (effective_bank << 15) | (addr_low - 0x8000)
        return CanonicalAddress("ROM", rom_offset)

    # ROM: Banks $C0-$FF (linear mapping, 64KB per bank)
    if bank >= 0xC0:
        rom_offset = ((bank - 0xC0) << 16) | addr_low
        return CanonicalAddress("ROM", rom_offset)

    return CanonicalAddress("UNKNOWN", addr)


def sa1_to_canonical(
    addr: int,
    bank_regs: BankRegisters | None = None,
) -> CanonicalAddress:
    """
    Translate SA-1 bus address to canonical form.

    SA-1 Memory Map (relevant regions):
        $00:0000-$07FF  - I-RAM (SA-1 internal RAM)
        $00:6000-$7FFF  - BW-RAM (mapped via BMAP)
        $40:0000-$FFFF  - BW-RAM (direct, 256KB max)
        $C0:0000-$FFFF  - ROM (mapped via CXB, 1MB per group)
        $D0:0000-$FFFF  - ROM (mapped via DXB)
        $E0:0000-$FFFF  - ROM (mapped via EXB)
        $F0:0000-$FFFF  - ROM (mapped via FXB)

    Args:
        addr: 24-bit SA-1 bus address
        bank_regs: Optional bank register state

    Returns:
        CanonicalAddress with region and offset
    """
    bank = (addr >> 16) & 0xFF
    addr_low = addr & 0xFFFF

    if bank_regs is None:
        bank_regs = BankRegisters()  # Power-on defaults

    # I-RAM: $00:0000-$07FF (SA-1 view)
    if bank == 0x00 and addr_low < 0x0800:
        return CanonicalAddress("IRAM", addr_low)

    # BW-RAM via $00:6000-$7FFF (uses BMAP for bank selection)
    if bank == 0x00 and 0x6000 <= addr_low < 0x8000:
        # Page within BW-RAM determined by BMAP bits 0-4
        bwram_page = bank_regs.bmap & 0x1F
        bwram_offset = (bwram_page << 13) | (addr_low - 0x6000)
        return CanonicalAddress("BWRAM", bwram_offset)

    # BW-RAM direct: $40-$4F
    if 0x40 <= bank <= 0x4F:
        bwram_offset = ((bank - 0x40) << 16) | addr_low
        return CanonicalAddress("BWRAM", bwram_offset)

    # ROM: Banks $C0-$CF (CXB mapping)
    if 0xC0 <= bank <= 0xCF:
        rom_bank_base = bank_regs.cxb << 20  # Each CXB value = 1MB
        rom_offset = rom_bank_base | ((bank - 0xC0) << 16) | addr_low
        return CanonicalAddress("ROM", rom_offset)

    # ROM: Banks $D0-$DF (DXB mapping)
    if 0xD0 <= bank <= 0xDF:
        rom_bank_base = bank_regs.dxb << 20
        rom_offset = rom_bank_base | ((bank - 0xD0) << 16) | addr_low
        return CanonicalAddress("ROM", rom_offset)

    # ROM: Banks $E0-$EF (EXB mapping)
    if 0xE0 <= bank <= 0xEF:
        rom_bank_base = bank_regs.exb << 20
        rom_offset = rom_bank_base | ((bank - 0xE0) << 16) | addr_low
        return CanonicalAddress("ROM", rom_offset)

    # ROM: Banks $F0-$FF (FXB mapping)
    if 0xF0 <= bank <= 0xFF:
        rom_bank_base = bank_regs.fxb << 20
        rom_offset = rom_bank_base | ((bank - 0xF0) << 16) | addr_low
        return CanonicalAddress("ROM", rom_offset)

    # SA-1 LoROM areas ($00-$3F with offset >= $8000)
    if bank <= 0x3F and addr_low >= 0x8000:
        # Uses CXB/DXB for ROM mapping
        if bank <= 0x1F:
            rom_bank_base = bank_regs.cxb << 20
        else:
            rom_bank_base = bank_regs.dxb << 20
        rom_offset = rom_bank_base | (bank << 15) | (addr_low - 0x8000)
        return CanonicalAddress("ROM", rom_offset)

    return CanonicalAddress("UNKNOWN", addr)


def addresses_match(
    addr1: CanonicalAddress,
    addr2: CanonicalAddress,
) -> bool:
    """
    Check if two canonical addresses refer to the same memory location.

    Args:
        addr1: First canonical address
        addr2: Second canonical address

    Returns:
        True if addresses are equivalent
    """
    return addr1.region == addr2.region and addr1.offset == addr2.offset


def normalize_dma_source(
    src_addr: int,
    src_bank: int,
) -> CanonicalAddress:
    """
    Normalize a SNES DMA source address (from log) to canonical form.

    SNES DMA logs provide source as 16-bit address + 8-bit bank.

    Args:
        src_addr: 16-bit source address (A1T)
        src_bank: 8-bit source bank (A1B)

    Returns:
        Canonical address
    """
    full_addr = (src_bank << 16) | src_addr
    return scpu_to_canonical(full_addr)


def is_wram_staging(canonical: CanonicalAddress) -> bool:
    """Check if address is in WRAM (common staging area)."""
    return canonical.region == "WRAM"


def is_iram_staging(canonical: CanonicalAddress) -> bool:
    """Check if address is in I-RAM (SA-1 internal RAM)."""
    return canonical.region == "IRAM"


def is_bwram_staging(canonical: CanonicalAddress) -> bool:
    """Check if address is in BW-RAM (battery-backed work RAM)."""
    return canonical.region == "BWRAM"


# =============================================================================
# Address range utilities
# =============================================================================


@dataclass
class CanonicalRange:
    """A contiguous range in canonical address space."""

    region: MemoryRegion
    start_offset: int
    size: int

    @property
    def end_offset(self) -> int:
        """End offset (exclusive)."""
        return self.start_offset + self.size

    def contains(self, addr: CanonicalAddress) -> bool:
        """Check if address falls within this range."""
        if addr.region != self.region:
            return False
        return self.start_offset <= addr.offset < self.end_offset

    def overlaps(self, other: CanonicalRange) -> bool:
        """Check if two ranges overlap."""
        if self.region != other.region:
            return False
        return not (
            self.end_offset <= other.start_offset
            or other.end_offset <= self.start_offset
        )

    @classmethod
    def from_dma(
        cls,
        src_addr: int,
        src_bank: int,
        size: int,
    ) -> CanonicalRange:
        """Create range from SNES DMA parameters."""
        canonical = normalize_dma_source(src_addr, src_bank)
        return cls(
            region=canonical.region,
            start_offset=canonical.offset,
            size=size,
        )
