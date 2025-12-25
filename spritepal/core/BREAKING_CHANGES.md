# Breaking Change Checklist

Use this checklist before making changes to core infrastructure.
These changes have historically caused "spooky action at a distance" bugs.

## Before Changing Manager Initialization Order

**Files**: `core/managers/registry.py`, `core/di_container.py`

- [ ] Update `MANAGER_DEPENDENCIES` dict with new dependency
- [ ] Update `MANAGER_TO_PROTOCOLS` if protocols change
- [ ] Verify `MANAGED_CLASSES` order satisfies all dependencies
- [ ] Update `docs/initialization_flow.md`
- [ ] Run full test suite: `uv run pytest -n 0` (serial, catches init race conditions)

**Why it matters**: Managers depend on each other via DI. Wrong order = cryptic "No registration for X" errors.

---

## Before Changing Signal Signatures

**Files**: `core/managers/*.py`, `core/workers/*.py`, `ui/*.py`

- [ ] Find all `.connect()` calls for this signal:
  ```bash
  rg "signal_name\.connect" --type py
  ```
- [ ] Update all lambda/slot signatures to match
- [ ] Update `docs/SIGNALS.md` with new signature
- [ ] Check for dynamic connections (signals stored in dicts/lists)

**Why it matters**: Signal/slot signature mismatches fail silently at runtime, not compile time.

---

## Before Changing Protocol Methods

**Files**: `core/protocols/dialog_protocols.py`

- [ ] Find all implementations:
  ```bash
  rg "class.*\(.*ProtocolName" --type py
  ```
- [ ] Find all consumers using `inject()`:
  ```bash
  rg "inject\(ProtocolName" --type py
  ```
- [ ] Update all implementations and callers
- [ ] Run type checker: `uv run basedpyright core ui`

**Why it matters**: Protocol changes break duck typing silently. Type checker catches this.

---

## Before Changing Singleton Reset Methods

**Files**: `core/managers/registry.py`, `tests/fixtures/core_fixtures.py`

- [ ] Check `reset_all_singletons()` in `tests/fixtures/core_fixtures.py`
- [ ] Ensure reset order matches initialization order (reverse)
- [ ] Test both `isolated_managers` and `session_managers` fixtures
- [ ] Run parallel tests: `uv run pytest -n auto`
- [ ] Run serial tests: `uv run pytest -n 0`

**Why it matters**: Incomplete resets cause test pollution. Parallel tests expose race conditions.

---

## Before Changing DialogBase or Widget Base Classes

**Files**: `ui/components/base/dialog_base.py`

- [ ] Check all subclasses:
  ```bash
  rg "class.*\(DialogBase" --type py
  ```
- [ ] Verify `_setup_ui()` timing is preserved
- [ ] Ensure instance variables are declared BEFORE `super().__init__()`
- [ ] Test dialogs that override `__init__`

**Why it matters**: DialogBase enforces init order. Breaking it causes AttributeError on widget access.

---

## Before Changing Settings Keys

**Files**: `utils/constants.py`, `core/managers/application_state_manager.py`

- [ ] Find all usages of the key:
  ```bash
  rg "SETTINGS_KEY_NAME" --type py
  ```
- [ ] Plan migration for existing user settings files
- [ ] Add backward compatibility read (old key → new key)
- [ ] Update any UI that displays the setting

**Why it matters**: Users have existing settings files. Changing keys loses their configuration.

---

## Before Changing Cache Key Formats

**Files**: `core/services/rom_cache.py`, `core/async_rom_cache.py`

- [ ] Document the old format
- [ ] Add migration code to handle old format
- [ ] Consider cache invalidation strategy
- [ ] Test with existing cache files

**Why it matters**: Cache format changes invalidate users' cached data silently.

---

## Before Adding a New Manager

1. [ ] Create manager class in `core/managers/`
2. [ ] Add to `MANAGER_DEPENDENCIES` (document what it needs)
3. [ ] Add to `MANAGER_TO_PROTOCOLS` (document what it provides)
4. [ ] Add to `MANAGED_CLASSES` in correct order
5. [ ] Register in `initialize_managers()` after dependencies
6. [ ] Export from `core/managers/__init__.py`
7. [ ] Update `docs/application_flows.md` initialization section
8. [ ] Add tests using `isolated_managers` fixture

**Note**: Protocols are only needed for UI/dialog factories. Most managers use concrete classes directly via `inject()`.

---

## Before Adding a New Service

**Files**: `core/services/`

1. [ ] Create service file in `core/services/`
2. [ ] Export from `core/services/__init__.py`
3. [ ] Update `docs/architecture.md` Services Layer section
4. [ ] Update `docs/application_flows.md` Quick Reference section
5. [ ] Add tests for the service

**Current services**:
- `dump_file_detection_service.py` - Auto-detection of VRAM/CGRAM/OAM dump files
- `extraction_readiness_service.py` - Validation for extraction readiness
- `image_utils.py` - Image format conversions
- `lru_cache.py` - LRU cache implementation
- `palette_utils.py` - Palette handling utilities
- `path_suggestion_service.py` - File path suggestions
- `preview_generator.py` - Thumbnail/preview generation (singleton)
- `rom_cache.py` - ROM file caching
- `rom_service.py` - ROM file operations
- `vram_service.py` - VRAM extraction operations
- `worker_lifecycle.py` - Background worker management

---

## Quick Validation Commands

```bash
# Type check (catches protocol mismatches)
uv run basedpyright core ui

# Lint (catches import issues)
uv run ruff check .

# Full test suite, serial (catches init order bugs)
uv run pytest -n 0 --tb=short

# Full test suite, parallel (catches race conditions)
uv run pytest -n auto --tb=short

# Find signal connections for a specific signal
rg "extraction_progress\.connect" --type py

# Find all inject() calls for a class
rg "inject\(CoreOperationsManager" --type py
```

---

*When in doubt, run the full test suite both serial (`-n 0`) and parallel (`-n auto`).*
