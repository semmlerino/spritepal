-- sprite_labeler.lua
-- Labels sprites on-screen with their OAM index
-- CLEAN MODE: Only labels sprite under mouse cursor

local show_all = false      -- F9 toggles this
local show_boxes = false    -- F10 toggles this
local hover_radius = 24     -- Pixels from mouse to show label

local oam_sizes = {
    [0] = {{8,8}, {16,16}},   -- 8x8 + 16x16
    [1] = {{8,8}, {32,32}},   -- 8x8 + 32x32
    [2] = {{8,8}, {64,64}},   -- 8x8 + 64x64
    [3] = {{16,16}, {32,32}}, -- 16x16 + 32x32
    [4] = {{16,16}, {64,64}}, -- 16x16 + 64x64
    [5] = {{32,32}, {64,64}}, -- 32x32 + 64x64
    [6] = {{16,32}, {32,64}}, -- 16x32 + 32x64
    [7] = {{16,32}, {32,32}}  -- 16x32 + 32x32
}

local function get_sprite_info(index)
    local base = index * 4

    local x_low = emu.read(base, emu.memType.snesSpriteRam)
    local y = emu.read(base + 1, emu.memType.snesSpriteRam)
    local tile = emu.read(base + 2, emu.memType.snesSpriteRam)
    local attr = emu.read(base + 3, emu.memType.snesSpriteRam)

    -- High table byte
    local high_offset = 0x200 + math.floor(index / 4)
    local high_byte = emu.read(high_offset, emu.memType.snesSpriteRam)
    local shift = (index % 4) * 2
    local x_high = (high_byte >> shift) & 1
    local large = ((high_byte >> shift) >> 1) & 1

    -- Sign-extend X coordinate
    local x = x_low + (x_high * 256)
    if x >= 256 then
        x = x - 512
    end

    -- Get size based on OAM mode (read from PPU state)
    local state = emu.getState()
    local oam_mode = state["snes.ppu.oamMode"] or 0
    local size_table = oam_sizes[oam_mode] or oam_sizes[0]
    local size = size_table[large + 1]
    local width = size[1]
    local height = size[2]

    return {
        index = index,
        x = x,
        y = y,
        tile = tile,
        palette = (attr >> 1) & 7,
        priority = (attr >> 4) & 3,
        hflip = (attr >> 6) & 1,
        vflip = (attr >> 7) & 1,
        large = large,
        width = width,
        height = height,
        use_second_table = attr & 1
    }
end

local function is_visible(spr)
    -- Check if sprite is on screen
    local screen_height = 224  -- or 239 for overscan

    -- X visibility (sprite can wrap)
    local x_visible = (spr.x + spr.width > 0) and (spr.x < 256)

    -- Y visibility (sprite can wrap at 256)
    local y_end = spr.y + spr.height
    local y_visible = false
    if y_end <= 256 then
        y_visible = (spr.y < screen_height) and (y_end > 0)
    else
        -- Wraps from bottom to top
        y_visible = (spr.y < screen_height) or ((y_end - 256) > 0)
    end

    return x_visible and y_visible
end

local selected_sprite = -1

-- Colors for different priority levels
local priority_colors = {
    [0] = 0xFF0000,  -- Red (lowest)
    [1] = 0xFFFF00,  -- Yellow
    [2] = 0x00FF00,  -- Green
    [3] = 0x00FFFF   -- Cyan (highest)
}

local function is_near_mouse(spr, mouse)
    -- Check if sprite is near mouse cursor
    local cx = spr.x + spr.width / 2
    local cy = spr.y + spr.height / 2
    local dx = math.abs(mouse.x - cx)
    local dy = math.abs(mouse.y - cy)
    return dx < (spr.width / 2 + hover_radius) and dy < (spr.height / 2 + hover_radius)
end

local function point_in_sprite(spr, mx, my)
    return mx >= spr.x and mx < spr.x + spr.width and
           my >= spr.y and my < spr.y + spr.height
end

local function draw_sprites()
    local mouse = emu.getMouseState()
    local visible_sprites = {}
    local sprites_under_cursor = {}

    for i = 0, 127 do
        local spr = get_sprite_info(i)
        if is_visible(spr) then
            table.insert(visible_sprites, spr)
            if point_in_sprite(spr, mouse.x, mouse.y) then
                table.insert(sprites_under_cursor, spr)
            end
        end
    end

    -- Draw boxes if enabled
    if show_boxes then
        for _, spr in ipairs(visible_sprites) do
            local color = priority_colors[spr.priority] or 0xFFFFFF
            if spr.index == selected_sprite then
                color = 0xFF00FF
            end
            emu.drawRectangle(math.max(0, spr.x), spr.y, spr.width, spr.height, color, false)
        end
    end

    -- Show all mode
    if show_all then
        for _, spr in ipairs(visible_sprites) do
            emu.drawString(math.max(0, spr.x), spr.y, tostring(spr.index), 0xFFFFFF, 0x000000)
        end
    else
        -- Clean mode: show stacked list of sprites under cursor
        if #sprites_under_cursor > 0 then
            -- Draw info box at top of screen
            local info_y = 8
            emu.drawRectangle(4, 4, 80, 10 + #sprites_under_cursor * 10, 0x000000, true)
            emu.drawString(8, info_y, "Under cursor:", 0xFFFF00, 0x000000)
            info_y = info_y + 10

            for _, spr in ipairs(sprites_under_cursor) do
                local text = string.format("#%d (%dx%d)", spr.index, spr.width, spr.height)
                emu.drawString(8, info_y, text, 0xFFFFFF, 0x000000)
                info_y = info_y + 10
            end
        end
    end

    -- Highlight selected sprite
    if selected_sprite >= 0 then
        local spr = get_sprite_info(selected_sprite)
        if is_visible(spr) then
            emu.drawRectangle(spr.x, spr.y, spr.width, spr.height, 0xFF00FF, false)
            emu.drawString(spr.x, spr.y - 10, "SEL:" .. selected_sprite, 0xFF00FF, 0x000000)
        end
    end

    -- Draw crosshair
    if mouse.x >= 0 and mouse.x < 256 and mouse.y >= 0 and mouse.y < 224 then
        emu.drawLine(mouse.x - 8, mouse.y, mouse.x + 8, mouse.y, 0xFFFFFF)
        emu.drawLine(mouse.x, mouse.y - 8, mouse.x, mouse.y + 8, 0xFFFFFF)
    end
end

local function print_sprite_details(index)
    local spr = get_sprite_info(index)

    emu.log("========================================")
    emu.log(string.format("SPRITE #%d DETAILS", index))
    emu.log("========================================")
    emu.log(string.format("Position: (%d, %d)", spr.x, spr.y))
    emu.log(string.format("Size: %dx%d (large=%d)", spr.width, spr.height, spr.large))
    emu.log(string.format("Tile: $%02X", spr.tile))
    emu.log(string.format("Palette: %d", spr.palette))
    emu.log(string.format("Priority: %d", spr.priority))
    emu.log(string.format("H-Flip: %d, V-Flip: %d", spr.hflip, spr.vflip))
    emu.log(string.format("Second Table: %d", spr.use_second_table))

    -- Calculate VRAM address
    local state = emu.getState()
    local oam_base = state["snes.ppu.oamBaseAddress"] or 0
    local oam_offset = state["snes.ppu.oamAddressOffset"] or 0

    local tile_addr = oam_base + (spr.tile * 16)
    if spr.use_second_table == 1 then
        tile_addr = tile_addr + oam_offset
    end
    tile_addr = (tile_addr & 0x7FFF) * 2  -- Convert to byte address

    emu.log(string.format("VRAM Address: $%04X", tile_addr))
    emu.log("========================================")
end

-- Input handling
local prev_f9 = false
local prev_f10 = false
local prev_f11 = false

local function check_input()
    local f9 = emu.isKeyPressed("F9")
    local f10 = emu.isKeyPressed("F10")
    local f11 = emu.isKeyPressed("F11")

    -- F9: Toggle show all labels
    if f9 and not prev_f9 then
        show_all = not show_all
        emu.displayMessage("Show All", show_all and "ON" or "OFF (hover mode)")
    end

    -- F10: Toggle boxes
    if f10 and not prev_f10 then
        show_boxes = not show_boxes
        emu.displayMessage("Boxes", show_boxes and "ON" or "OFF")
    end

    -- F11: Print details for ALL sprites under cursor
    if f11 and not prev_f11 then
        local mouse = emu.getMouseState()
        if mouse.x >= 0 and mouse.x < 256 and mouse.y >= 0 and mouse.y < 224 then
            local found_any = false
            emu.log("")
            emu.log("=== SPRITES AT (" .. mouse.x .. ", " .. mouse.y .. ") ===")

            for i = 0, 127 do
                local spr = get_sprite_info(i)
                if is_visible(spr) and point_in_sprite(spr, mouse.x, mouse.y) then
                    found_any = true
                    selected_sprite = i  -- Select last one found
                    print_sprite_details(i)
                end
            end

            if not found_any then
                emu.log("No sprites at this position")
            end
        end
    end

    prev_f9 = f9
    prev_f10 = f10
    prev_f11 = f11
end

-- Register callbacks
emu.addEventCallback(function()
    draw_sprites()
    check_input()
end, emu.eventType.endFrame)

emu.log("========================================")
emu.log("SPRITE LABELER - CLEAN MODE")
emu.log("========================================")
emu.log("Hover over sprites - list appears top-left")
emu.log("")
emu.log("F11 = Print VRAM details for all sprites")
emu.log("      under cursor (check console output)")
emu.log("F9  = Toggle show ALL labels")
emu.log("F10 = Toggle bounding boxes")
emu.log("========================================")
