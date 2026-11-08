"""Locations of bundled data. Each can be overridden by an environment variable."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("SAMAY_DATA_DIR", ROOT / "data"))
RULES_DIR = Path(os.environ.get("SAMAY_RULES_DIR", ROOT / "rules"))
EPHEMERIS_PATH = Path(os.environ.get("SAMAY_EPHEMERIS", DATA_DIR / "de440s.bsp"))
PROFILES_DIR = DATA_DIR / "profiles"
TIME_STANDARDS_DIR = DATA_DIR / "time_standards"
