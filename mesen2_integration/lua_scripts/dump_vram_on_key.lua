-- Dump VRAM tile bytes on keypress (F5)
-- Press F5 when Waddle Dee is visible to capture VRAM state
--
-- Mesen sprite viewer shows: Tile Index $6C, Tile Address $66C0

local OUTPUT = "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\spritepal\\mesen2_exchange\\vram_tile_dump.txt"

local function dump_vram_tiles()
    local f = io.open(OUTPUT, "w")
    f:write("VRAM TILE DUMP - For comparison with SpritePal\n")
    f:write("==============================================\n")
    f:write(string.format("Captured at frame: %d\n", emu.getState().ppu.frameCount or 0))

    -- Tiles to dump based on Mesen sprite viewer info
    -- Tile $6C at word address $66C0 = byte address $CD80
    local tiles = {
        {name = "Tile $6C (Waddle Dee top-left)", word_addr = 0x66C0},
        {name = "Tile $6D (top-right)", word_addr = 0x66D0},
        {name = "Tile $7C (bottom-left, +16)", word_addr = 0x67C0},
        {name = "Tile $7D (bottom-right)", word_addr = 0x67D0},
    }

    for _, tile in ipairs(tiles) do
        local byte_addr = tile.word_addr * 2
        f:write(string.format("\n%s\n", tile.name))
        f:write(string.format("  VRAM word addr: $%04X, byte addr: $%05X\n", tile.word_addr, byte_addr))

        -- Read 32 bytes
        local hex_line = "  "
        for i = 0, 31 do
            local val = emu.read(byte_addr + i, emu.memType.snesVideoRam)
            hex_line = hex_line .. string.format("%02X ", val)
        end
        f:write(hex_line .. "\n")
    end

    f:write("\n\n-- SPRITEPAL HAL-DECOMPRESSED DATA (ROM 0x25AD84) --\n")
    f:write("Tile 0: 02 0F C1 FF 7F 1F 63 BD 52 1E 33 DF 02 FD 15 55 09 05 00 FF 3B 80 03 78 7F B0 7E EA 7D 00 64 05\n")
    f:write("Tile 1: 00 0F C1 FF 7F 3E 43 3E 5A 1E 42 7B 49 F8 50 90 50 05 00 FF 3B 80 03 78 7F B0 7E EA 7D 00 64 00\n")
    f:write("Tile 2: 00 0F C1 FF 7F 3F 67 BF 5A 3F 4E BF 3D 58 45 94 34 0D 08 FF 3B 80 03 78 7F B0 7E EA 7D 00 64 00\n")
    f:write("Tile 3: 00 0F C1 29 25 E9 1C C9 18 A9 14 89 10 67 14 26 10 04 00 29 11 00 01 07 25 C4 24 83 24 00 1C 00\n")

    f:close()
    emu.displayMessage("Info", "VRAM dump saved! Check mesen2_exchange/vram_tile_dump.txt")
end

-- Register F5 key handler
emu.addEventCallback(function()
    local input = emu.getInput(0)
    -- Check if F5 pressed (using select button as proxy since direct key detection varies)
end, emu.eventType.inputPolled)

-- Alternative: dump every time script loads (one-shot)
-- Just run the script when Waddle Dee is on screen
dump_vram_tiles()
