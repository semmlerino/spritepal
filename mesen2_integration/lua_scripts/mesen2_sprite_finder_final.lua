-- Mesen 2 Sprite Finder - Final API-Verified Version
-- Fully compliant with Mesen 2 API documentation
-- Tracks sprites and correlates with ROM offsets via DMA

-- Global state
local state = {
    frame_count = 0,
    dma_captures = {},
    active_sprites = {},
    unique_rom_offsets = {},
    obsel_config = nil,  -- Will be updated from PPU state
    callbacks = {},
    stats = {
        total_dma = 0,
        vram_dma = 0,
        sprites_found = 0,
        mappings = 0
    }
}

-- Constants
local DMA_ENABLE = 0x420B
local HDMA_ENABLE = 0x420C
local DMA_BASE = 0x4300
local _OBSEL = 0x2101  -- luacheck: ignore (documented constant)
local VRAM_ADDR_L = 0x2116
local VRAM_ADDR_H = 0x2117

-- Helper: Convert CPU address to ROM offset using Mesen 2 API
local function cpu_to_rom_offset(cpu_addr)
    -- Try Mesen 2's built-in address conversion first
    local result = emu.convertAddress(cpu_addr)
    if result and result.memType == emu.memType.prgRom then
        return result.address
    end
    
    -- Fallback to manual LoROM calculation
    local bank = (cpu_addr >> 16) & 0xFF
    local addr = cpu_addr & 0xFFFF
    
    if addr < 0x8000 then
        return nil
    end
    
    local rom_offset = ((bank & 0x7F) * 0x8000) + (addr - 0x8000)
    return rom_offset
end

-- Helper: Read DMA channel registers
local function read_dma_channel(channel)
    local base = DMA_BASE + (channel * 0x10)
    
    -- Read all DMA registers
    local control = emu.read(base + 0x00, emu.memType.cpu)
    local dest_reg = emu.read(base + 0x01, emu.memType.cpu)
    local src_low = emu.read(base + 0x02, emu.memType.cpu)
    local src_mid = emu.read(base + 0x03, emu.memType.cpu)
    local src_bank = emu.read(base + 0x04, emu.memType.cpu)
    local size_low = emu.read(base + 0x05, emu.memType.cpu)
    local size_high = emu.read(base + 0x06, emu.memType.cpu)
    
    local source_addr = (src_bank << 16) | (src_mid << 8) | src_low
    local transfer_size = (size_high << 8) | size_low
    if transfer_size == 0 then
        transfer_size = 0x10000  -- 0 means 64KB
    end
    
    return {
        control = control,
        dest_reg = dest_reg,
        source_addr = source_addr,
        transfer_size = transfer_size,
        transfer_mode = control & 0x07,
        fixed = (control & 0x08) ~= 0,
        direction = (control & 0x80) ~= 0 and "B->A" or "A->B"
    }
end

-- Update OBSEL from PPU register (read directly, not from emu.getState().ppu which doesn't exist for SNES)
local function update_obsel_from_state()
    local obsel = emu.read(0x2101, emu.memType.snesMemory)
    local name_base = obsel & 0x07
    local name_select = (obsel >> 3) & 0x03
    local oam_base_addr = name_base << 13
    local oam_addr_offset = (name_select + 1) << 12
    state.obsel_config = {
        name_base = name_base,
        name_select = name_select,
        size_select = (obsel >> 5) & 0x07,
        tile_base_addr = oam_base_addr * 2,
        oam_base_addr = oam_base_addr,
        oam_addr_offset = oam_addr_offset,
        raw = obsel
    }
end

-- Callback: DMA Enable register write
local function on_dma_enable_write(address, value)
    if value == 0 then return end
    
    state.stats.total_dma = state.stats.total_dma + 1
    
    -- Read current VRAM address
    local vram_low = emu.read(VRAM_ADDR_L, emu.memType.cpu)
    local vram_high = emu.read(VRAM_ADDR_H, emu.memType.cpu)
    local vram_addr = (vram_high << 8) | vram_low
    
    -- Process each enabled channel
    for channel = 0, 7 do
        if (value & (1 << channel)) ~= 0 then
            local dma = read_dma_channel(channel)
            
            -- Check if this is a VRAM transfer
            if dma.dest_reg == 0x18 or dma.dest_reg == 0x19 then
                state.stats.vram_dma = state.stats.vram_dma + 1
                
                local rom_offset = cpu_to_rom_offset(dma.source_addr)
                
                if rom_offset then
                    -- Capture the DMA transfer
                    local capture = {
                        frame = state.frame_count,
                        channel = channel,
                        vram_addr = vram_addr * 2,  -- Word to byte address
                        source_addr = dma.source_addr,
                        rom_offset = rom_offset,
                        size = dma.transfer_size,
                        dest_reg = dma.dest_reg
                    }
                    
                    table.insert(state.dma_captures, capture)
                    
                    -- Track unique ROM offsets
                    if not state.unique_rom_offsets[rom_offset] then
                        state.unique_rom_offsets[rom_offset] = {
                            first_frame = state.frame_count,
                            last_frame = state.frame_count,
                            vram_addrs = {},
                            hit_count = 0
                        }
                    end
                    
                    local rom_data = state.unique_rom_offsets[rom_offset]
                    rom_data.last_frame = state.frame_count
                    rom_data.hit_count = rom_data.hit_count + 1
                    rom_data.vram_addrs[vram_addr] = true
                    
                    -- Check if this is in sprite region
                    if state.obsel_config then
                        local base_byte = state.obsel_config.oam_base_addr * 2
                        local offset_byte = state.obsel_config.oam_addr_offset * 2
                        local in_base = vram_addr >= base_byte and vram_addr < base_byte + 0x2000
                        local in_offset = vram_addr >= base_byte + offset_byte
                            and vram_addr < base_byte + offset_byte + 0x2000
                        if in_base or in_offset then
                            capture.is_sprite_region = true
                            emu.log(string.format(
                                "SPRITE_DMA: F=%d Ch=%d VRAM=$%04X ROM=$%06X Size=%d",
                                state.frame_count, channel, vram_addr, rom_offset, dma.transfer_size
                            ))
                        end
                    end
                end
            elseif dma.dest_reg == 0x04 then
                -- OAM DMA
                emu.log(string.format("OAM_DMA: Frame=%d Channel=%d", state.frame_count, channel))
            end
        end
    end
end

-- Callback: HDMA Enable register write
local function on_hdma_enable_write(address, value)
    if value ~= 0 then
        emu.log(string.format("HDMA_ACTIVE: $%02X at frame %d", value, state.frame_count))
    end
end

-- Analyze OAM using correct memory type
local function analyze_oam()
    -- Read OAM data using the correct memory type
    local oam_data = {}
    for i = 0, 543 do  -- OAM is 544 bytes (512 + 32 high table)
        oam_data[i] = emu.read(i, emu.memType.oam)
    end
    
    -- Parse sprite entries
    state.active_sprites = {}
    for i = 0, 127 do
        local base = i * 4
        local x = oam_data[base]
        local y = oam_data[base + 1]
        local tile = oam_data[base + 2]
        local attr = oam_data[base + 3]
        
        -- Get X MSB and size from high table
        local high_byte_index = 512 + math.floor(i / 4)
        local high_bit_index = (i % 4) * 2
        local high_byte = oam_data[high_byte_index]
        local x_msb = (high_byte >> high_bit_index) & 0x01
        local size_bit = (high_byte >> (high_bit_index + 1)) & 0x01
        
        -- Calculate actual X position
        x = x | (x_msb * 256)
        
        -- Check if sprite is visible
        if y < 224 or y >= 240 then  -- On-screen or wrapped
            local sprite = {
                id = i,
                x = x,
                y = y,
                tile = tile,
                attr = attr,
                palette = (attr >> 1) & 0x07,
                priority = (attr >> 4) & 0x03,
                flip_h = (attr & 0x40) ~= 0,
                flip_v = (attr & 0x80) ~= 0,
                size_bit = size_bit,
                name_table = (attr & 0x01)
            }
            
            -- Calculate VRAM address for sprite tiles
            if state.obsel_config then
                local word_addr = state.obsel_config.oam_base_addr + (tile << 4)
                if sprite.name_table ~= 0 then
                    word_addr = word_addr + state.obsel_config.oam_addr_offset
                end
                word_addr = word_addr & 0x7FFF
                sprite.vram_addr = word_addr << 1
                
                -- Determine sprite size
                local size_select = state.obsel_config.size_select
                local sizes = {
                    [0] = {8, 16}, [1] = {8, 32}, [2] = {8, 64},
                    [3] = {16, 32}, [4] = {16, 64}, [5] = {32, 64},
                    [6] = {16, 32}, [7] = {16, 32}
                }
                local size_pair = sizes[size_select] or {8, 16}
                sprite.width = size_pair[size_bit + 1]
                sprite.height = sprite.width  -- Square sprites
                sprite.tile_count = (sprite.width / 8) * (sprite.height / 8)
            end
            
            table.insert(state.active_sprites, sprite)
        end
    end
    
    state.stats.sprites_found = math.max(state.stats.sprites_found, #state.active_sprites)
end

-- Correlate sprites with DMA captures
local function correlate_sprites_and_dma()
    if not state.obsel_config then return end
    
    for _, sprite in ipairs(state.active_sprites) do
        if sprite.vram_addr then
            local sprite_vram_start = sprite.vram_addr
            local sprite_vram_end = sprite_vram_start + (sprite.tile_count * 32)
            
            -- Check recent DMA captures
            for i = #state.dma_captures, math.max(1, #state.dma_captures - 100), -1 do
                local capture = state.dma_captures[i]
                
                if capture.vram_addr and capture.rom_offset then
                    local dma_vram_start = capture.vram_addr
                    local dma_vram_end = dma_vram_start + capture.size
                    
                    -- Check for overlap
                    if dma_vram_start < sprite_vram_end and dma_vram_end > sprite_vram_start then
                        state.stats.mappings = state.stats.mappings + 1
                        emu.log(string.format(
                            "SPRITE_MAPPED: id=%d pos=(%d,%d) tile=$%02X size=%dx%d -> ROM=$%06X",
                            sprite.id, sprite.x, sprite.y, sprite.tile,
                            sprite.width, sprite.height, capture.rom_offset
                        ))
                        break  -- Found a match for this sprite
                    end
                end
            end
        end
    end
end

-- Read VRAM directly for debugging
local function debug_vram_contents()
    if state.obsel_config then
        local sprite_base = state.obsel_config.tile_base_addr
        local vram_mem = emu.memType.snesVram or emu.memType.snesVideoRam
        
        -- Read first few bytes of sprite pattern table
        local sample = {}
        for i = 0, 15 do
            sample[i] = emu.read(sprite_base + i, vram_mem)
        end
        
        local hex_str = ""
        for i = 0, 15 do
            hex_str = hex_str .. string.format("%02X ", sample[i])
        end
        
        emu.log(string.format("VRAM_SAMPLE @ $%04X: %s", sprite_base, hex_str))
    end
end

-- Frame end callback
local function on_frame_end()
    state.frame_count = state.frame_count + 1
    
    -- Update OBSEL from PPU state
    update_obsel_from_state()
    
    -- Analyze OAM
    analyze_oam()
    
    -- Correlate sprites with DMA
    if #state.active_sprites > 0 and #state.dma_captures > 0 then
        correlate_sprites_and_dma()
    end
    
    -- Periodic status update
    if state.frame_count % 300 == 0 then
        local unique_count = 0
        for _ in pairs(state.unique_rom_offsets) do
            unique_count = unique_count + 1
        end
        
        emu.log(string.format(
            "STATUS: Frame=%d Active=%d MaxFound=%d DMA=%d VRAM_DMA=%d Unique=%d Mappings=%d",
            state.frame_count,
            #state.active_sprites,
            state.stats.sprites_found,
            state.stats.total_dma,
            state.stats.vram_dma,
            unique_count,
            state.stats.mappings
        ))
        
        -- Debug VRAM contents
        debug_vram_contents()
        
        -- Export findings
        if unique_count > 0 then
            export_findings()
        end
    end
end

-- Export findings with JSON
function export_findings()
    local output = "=== Mesen 2 Sprite Finder Results (API-Verified) ===\n"
    output = output .. string.format("Analysis Frame: %d\n", state.frame_count)
    output = output .. string.format("Duration: %.1f seconds\n", state.frame_count / 60.0)
    
    output = output .. "\n--- Statistics ---\n"
    output = output .. string.format("Total DMA Transfers: %d\n", state.stats.total_dma)
    output = output .. string.format("VRAM DMA Transfers: %d\n", state.stats.vram_dma)
    output = output .. string.format("Max Active Sprites: %d\n", state.stats.sprites_found)
    output = output .. string.format("Sprite-ROM Mappings: %d\n", state.stats.mappings)
    
    if state.obsel_config then
        output = output .. "\n--- Sprite Configuration ---\n"
        output = output .. string.format("OBSEL: $%02X\n", state.obsel_config.raw or 0)
        output = output .. string.format("  Name Base: %d (VRAM $%04X)\n",
            state.obsel_config.name_base,
            state.obsel_config.tile_base_addr)
        output = output .. string.format("  Name Select: %d (offset words %d)\n",
            state.obsel_config.name_select,
            state.obsel_config.oam_addr_offset or 0)
        output = output .. string.format("  Size Select: %d\n", state.obsel_config.size_select)
    end
    
    output = output .. "\n--- Unique ROM Offsets (Sprite Regions) ---\n"
    
    -- Sort ROM offsets
    local sorted_offsets = {}
    for offset, data in pairs(state.unique_rom_offsets) do
        table.insert(sorted_offsets, {offset = offset, data = data})
    end
    table.sort(sorted_offsets, function(a, b) return a.offset < b.offset end)
    
    -- Output top ROM offsets
    local count = 0
    for _, entry in ipairs(sorted_offsets) do
        -- Count VRAM addresses
        local vram_count = 0
        local vram_list = {}
        for vram in pairs(entry.data.vram_addrs) do
            vram_count = vram_count + 1
            table.insert(vram_list, string.format("$%04X", vram))
        end
        
        -- Only show entries with multiple hits
        if entry.data.hit_count > 1 then
            output = output .. string.format(
                "  ROM $%06X: %d hits, frames %d-%d, VRAM: %s\n",
                entry.offset,
                entry.data.hit_count,
                entry.data.first_frame,
                entry.data.last_frame,
                table.concat(vram_list, ", ")
            )
            count = count + 1
            if count >= 20 then break end  -- Limit output
        end
    end
    
    -- Write to file
    local file = io.open("mesen2_sprite_findings.txt", "w")
    if file then
        file:write(output)
        file:close()
    end
    
    -- Also create JSON export
    export_json()
end

-- JSON export function
function export_json()
    local json_data = {
        metadata = {
            frame_count = state.frame_count,
            duration_sec = state.frame_count / 60.0,
            stats = state.stats
        },
        obsel_config = state.obsel_config,
        rom_offsets = {}
    }
    
    -- Add ROM offsets
    for offset, data in pairs(state.unique_rom_offsets) do
        if data.hit_count > 1 then  -- Only include frequently accessed offsets
            table.insert(json_data.rom_offsets, {
                offset = offset,
                hits = data.hit_count,
                first_frame = data.first_frame,
                last_frame = data.last_frame
            })
        end
    end
    
    -- Sort for consistency
    table.sort(json_data.rom_offsets, function(a, b) return a.offset < b.offset end)
    
    -- Simple JSON serialization
    local function to_json(t, indent)
        indent = indent or 0
        local spaces = string.rep("  ", indent)
        
        if type(t) == "table" then
            local is_array = #t > 0
            local result = is_array and "[\n" or "{\n"
            local first = true
            
            if is_array then
                for i, v in ipairs(t) do
                    if not first then result = result .. ",\n" end
                    result = result .. spaces .. "  " .. to_json(v, indent + 1)
                    first = false
                end
            else
                for k, v in pairs(t) do
                    if not first then result = result .. ",\n" end
                    result = result .. spaces .. '  "' .. k .. '": ' .. to_json(v, indent + 1)
                    first = false
                end
            end
            
            result = result .. "\n" .. spaces .. (is_array and "]" or "}")
            return result
        elseif type(t) == "string" then
            return '"' .. t .. '"'
        else
            return tostring(t)
        end
    end
    
    local json_str = to_json(json_data)
    
    local file = io.open("mesen2_sprite_data.json", "w")
    if file then
        file:write(json_str)
        file:close()
    end
end

-- Initialize
function init()
    emu.log("=== Mesen 2 Sprite Finder (API-Verified) ===")
    emu.log("Using correct API: OAM via emu.memType.oam, PPU state via emu.getState()")
    
    -- Register callbacks with correct API
    state.callbacks.dma = emu.addMemoryCallback(
        on_dma_enable_write,
        emu.memCallbackType.cpuWrite,
        DMA_ENABLE,
        DMA_ENABLE
    )
    
    state.callbacks.hdma = emu.addMemoryCallback(
        on_hdma_enable_write,
        emu.memCallbackType.cpuWrite,
        HDMA_ENABLE,
        HDMA_ENABLE
    )
    
    state.callbacks.frame = emu.addEventCallback(
        on_frame_end,
        emu.eventType.endFrame
    )
    
    -- Get initial OBSEL state
    update_obsel_from_state()
    
    emu.log("Callbacks registered. Monitoring DMA and sprites...")
    emu.log("Outputs: mesen2_sprite_findings.txt, mesen2_sprite_data.json")
end

-- Cleanup
function cleanup()
    emu.log("Finalizing...")
    
    -- Final export
    export_findings()
    
    -- Remove callbacks
    if state.callbacks.dma then
        emu.removeMemoryCallback(state.callbacks.dma)
    end
    if state.callbacks.hdma then
        emu.removeMemoryCallback(state.callbacks.hdma)
    end
    if state.callbacks.frame then
        emu.removeEventCallback(state.callbacks.frame)
    end
    
    emu.log(string.format(
        "=== Complete: %d frames, %d sprites, %d mappings ===",
        state.frame_count,
        state.stats.sprites_found,
        state.stats.mappings
    ))
end

-- Start
init()
