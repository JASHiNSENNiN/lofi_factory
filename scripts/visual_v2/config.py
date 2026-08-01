"""
config.py — Abstract Lo-fi Radio Interface layout constants.
"""

import os

# ── Resolution & paths ─────────────────────────────────────────────────────
W, H    = 1280, 720          # was 1920×1080 — 720p encodes ~3× faster
FPS     = 24
VISUALS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "visuals")
os.makedirs(VISUALS_DIR, exist_ok=True)

# ── Header bar (top strip) ──────────────────────────────────────────────────
HEADER_H    = 54             # scaled 2/3 from 80
HEADER_MID  = HEADER_H // 2

# ── Vinyl record (left side) ────────────────────────────────────────────────
VINYL_CX      = 260          # scaled from 390
VINYL_CY      = 223          # scaled from 335
VINYL_R       = 147          # scaled from 220
VINYL_LABEL_R = 43           # scaled from 65
VINYL_HOLE_R  = 4            # scaled from 5

# Content divider: vinyl lives in x 0-493, now-playing in x 513-1240
DIVIDER_X = 493              # scaled from 740

# ── Now-Playing panel (right side) ─────────────────────────────────────────
NP_X0   = 513                # scaled from 770
NP_Y0   = 67                 # scaled from 100
NP_X1   = W - 40            # scaled margin from 60 → 40
NP_Y1   = 373                # scaled from 560

# Progress bar inside NP panel
PROG_Y      = NP_Y0 + 253   # scaled from NP_Y0+380
PROG_X0     = NP_X0
PROG_X1     = NP_X1
PROG_H      = 6

# ── EQ Visualizer (bottom section) ─────────────────────────────────────────
EQ_BARS     = 35             # scaled from 52
EQ_X0       = 20             # scaled from 30
EQ_X1       = W - 20        # scaled from W-30
EQ_Y_BOT    = 673            # scaled from 1010
EQ_MAX_H    = 273            # scaled from 410
EQ_MIN_H    = 4              # scaled from 6
EQ_GAP      = 3              # scaled from 4

# ── Floating orbs (background atmosphere) ──────────────────────────────────
ORB_COUNT   = 21             # scaled from 32

# ── VU Meters ───────────────────────────────────────────────────────────────
VU_L_CX     = NP_X0 + 40    # scaled from NP_X0+60
VU_R_CX     = NP_X0 + 107   # scaled from NP_X0+160
VU_CY       = NP_Y0 + 193   # scaled from NP_Y0+290
VU_R        = 30             # scaled from 45

# ── Clock (header right) ────────────────────────────────────────────────────
CLOCK_X     = W - 120        # scaled from W-180
CLOCK_Y     = HEADER_MID

# Channel watermark
CHANNEL_NAME = "Lofi Streams"
