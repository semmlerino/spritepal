-- verify_endianness.lua
-- Purpose: Empirically verify emu.readWord() byte order behavior
-- Usage: Mesen2.exe --testrunner "rom.sfc" "verify_endianness.lua"
--
-- This script reads VRAM at several addresses using both:
--   1. emu.read() for individual bytes
--   2. emu.readWord() for 16-bit words
-- Then compares to determine actual byte order returned by readWord()

local OUTPUT_PATH = os.getenv("OUTPUT_PATH") or "mesen2_exchange/endianness_verification.txt"
local TARGET_FRAME = tonumber(os.getenv("TARGET_FRAME")) or 100

-- Validate API availability
assert(emu.read, "emu.read not available")
assert(emu.readWord, "emu.readWord not available")
assert(emu.memType.snesVideoRam, "snesVideoRam memType not available")

local results = {}
local frame_count = 0
local tested = false

local function log(msg)
    table.insert(results, msg)
    print(msg)
end

local function verify_endianness()
    log("=== emu.readWord() Endianness Verification ===")
    log(string.format("Frame: %d", frame_count))
    log("")

    -- Test at multiple VRAM addresses to find non-zero data
    local test_addrs = {0x0000, 0x0100, 0x0200, 0x1000, 0x2000, 0x4000, 0x8000}
    local found_nonzero = false

    for _, addr in ipairs(test_addrs) do
        -- Read individual bytes
        local byte0 = emu.read(addr, emu.memType.snesVideoRam)
        local byte1 = emu.read(addr + 1, emu.memType.snesVideoRam)

        -- Read as word
        local word = emu.readWord(addr, emu.memType.snesVideoRam)

        -- Skip if both bytes are zero (not useful for verification)
        if byte0 ~= 0 or byte1 ~= 0 then
            found_nonzero = true

            log(string.format("Address 0x%04X:", addr))
            log(string.format("  emu.read(addr)   = 0x%02X (byte at address)", byte0))
            log(string.format("  emu.read(addr+1) = 0x%02X (byte at address+1)", byte1))
            log(string.format("  emu.readWord(addr) = 0x%04X", word))

            -- Interpret the word both ways
            local word_low_byte = word & 0xFF
            local word_high_byte = (word >> 8) & 0xFF

            log(string.format("  Word low byte (word & 0xFF):       0x%02X", word_low_byte))
            log(string.format("  Word high byte ((word >> 8) & FF): 0x%02X", word_high_byte))

            -- Determine which interpretation matches
            local is_little_endian = (word_low_byte == byte0 and word_high_byte == byte1)
            local is_big_endian = (word_high_byte == byte0 and word_low_byte == byte1)

            if is_little_endian then
                log("  -> LITTLE-ENDIAN: low byte of word = byte at address")
            elseif is_big_endian then
                log("  -> BIG-ENDIAN: high byte of word = byte at address")
            else
                log("  -> INCONCLUSIVE: bytes don't match either interpretation")
            end
            log("")
        end
    end

    if not found_nonzero then
        log("WARNING: All tested VRAM addresses contained zero bytes.")
        log("Try running with a ROM that has VRAM data loaded.")
    end

    -- Also test WRAM for comparison
    log("=== WRAM Comparison ===")
    local wram_addr = 0x0100
    local wram_byte0 = emu.read(wram_addr, emu.memType.snesWorkRam)
    local wram_byte1 = emu.read(wram_addr + 1, emu.memType.snesWorkRam)
    local wram_word = emu.readWord(wram_addr, emu.memType.snesWorkRam)

    log(string.format("WRAM Address 0x%04X:", wram_addr))
    log(string.format("  emu.read(addr)     = 0x%02X", wram_byte0))
    log(string.format("  emu.read(addr+1)   = 0x%02X", wram_byte1))
    log(string.format("  emu.readWord(addr) = 0x%04X", wram_word))

    local wram_low = wram_word & 0xFF
    local wram_high = (wram_word >> 8) & 0xFF

    if wram_low == wram_byte0 and wram_high == wram_byte1 then
        log("  -> WRAM: LITTLE-ENDIAN")
    elseif wram_high == wram_byte0 and wram_low == wram_byte1 then
        log("  -> WRAM: BIG-ENDIAN")
    else
        log("  -> WRAM: INCONCLUSIVE")
    end
    log("")

    -- Test CGRAM (Color RAM / Palette)
    log("=== CGRAM (Palette) Verification ===")
    local cgram_addr = 0x0000  -- First palette entry
    local cgram_byte0 = emu.read(cgram_addr, emu.memType.snesCgRam)
    local cgram_byte1 = emu.read(cgram_addr + 1, emu.memType.snesCgRam)
    local cgram_word = emu.readWord(cgram_addr, emu.memType.snesCgRam)

    log(string.format("CGRAM Address 0x%04X:", cgram_addr))
    log(string.format("  emu.read(addr)     = 0x%02X", cgram_byte0))
    log(string.format("  emu.read(addr+1)   = 0x%02X", cgram_byte1))
    log(string.format("  emu.readWord(addr) = 0x%04X", cgram_word))

    local cgram_low = cgram_word & 0xFF
    local cgram_high = (cgram_word >> 8) & 0xFF

    if cgram_low == cgram_byte0 and cgram_high == cgram_byte1 then
        log("  -> CGRAM: LITTLE-ENDIAN")
    elseif cgram_high == cgram_byte0 and cgram_low == cgram_byte1 then
        log("  -> CGRAM: BIG-ENDIAN")
    else
        log("  -> CGRAM: INCONCLUSIVE (may be zero data)")
    end
    log("")

    -- Test OAM (Sprite RAM)
    log("=== OAM (Sprite RAM) Verification ===")
    -- OAM is 544 bytes: 512 bytes for 128 sprites + 32 bytes for high table
    local oam_addr = 0x0000  -- First sprite entry
    local oam_byte0 = emu.read(oam_addr, emu.memType.snesSpriteRam)
    local oam_byte1 = emu.read(oam_addr + 1, emu.memType.snesSpriteRam)
    local oam_word = emu.readWord(oam_addr, emu.memType.snesSpriteRam)

    log(string.format("OAM Address 0x%04X:", oam_addr))
    log(string.format("  emu.read(addr)     = 0x%02X", oam_byte0))
    log(string.format("  emu.read(addr+1)   = 0x%02X", oam_byte1))
    log(string.format("  emu.readWord(addr) = 0x%04X", oam_word))

    local oam_low = oam_word & 0xFF
    local oam_high = (oam_word >> 8) & 0xFF

    if oam_low == oam_byte0 and oam_high == oam_byte1 then
        log("  -> OAM: LITTLE-ENDIAN")
    elseif oam_high == oam_byte0 and oam_low == oam_byte1 then
        log("  -> OAM: BIG-ENDIAN")
    else
        log("  -> OAM: INCONCLUSIVE (may be zero data)")
    end
    log("")

    -- Summary
    log("=== CONCLUSION ===")
    log("If VRAM shows LITTLE-ENDIAN: the documentation is WRONG")
    log("If VRAM shows BIG-ENDIAN: the documentation is correct")
    log("")
    log("Expected based on source code analysis (MemoryDumper.cpp):")
    log("  return (msb << 8) | lsb;  // lsb from addr, msb from addr+1")
    log("This is LITTLE-ENDIAN behavior.")
end

local function on_end_frame()
    frame_count = frame_count + 1

    if frame_count >= TARGET_FRAME and not tested then
        tested = true
        verify_endianness()

        -- Write results to file
        local file = io.open(OUTPUT_PATH, "w")
        if file then
            file:write(table.concat(results, "\n"))
            file:close()
            print(string.format("Results written to: %s", OUTPUT_PATH))
        else
            print("WARNING: Could not write to output file")
        end

        emu.stop()
    end
end

emu.addEventCallback(on_end_frame, emu.eventType.endFrame)
print(string.format("Endianness verification script loaded. Waiting for frame %d...", TARGET_FRAME))
