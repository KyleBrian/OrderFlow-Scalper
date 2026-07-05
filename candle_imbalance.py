"""
Candle Imbalance Detector — CRT (Candle Range Theory) edge detection.
Detects when one side of the candle has disproportionate volume.
This is a KEY sniper entry setup: high volume on one side, close on opposite side.

Example:
  Bullish imbalance = High volume on candle LOW, close at/near HIGH
  → Buyers came in at bottom, pushed up efficiently (fewer pushes needed)
  → Sniper entry = LONG on next candle's breakout above high
"""

import numpy as np
import pandas as pd
import logging
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

import config
from footprint import FootprintBar

log = logging.getLogger(__name__)


class ImbalanceDirection(Enum):
    """Detected candle imbalance direction."""
    BULLISH = "bullish"      # Volume at low, close at high = buyers dominant
    BEARISH = "bearish"      # Volume at high, close at low = sellers dominant
    BALANCED = "balanced"    # No significant imbalance


@dataclass
class CandleImbalance:
    """Detected candle imbalance pattern."""
    bar_time: pd.Timestamp
    direction: ImbalanceDirection
    volume_ratio: float          # ratio of larger_side_vol / smaller_side_vol
    imbalance_strength: float    # 0.0-1.0 (higher = stronger imbalance)
    entry_level: float           # proposed sniper entry (breakout of high/low)
    stop_loss: float             # tight stop on opposite side
    target_ratio: float          # RR expected from this setup
    details: dict = None


class CandleImbalanceDetector:
    """
    Detects candle imbalance patterns using footprint data.
    
    Theory:
    -------
    When volume is concentrated on one side of the candle body but price closes
    on the opposite side, it reveals buyer/seller strength:
    
    - BULLISH: Volume at LOW + CLOSE at/near HIGH
      Buyers absorbed selling pressure at bottom, then pushed with LESS volume.
      This means buyers are STRONG (efficient), sellers are WEAK.
      → Next candle breakout = continuation (sniper long)
    
    - BEARISH: Volume at HIGH + CLOSE at/near LOW  
      Sellers absorbed buying pressure at top, then pushed with LESS volume.
      This means sellers are STRONG, buyers are WEAK.
      → Next candle breakout = continuation (sniper short)
    """

    def __init__(self, tick_size: float):
        self.tick_size = tick_size

    def detect(
        self,
        fp_bar: FootprintBar,
        fp_bars_history: List[FootprintBar],
        context_bars: pd.DataFrame = None,
    ) -> Optional[CandleImbalance]:
        """
        Detect candle imbalance in a single bar.
        
        Parameters
        ----------
        fp_bar : FootprintBar
            The current bar to analyze
        fp_bars_history : List[FootprintBar]
            Historical bars for context (unused but useful for future refinements)
        context_bars : pd.DataFrame
            OHLC context bars (to confirm close position relative to candle range)
            
        Returns
        -------
        CandleImbalance or None
            If significant imbalance detected, returns analysis; else None.
        """
        if not fp_bar.levels or fp_bar.total_buy_vol == 0:
            return None

        # ──────────────────────────────────────────────────────────────────
        # Step 1: Separate high-half and low-half volume
        # ──────────────────────────────────────────────────────────────────
        candle_high = fp_bar.bar_high
        candle_low = fp_bar.bar_low
        candle_mid = (candle_high + candle_low) / 2.0

        low_half_vol = 0.0   # volume below midpoint
        high_half_vol = 0.0  # volume above midpoint

        for price, level in fp_bar.levels.items():
            if price < candle_mid:
                low_half_vol += level.total
            elif price > candle_mid:
                high_half_vol += level.total

        total_vol = low_half_vol + high_half_vol
        if total_vol == 0:
            return None

        low_half_pct = low_half_vol / total_vol
        high_half_pct = high_half_vol / total_vol

        # ──────────────────────────────────────────────────────────────────
        # Step 2: Determine imbalance direction
        # ──────────────────────────────────────────────────────────────────
        # If one side > 60% of total, we have an imbalance
        imbalance_threshold = config.CANDLE_IMBALANCE_VOLUME_RATIO_THRESHOLD  # default 0.60

        larger_vol = max(low_half_vol, high_half_vol)
        smaller_vol = min(low_half_vol, high_half_vol)

        if smaller_vol == 0:
            volume_ratio = float("inf")
        else:
            volume_ratio = larger_vol / smaller_vol

        # Determine which side is dominant
        if low_half_pct > imbalance_threshold:
            dominant_side = "low"
            imbalance_pct = low_half_pct
        elif high_half_pct > imbalance_threshold:
            dominant_side = "high"
            imbalance_pct = high_half_pct
        else:
            # No significant imbalance
            return None

        # ──────────────────────────────────────────────────────────────────
        # Step 3: Check if close confirms the imbalance
        # ──────────────────────────────────────────────────────────────────
        # Bullish: volume at LOW (dominant_side="low"), close at/near HIGH
        # Bearish: volume at HIGH (dominant_side="high"), close at/near LOW
        candle_body_size = candle_high - candle_low
        close_to_high = (candle_high - fp_bar.bar_close) / candle_body_size if candle_body_size > 0 else 0.5
        close_to_low = (fp_bar.bar_close - candle_low) / candle_body_size if candle_body_size > 0 else 0.5

        bullish_imbalance = (dominant_side == "low" and close_to_high < 0.33)
        bearish_imbalance = (dominant_side == "high" and close_to_low < 0.33)

        if not (bullish_imbalance or bearish_imbalance):
            # Imbalance detected but close doesn't confirm
            return None

        # ──────────────────────────────────────────────────────────────────
        # Step 4: Build the imbalance signal
        # ──────────────────────────────────────────────────────────────────
        direction = ImbalanceDirection.BULLISH if bullish_imbalance else ImbalanceDirection.BEARISH

        # Imbalance strength scales with deviation from balanced (50/50)
        imbalance_strength = abs(imbalance_pct - 0.5) * 2.0  # ranges 0.0 to 1.0 for 50%-100%

        # Sniper entry: breakout of the high/low of this candle
        if direction == ImbalanceDirection.BULLISH:
            entry_level = candle_high + self.tick_size  # enter on breakout above high
            stop_loss = candle_low - self.tick_size  # tight stop below low
        else:
            entry_level = candle_low - self.tick_size  # enter on breakout below low
            stop_loss = candle_high + self.tick_size  # tight stop above high

        # Expected risk/reward: candle high/low is 1R, expect 2-3R target
        risk_ticks = abs(entry_level - stop_loss) / self.tick_size
        target_ticks = risk_ticks * 2.0  # conservative 2:1 RR
        target_ratio = 2.0

        imbalance = CandleImbalance(
            bar_time=fp_bar.bar_time,
            direction=direction,
            volume_ratio=volume_ratio,
            imbalance_strength=min(imbalance_strength, 1.0),
            entry_level=entry_level,
            stop_loss=stop_loss,
            target_ratio=target_ratio,
            details={
                "candle_high": candle_high,
                "candle_low": candle_low,
                "candle_close": fp_bar.bar_close,
                "low_half_vol": low_half_vol,
                "high_half_vol": high_half_vol,
                "low_half_pct": low_half_pct,
                "high_half_pct": high_half_pct,
                "dominant_side": dominant_side,
                "volume_ratio": volume_ratio,
            },
        )

        log.info(
            "Candle imbalance detected [%s] @ %s: strength=%.1f%% "
            "entry=%.2f stop=%.2f vol_ratio=%.2f",
            direction.value, fp_bar.bar_time, imbalance_strength * 100,
            entry_level, stop_loss, volume_ratio,
        )

        return imbalance

    def detect_multiple(
        self,
        fp_bars: List[FootprintBar],
        context_bars: pd.DataFrame = None,
    ) -> List[CandleImbalance]:
        """
        Scan multiple bars for imbalances. Returns strongest recent signals.
        """
        imbalances = []
        for i, fp_bar in enumerate(fp_bars[-5:]):  # scan last 5 bars only
            imb = self.detect(fp_bar, fp_bars, context_bars)
            if imb:
                imbalances.append(imb)

        return imbalances
