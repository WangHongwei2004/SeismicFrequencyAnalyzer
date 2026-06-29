# -*- coding: utf-8 -*-
"""Application metadata and defaults."""

from __future__ import annotations

import sys
from pathlib import Path


APP_VERSION = "v1.1.0"
APP_AUTHOR = "WHW"
APP_COMPLETION_DATE = "2026.6.27"
APP_GITHUB_URL = "https://github.com/WangHongwei2004"

DEFAULT_MIN_PEAK_FREQUENCY_HZ = 0.0
DEFAULT_MAX_PEAK_FREQUENCY_HZ = 0.0


def load_default_peak_settings() -> tuple[float, float]:
    try:
        from dominant_frequency_two_methods import (
            PEAK_SEARCH_MAX_FREQUENCY_HZ,
            PEAK_SEARCH_MIN_FREQUENCY_HZ,
        )
    except ModuleNotFoundError:
        return DEFAULT_MIN_PEAK_FREQUENCY_HZ, DEFAULT_MAX_PEAK_FREQUENCY_HZ
    return PEAK_SEARCH_MIN_FREQUENCY_HZ, PEAK_SEARCH_MAX_FREQUENCY_HZ


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent
