"""
Signals Detector — Classify order flow signals from Strategy 1, Step 4.
Absorption, Imbalance Stacking, Delta Divergence, Iceberg Detection.
"""
import numpy as np
import pandas as pd
import logging
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

from . import config
from .footprint import FootprintBar, FootprintBuilder, ImbalanceStack
from .delta import DeltaEngine, Divergence
from .key_levels import KeyLevels
from .data_puller import DOMSnapshot

log = logging.getLogger(__name__)


class SignalType(Enum):
    ABSORPTION = "absorption"
    IMBALANCE_STACK = "imbalance_stack"
    DELTA_DIVERGENCE = "delta_divergence"
    ICEBERG = "iceberg"
    EXHAUSTION = "exhaustion"


@dataclass
class Signal:
    """A detected order flow signal."""
    signal_type: SignalType
    direction: str           # 'long' or 'short'
    key_level: float         # the level this signal was detected at
    confidence: float        # 0.0 - 1.0 (higher = stronger)
    bar_time: pd.Timestamp
    details: dict = field(default_factory=dict)

    def __str__(self):
        return (
            f"[{self.signal_type.value}] {self.direction.upper()} "
            f"at {self.key_level:.2f} (conf={self.confidence:.0%}) "
            f"@ {self.bar_time}"
        )


class SignalDetector:
    """
    Runs all signal detectors and classifies the best signal.
    Maps to Strategy 1, Step 3-4 (Read Order Flow → Signal Classification).
    """

    def __init__(
        self,
        footprint_builder: FootprintBuilder,
        delta_engine: DeltaEngine,
        tick_size: float,
    ):
        self.fp_builder = footprint_builder
        self.delta_engine = delta_engine
        self.tick_size = tick_size

    def scan_all(
        self,
        fp_bars: List[FootprintBar],
        key_levels: KeyLevels,
        current_price: float,
        tick_df: pd.DataFrame = None,
        dom: DOMSnapshot = None,
    ) -> List[Signal]:
        """
        Run all detectors on recent footprint bars near key levels.
        Returns all detected signals, sorted by confidence descending.
        """
        signals: List[Signal] = []
        proximity = config.PROXIMITY_TICKS * self.tick_size

        # Only analyze bars near key levels
        nearby_levels = key_levels.levels_within(current_price, proximity)
        if not nearby_levels:
            return []

        # Take the last few bars for analysis
        recent_bars = fp_bars[-5:] if len(fp_bars) > 5 else fp_bars

        for fp_bar in recent_bars:
            for level in nearby_levels:
                # ── 1. Absorption ──
                absorption = self._detect_absorption(fp_bar, level)
                if absorption:
                    signals.append(absorption)

                # ── 2. Imbalance Stacking ──
                imbalance_signals = self._detect_imbalance_stacking(fp_bar, level)
                signals.extend(imbalance_signals)

            # ── 3. Exhaustion ──
            exhaustion = self._detect_exhaustion(fp_bar, nearby_levels)
            if exhaustion:
                signals.append(exhaustion)

        # ── 4. Delta Divergence (across multiple bars) ──
        divergence_signals = self._detect_delta_divergence(nearby_levels)
        signals.extend(divergence_signals)

        # ── 5. Iceberg Detection (from tick data) ──
        if tick_df is not None:
            iceberg_signals = self._detect_iceberg(tick_df, nearby_levels)
            signals.extend(iceberg_signals)

        # Sort by confidence
        signals.sort(key=lambda s: s.confidence, reverse=True)
        return signals

    def classify_best_signal(
        self,
        fp_bars: List[FootprintBar],
        key_levels: KeyLevels,
        current_price: float,
        tick_df: pd.DataFrame = None,
        dom: DOMSnapshot = None,
    ) -> Optional[Signal]:
        """
        Run all detectors and return the single best signal, or None.
        This is the entry point for the scanner.
        """
        signals = self.scan_all(fp_bars, key_levels, current_price, tick_df, dom)
        if not signals:
            return None

        best = signals[0]
        log.info("Best signal: %s", best)
        return best

    # ── Absorption Detector ────────────────────────
    def _detect_absorption(self, fp_bar: FootprintBar, level: float) -> Optional[Signal]:
        result = self.fp_builder.detect_absorption(fp_bar, level)
        if result is None:
            return None

        direction = "long" if result["direction"] == "bullish" else "short"
        confidence = min(result["absorbed_vol"] / (config.ABSORPTION_VOL_MULTIPLIER * 100), 1.0)

        return Signal(
            signal_type=SignalType.ABSORPTION,
            direction=direction,
            key_level=level,
            confidence=confidence,
            bar_time=fp_bar.bar_time,
            details=result,
        )

    # ── Imbalance Stacking Detector ────────────────
    def _detect_imbalance_stacking(
        self, fp_bar: FootprintBar, level: float,
    ) -> List[Signal]:
        stacks = self.fp_builder.find_imbalance_stacks(fp_bar)
        signals = []
        for stack in stacks:
            if not stack.is_significant:
                continue

            direction = "long" if stack.direction == "bullish" else "short"
            # Confidence scales with number of consecutive imbalances
            confidence = min(stack.count / 6.0, 1.0)

            signals.append(Signal(
                signal_type=SignalType.IMBALANCE_STACK,
                direction=direction,
                key_level=level,
                confidence=confidence,
                bar_time=fp_bar.bar_time,
                details={
                    "count": stack.count,
                    "direction": stack.direction,
                    "avg_ratio": np.mean([imb.ratio for imb in stack.imbalances]),
                },
            ))
        return signals

    # ── Delta Divergence Detector ──────────────────
    def _detect_delta_divergence(self, nearby_levels: List[float]) -> List[Signal]:
        divergences = self.delta_engine.detect_divergences()
        signals = []
        for div in divergences:
            # Check if the divergence swing point is near a key level
            nearest_level = None
            min_dist = float("inf")
            for level in nearby_levels:
                dist = abs(div.price_swing2 - level)
                if dist < min_dist:
                    min_dist = dist
                    nearest_level = level

            if nearest_level is None:
                continue

            direction = "long" if div.direction == "bullish" else "short"

            signals.append(Signal(
                signal_type=SignalType.DELTA_DIVERGENCE,
                direction=direction,
                key_level=nearest_level,
                confidence=div.strength,
                bar_time=div.bar_time,
                details={
                    "price_swing1": div.price_swing1,
                    "price_swing2": div.price_swing2,
                    "delta_swing1": div.delta_swing1,
                    "delta_swing2": div.delta_swing2,
                },
            ))
        return signals

    # ── Exhaustion Detector ────────────────────────
    def _detect_exhaustion(
        self, fp_bar: FootprintBar, nearby_levels: List[float],
    ) -> Optional[Signal]:
        result = self.fp_builder.detect_exhaustion(fp_bar)
        if result is None:
            return None

        # Find nearest level
        check_price = fp_bar.bar_high if "bearish" in result["direction"] else fp_bar.bar_low
        nearest = min(nearby_levels, key=lambda lv: abs(lv - check_price), default=None)
        if nearest is None:
            return None

        direction = "short" if "bearish" in result["direction"] else "long"
        confidence = 1.0 - result["delta_ratio"]  # lower delta_ratio = stronger exhaustion

        return Signal(
            signal_type=SignalType.EXHAUSTION,
            direction=direction,
            key_level=nearest,
            confidence=confidence * 0.7,  # exhaustion alone is moderate
            bar_time=fp_bar.bar_time,
            details=result,
        )

    # ── Iceberg Detector (from raw ticks) ──────────
    def _detect_iceberg(
        self, tick_df: pd.DataFrame, nearby_levels: List[float],
    ) -> List[Signal]:
        """
        Detect iceberg orders: repeated small fills at the same price.
        Pattern: 10+ ticks at same price, consistent volume (±20%),
        total volume > 5× individual clip size.
        """
        signals = []
        if tick_df.empty:
            return signals

        # Only consider trade ticks with volume
        trades = tick_df[(tick_df["volume_real"] > 0)].copy()
        if trades.empty:
            return signals

        # Use 'last' price; fallback to mid
        price_col = "last"
        if (trades[price_col] <= 0).all():
            trades[price_col] = (trades["bid"] + trades["ask"]) / 2

        for level in nearby_levels:
            tol = config.PROXIMITY_TICKS * self.tick_size
            level_ticks = trades[abs(trades[price_col] - level) <= tol]

            if len(level_ticks) < config.ICEBERG_MIN_REPEATS:
                continue

            volumes = level_ticks["volume_real"].values
            median_vol = np.median(volumes)
            if median_vol <= 0:
                continue

            # Check consistency: most fills within ±tolerance of median
            within_tolerance = np.abs(volumes - median_vol) / median_vol < config.ICEBERG_VOL_TOLERANCE
            consistent_pct = within_tolerance.mean()

            total_vol = volumes.sum()
            ratio = total_vol / median_vol

            if consistent_pct > 0.6 and ratio > config.ICEBERG_TOTAL_VS_DISPLAY:
                # Determine direction from flags
                buy_count = level_ticks["is_buy"].sum()
                sell_count = level_ticks["is_sell"].sum()
                direction = "long" if buy_count > sell_count else "short"

                confidence = min(consistent_pct * (ratio / 10.0), 1.0)

                signals.append(Signal(
                    signal_type=SignalType.ICEBERG,
                    direction=direction,
                    key_level=level,
                    confidence=confidence,
                    bar_time=pd.Timestamp(level_ticks["datetime"].iloc[-1]),
                    details={
                        "fill_count": len(level_ticks),
                        "median_clip": median_vol,
                        "total_vol": total_vol,
                        "ratio": ratio,
                        "consistency": consistent_pct,
                    },
                ))

        return signals
