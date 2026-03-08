"""
Key Levels — Compute all important price levels from Strategy 1, Step 1.
Previous Day H/L/C, VPOC, HVN/LVN, Opening Range, Overnight H/L,
Weekly & Monthly VWAP, Naked POCs.
"""
import numpy as np
import pandas as pd
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from . import config
from .data_puller import DataPuller, BarData
from .volume_profile import VolumeProfile, build_volume_profile

log = logging.getLogger(__name__)


@dataclass
class KeyLevels:
    """All key levels for the current session."""
    prev_day_high: float = 0.0
    prev_day_low: float = 0.0
    prev_day_close: float = 0.0

    vpoc: float = 0.0
    vah: float = 0.0
    val: float = 0.0
    hvn_levels: List[float] = field(default_factory=list)
    lvn_levels: List[float] = field(default_factory=list)

    opening_range_high: float = 0.0
    opening_range_low: float = 0.0

    overnight_high: float = 0.0
    overnight_low: float = 0.0

    weekly_vwap: float = 0.0
    monthly_vwap: float = 0.0

    naked_pocs: List[float] = field(default_factory=list)

    def all_levels(self) -> List[float]:
        """Return a flat list of all non-zero *structural* key levels
        (excludes raw HVN/LVN tick-level lists to avoid thousands of entries).
        """
        singles = [
            self.prev_day_high, self.prev_day_low, self.prev_day_close,
            self.vpoc, self.vah, self.val,
            self.opening_range_high, self.opening_range_low,
            self.overnight_high, self.overnight_low,
            self.weekly_vwap, self.monthly_vwap,
        ]
        levels = [lv for lv in singles if lv > 0]
        levels.extend([lv for lv in self.naked_pocs if lv > 0])
        return sorted(set(levels))

    def is_near_hvn(self, price: float, distance: float) -> bool:
        """Check if price is near any HVN (used for confluence, not signal trigger)."""
        return any(abs(price - lv) <= distance for lv in self.hvn_levels)

    def is_near_lvn(self, price: float, distance: float) -> bool:
        """Check if price is near any LVN (price should move quickly through these)."""
        return any(abs(price - lv) <= distance for lv in self.lvn_levels)

    def nearest_level(self, price: float) -> Optional[float]:
        """Find the closest key level to current price."""
        levels = self.all_levels()
        if not levels:
            return None
        return min(levels, key=lambda lv: abs(lv - price))

    def levels_within(self, price: float, distance: float) -> List[float]:
        """Return all key levels within `distance` of current price."""
        return [lv for lv in self.all_levels() if abs(lv - price) <= distance]


class KeyLevelBuilder:
    """Computes all key levels from fresh MT5 data."""

    def __init__(self, puller: DataPuller, tick_size: float):
        self.puller = puller
        self.tick_size = tick_size

    def build(self, volume_profile: Optional[VolumeProfile] = None) -> KeyLevels:
        """Compute all key levels. Call at session start and periodically."""
        kl = KeyLevels()

        # Previous day High / Low / Close
        self._set_prev_day(kl)

        # Volume Profile levels (pass in external or None)
        if volume_profile:
            kl.vpoc = volume_profile.vpoc
            kl.vah = volume_profile.vah
            kl.val = volume_profile.val
            kl.hvn_levels = volume_profile.hvn_levels
            kl.lvn_levels = volume_profile.lvn_levels

        # Opening Range (first 15 minutes)
        self._set_opening_range(kl)

        # Overnight High / Low
        self._set_overnight(kl)

        # Weekly & Monthly VWAP
        self._set_anchored_vwaps(kl)

        log.info(
            "Key levels built — PDH=%.2f PDL=%.2f VPOC=%.2f ORH=%.2f ORL=%.2f",
            kl.prev_day_high, kl.prev_day_low, kl.vpoc,
            kl.opening_range_high, kl.opening_range_low,
        )
        return kl

    # ── Previous Day H/L/C ─────────────────────────
    def _set_prev_day(self, kl: KeyLevels):
        bars = self.puller.pull_daily_bars(count=5)
        if bars is None or len(bars.df) < 2:
            log.warning("Cannot compute prev day levels — not enough daily bars")
            return
        prev = bars.df.iloc[-2]  # second-to-last bar = yesterday
        kl.prev_day_high = float(prev["high"])
        kl.prev_day_low = float(prev["low"])
        kl.prev_day_close = float(prev["close"])

    # ── Opening Range (first 15 min of session) ────
    def _set_opening_range(self, kl: KeyLevels):
        """High/Low of first 15 minutes of current session."""
        bars = self.puller.pull_bars(timeframe=config.TIMEFRAME_PRIMARY, count=500)
        if bars is None or bars.df.empty:
            return

        df = bars.df.copy()
        today = datetime.now(timezone.utc).date()
        df_today = df[df["datetime"].dt.date == today]
        if df_today.empty:
            return

        session_start = df_today["datetime"].iloc[0]
        first_15 = df_today[df_today["datetime"] < session_start + timedelta(minutes=15)]
        if first_15.empty:
            return

        kl.opening_range_high = float(first_15["high"].max())
        kl.opening_range_low = float(first_15["low"].min())

    # ── Overnight High / Low ───────────────────────
    def _set_overnight(self, kl: KeyLevels):
        """
        High/Low between previous session close and current session open.
        Uses M5 bars to cover overnight period.
        """
        now_utc = datetime.now(timezone.utc)
        # Approximate: overnight = yesterday 21:00 UTC to today session open
        overnight_start = (now_utc - timedelta(days=1)).replace(hour=21, minute=0, second=0)
        overnight_end = now_utc.replace(hour=0, minute=0, second=0)

        if overnight_start >= overnight_end:
            overnight_end = now_utc  # same day, use up to now

        bars = self.puller.pull_bars_range(
            timeframe=config.TIMEFRAME_CONTEXT,
            date_from=overnight_start,
            date_to=overnight_end,
        )
        if bars is None or bars.df.empty:
            return

        kl.overnight_high = float(bars.df["high"].max())
        kl.overnight_low = float(bars.df["low"].min())

    # ── Anchored VWAPs (Weekly & Monthly) ──────────
    def _set_anchored_vwaps(self, kl: KeyLevels):
        """Compute VWAP anchored from start of current week and month."""
        now_utc = datetime.now(timezone.utc)

        # Weekly VWAP: anchor from Monday 00:00 UTC
        monday = now_utc - timedelta(days=now_utc.weekday())
        monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        kl.weekly_vwap = self._compute_anchored_vwap(monday, now_utc)

        # Monthly VWAP: anchor from 1st of month 00:00 UTC
        month_start = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        kl.monthly_vwap = self._compute_anchored_vwap(month_start, now_utc)

    def _compute_anchored_vwap(self, anchor: datetime, end: datetime) -> float:
        """
        VWAP = Σ(TP × Volume) / Σ(Volume)
        where TP = (H + L + C) / 3
        """
        bars = self.puller.pull_bars_range(
            timeframe=config.TIMEFRAME_PRIMARY,
            date_from=anchor,
            date_to=end,
        )
        if bars is None or bars.df.empty:
            return 0.0

        df = bars.df
        tp = (df["high"] + df["low"] + df["close"]) / 3
        vol = df["real_volume"]
        if vol.sum() == 0:
            vol = df["tick_volume"]  # fallback for forex
        if vol.sum() == 0:
            return 0.0

        vwap = (tp * vol).sum() / vol.sum()
        return float(vwap)
