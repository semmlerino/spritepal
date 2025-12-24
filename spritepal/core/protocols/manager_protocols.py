"""
Protocol definitions for managers - DEPRECATED.

All manager protocols have been removed. Use concrete classes via DI:

- inject(CoreOperationsManager) for extraction and injection
- inject(ApplicationStateManager) for session/settings/state
- inject(ROMCache) for ROM caching
- inject(ROMExtractor) for ROM extraction
"""
from __future__ import annotations

# This file is kept for migration documentation.
# All protocols have been consolidated into concrete classes.
