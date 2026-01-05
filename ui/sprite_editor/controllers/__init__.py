#!/usr/bin/env python3
"""
Controllers for the sprite editor.
Coordinate views and models in the MVC pattern.
"""

from .editing_controller import EditingController
from .extraction_controller import ExtractionController
from .injection_controller import InjectionController
from .main_controller import MainController

__all__ = [
    "EditingController",
    "ExtractionController",
    "InjectionController",
    "MainController",
]
