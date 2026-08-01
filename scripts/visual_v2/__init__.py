"""
visual_v2 — Abstract Lo-fi Radio Interface visual generator.

12 themes, spinning vinyl record, EQ spectrum visualizer,
animated now-playing panel, floating orbs, perspective grid.

Quick start:
    from scripts.visual_v2 import generate_visual, ALL_THEMES
    path, theme = generate_visual("neon_tokyo", duration_secs=30,
                                  visual_seed=7, track_title="city lights",
                                  genre="lo-fi hip hop")
"""

from .generate import generate_visual
from .themes import ALL_THEMES, THEMES

__all__ = ["generate_visual", "ALL_THEMES", "THEMES"]
