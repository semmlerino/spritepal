#!/usr/bin/env python3
"""
Launch script for the unified sprite editor.
Starts the editor application with Extract → Edit → Inject workflow.
"""

import sys

from ui.sprite_editor import SpriteEditorApplication


def main() -> int:
    """Launch the sprite editor application."""
    app = SpriteEditorApplication()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
