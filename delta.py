"""
Delta Module — Bar delta, cumulative delta, and delta divergence detection.
"""
import numpy as np
import pandas as pd
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import config
from footprint import FootprintBar

log = logging.getLogger(__name__)


@dataclass
class DeltaBar:
    """Delta values for a single bar."""
    bar_time: pd.Timestamp
    buy_vol: float
    sell_vol: float
    delta: float          # buy_vol - sell_vol
    cum_delta: float      # running sum from session start
    close: float          # bar close price


@dataclass
class Divergence:
    """A detected delta divergence."""
    direction: str        # 'bullish' or 'bearish'
    price_swing1: float   # first swing point price
    price_swing2: float   # second swing point price
    delta_swing1: float   # delta at first swing
    delta_swing2: float   # delta at second swing
    bar_time: pd.Timestamp  # time of the second swing (detection point)
    strength: float       # how strong the divergence is (0-1)


class DeltaEngine:
    """Computes bar delta, cumulative delta, and divergence detection."""

    def __init__(self):
        self.delta_bars: List[DeltaBar] = []
        self._cum_delta: float = 0.0

    def reset(self):
        """Reset for a new session."""
        self.delta_bars.clear()
        self._cum_delta = 0.0

    # ── Build Delta from Footprint Bars ────────────
    def compute_from_footprint(self, fp_bars: List[FootprintBar]) -> List[DeltaBar]:
        """
        Compute delta series from footprint bars.
        Call once with full session's footprint bars.
        """
        self.reset()
        for fp in fp_bars:
            self._cum_delta += fp.bar_delta
            db = DeltaBar(
                bar_time=fp.bar_time,
                buy_vol=fp.total_buy_vol,
                sell_vol=fp.total_sell_vol,
                delta=fp.bar_delta,
                cum_delta=self._cum_delta,
                close=fp.bar_close,
            )
            self.delta_bars.append(db)
        return self.delta_bars

    # ── Build Delta Directly from Ticks + Bars ─────
    def compute_from_ticks(
        self,
        tick_df: pd.DataFrame,
        bar_df: pd.DataFrame,
    ) -> List[DeltaBar]:
        """
        Compute delta series by aggregating ticks into bar boundaries.
        Faster than building full footprint when only delta is needed.
        """
        self.reset()
        if tick_df.empty or bar_df.empty:
            return []

        for i in range(len(bar_df)):
            row = bar_df.iloc[i]
            bar_start = row["datetime"]
            bar_end = bar_df.iloc[i + 1]["datetime"] if i < len(bar_df) - 1 else bar_start + pd.Timedelta(minutes=1)

            mask = (tick_df["datetime"] >= bar_start) & (tick_df["datetime"] < bar_end)
            bar_ticks = tick_df[mask]

            buy_v = float(bar_ticks["buy_vol"].sum())
            sell_v = float(bar_ticks["sell_vol"].sum())
            delta = buy_v - sell_v
            self._cum_delta += delta

            self.delta_bars.append(DeltaBar(
                bar_time=bar_start,
                buy_vol=buy_v,
                sell_vol=sell_v,
                delta=delta,
                cum_delta=self._cum_delta,
                close=float(row["close"]),
            ))

        return self.delta_bars

    # ── Append Single Bar (for real-time updates) ──
    def append_bar(self, fp_bar: FootprintBar) -> DeltaBar:
        """Append a new bar to the running delta series."""
        self._cum_delta += fp_bar.bar_delta
        db = DeltaBar(
            bar_time=fp_bar.bar_time,
            buy_vol=fp_bar.total_buy_vol,
            sell_vol=fp_bar.total_sell_vol,
            delta=fp_bar.bar_delta,
            cum_delta=self._cum_delta,
            close=fp_bar.bar_close,
        )
        self.delta_bars.append(db)
        return db

    # ── Delta Divergence Detection ─────────────────
    def detect_divergences(
        self,
        lookback: int = None,
        min_swing: int = None,
    ) -> List[Divergence]:
        """
        Detect delta divergences in the delta bar series.

        Bullish divergence: price makes lower low, but delta makes higher low.
        Bearish divergence: price makes higher high, but delta makes lower high.
        """
        lb = lookback or config.DELTA_DIVERGENCE_LOOKBACK
        ms = min_swing or config.DELTA_DIVERGENCE_MIN_SWING

        if len(self.delta_bars) < lb:
            return []

        recent = self.delta_bars[-lb:]
        prices = np.array([db.close for db in recent])
        deltas = np.array([db.cum_delta for db in recent])
        times = [db.bar_time for db in recent]

        divergences: List[Divergence] = []

        # Find swing lows (for bullish divergence)
        lows = self._find_swing_lows(prices, ms)
        for i in range(1, len(lows)):
            idx1, idx2 = lows[i - 1], lows[i]
            if prices[idx2] < prices[idx1] and deltas[idx2] > deltas[idx1]:
                strength = self._divergence_strength(
                    prices[idx1], prices[idx2], deltas[idx1], deltas[idx2],
                )
                divergences.append(Divergence(
                    direction="bullish",
                    price_swing1=prices[idx1],
                    price_swing2=prices[idx2],
                    delta_swing1=deltas[idx1],
                    delta_swing2=deltas[idx2],
                    bar_time=times[idx2],
                    strength=strength,
                ))

        # Find swing highs (for bearish divergence)
        highs = self._find_swing_highs(prices, ms)
        for i in range(1, len(highs)):
            idx1, idx2 = highs[i - 1], highs[i]
            if prices[idx2] > prices[idx1] and deltas[idx2] < deltas[idx1]:
                strength = self._divergence_strength(
                    prices[idx1], prices[idx2], deltas[idx1], deltas[idx2],
                )
                divergences.append(Divergence(
                    direction="bearish",
                    price_swing1=prices[idx1],
                    price_swing2=prices[idx2],
                    delta_swing1=deltas[idx1],
                    delta_swing2=deltas[idx2],
                    bar_time=times[idx2],
                    strength=strength,
                ))

        return divergences

    # ── Current Cumulative Delta ───────────────────
    @property
    def current_cum_delta(self) -> float:
        return self._cum_delta

    @property
    def last_bar_delta(self) -> float:
        return self.delta_bars[-1].delta if self.delta_bars else 0.0

    def is_delta_supporting(self, direction: str) -> bool:
        """Check if recent delta supports the given trade direction."""
        if len(self.delta_bars) < 3:
            return False
        recent_deltas = [db.delta for db in self.delta_bars[-3:]]
        avg_recent = np.mean(recent_deltas)
        if direction == "long":
            return avg_recent > 0
        elif direction == "short":
            return avg_recent < 0
        return False

    def is_delta_reversing(self, direction: str) -> bool:
        """Check if delta is flipping against the trade direction."""
        if len(self.delta_bars) < 2:
            return False
        last_delta = self.delta_bars[-1].delta
        prev_delta = self.delta_bars[-2].delta
        if direction == "long":
            return last_delta < 0 and prev_delta < 0
        elif direction == "short":
            return last_delta > 0 and prev_delta > 0
        return False

    # ── Swing Detection Helpers ────────────────────
    @staticmethod
    def _find_swing_lows(data: np.ndarray, min_gap: int) -> List[int]:
        """Find local minima indices with minimum gap between swings."""
        lows = []
        for i in range(1, len(data) - 1):
            if data[i] < data[i - 1] and data[i] <= data[i + 1]:
                if not lows or (i - lows[-1]) >= min_gap:
                    lows.append(i)
        return lows

    @staticmethod
    def _find_swing_highs(data: np.ndarray, min_gap: int) -> List[int]:
        """Find local maxima indices with minimum gap between swings."""
        highs = []
        for i in range(1, len(data) - 1):
            if data[i] > data[i - 1] and data[i] >= data[i + 1]:
                if not highs or (i - highs[-1]) >= min_gap:
                    highs.append(i)
        return highs

    @staticmethod
    def _divergence_strength(p1: float, p2: float, d1: float, d2: float) -> float:
        """
        Heuristic strength metric for a divergence (0-1).
        Considers how far price deviated vs how much delta diverged.
        """
        price_move = abs(p2 - p1) / max(abs(p1), 1e-10)
        delta_move = abs(d2 - d1) / max(abs(d1), 1e-10)
        raw = min(price_move + delta_move, 2.0) / 2.0
        return round(raw, 3)
