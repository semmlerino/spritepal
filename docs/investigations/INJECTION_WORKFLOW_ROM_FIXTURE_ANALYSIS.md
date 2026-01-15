# Task 2.3: Injection Workflow ROM Fixture Consolidation Analysis

## Summary

**Decision:** Keep custom `test_rom_file` fixture with improved documentation.

**Status:** ✅ Complete - Custom fixture documented and tests passing (22/22)

## Analysis

### Custom Fixture Requirements

The custom fixture in `tests/integration/test_injection_workflow_integration.py` creates a 2MB ROM with:

1. **SNES LoROM header at 0x7FC0** with standard fields
2. **HAL-compressed sprite signature at offset 0x100000**: `\x00\x10\x00\x00`
3. Specific header values (title, map mode, ROM size, checksums, etc.)

### Shared Fixture Capabilities

The shared `test_rom_file` factory in `tests/fixtures/test_data_fixtures.py` supports:

- ✅ 2MB ROM size via `size="large"`
- ✅ SNES header via `with_header=True`
- ✅ Sprite patterns via `with_sprites=True`
- ✅ UUID-based unique patterns for cache collision prevention

### Incompatibility

**Critical difference:** Sprite data location

| Fixture | Sprite Data Locations |
|---------|----------------------|
| Custom | **0x100000** (single offset with HAL signature) |
| Shared | 0x10000, 0x20000, 0x30000 (multiple offsets with tile patterns) |

### Tests Depending on 0x100000 Offset

Multiple tests explicitly reference this offset:

1. **test_sprite_png fixture (line 117)**: Metadata `"rom_offset": "0x100000"`
2. **test_save_and_load_settings (line 347)**: `save_rom_injection_settings(..., "0x100000", ...)`
3. **Custom fixture (line 90)**: Sprite data explicitly placed at 0x100000

Changing this would require:
- Updating metadata in test fixtures
- Modifying test assertions
- Potentially breaking injection validation logic that checks for HAL-compressed signatures

## Implementation

### Changes Made

Enhanced the custom fixture's docstring to clearly document:
- Why it's a custom fixture (can't use shared factory)
- What specific requirements necessitate it
- What data structures it creates

**File:** `tests/integration/test_injection_workflow_integration.py` (lines 38-95)

```python
@pytest.fixture
def test_rom_file(tmp_path) -> Path:
    """Create a test ROM file with realistic data.

    CUSTOM FIXTURE - Cannot use shared test_rom_file factory because:
    1. Tests explicitly depend on sprite data at offset 0x100000
    2. Requires specific HAL-compressed signature at that location
    3. Metadata in test_sprite_png references this exact offset

    Creates a 2MB LoROM with:
    - Valid SNES header at 0x7FC0
    - HAL-compressed sprite signature at 0x100000
    """
```

### Verification

✅ All 22 tests pass
✅ Ruff linting passes
✅ basedpyright type checking passes (0 errors, 0 warnings)

## Recommendations

1. **Keep custom fixture** - The offset dependency is intentional and required
2. **Documentation added** - Clear explanation prevents future refactoring attempts
3. **No further action needed** - Tests are stable and well-documented

## Alternative Considered

**Refactor shared fixture to support custom offsets:**

Could extend the shared `test_rom_file` factory with:
```python
test_rom_file(
    size="large",
    with_header=True,
    sprite_offsets=[0x100000],
    sprite_signature=b"\x00\x10\x00\x00"
)
```

**Rejected because:**
- Adds complexity for a single test file
- The injection workflow tests have unique requirements
- Current solution is simpler and more maintainable

## Related Files

- Custom fixture: `tests/integration/test_injection_workflow_integration.py`
- Shared factory: `tests/fixtures/test_data_fixtures.py`
- Test data factory: `tests/fixtures/test_data_factory.py` (complete test setups)

## Future Considerations

If more tests need the 0x100000 sprite offset pattern, consider:
1. Extract the custom fixture to a dedicated module
2. Extend the shared factory with custom offset support
3. Document the offset convention in test documentation

For now, the single-file custom fixture with clear documentation is the right solution.
