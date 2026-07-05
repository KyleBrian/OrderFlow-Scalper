"""
ICT Order Block Detector — Smart Money Accumulation/Distribution Zones.
Based on Inner Circle Trader (ICT) concepts.

Order Block = The price zone where smart money (institutions) accumulated or distributed
BEFORE a sharp move away.

Pattern Recognition:
  1. Consolidation zone (high volume, tight range)
  2. Followed by a breakout/move away
  3. Price later retraces to that consolidation zone
  4. At the retracement, we see LOWER volume (no support yet)
  5. Entry at order block = high-probability reversal/bounce

This is where you WANT to be for sniper entries.
"""

import numpy as np
import pandas as pd
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum

from . import config
from .footprint import FootprintBar

log = logging.getLogger(__name__)


class OrderBlockType(Enum):
    """Type of order block."""
    ACCUMULATION = "accumulation"  # buyers accumulated before bullish breakout
    DISTRIBUTION = "distribution"  # sellers distributed before bearish breakout


@dataclass
class OrderBlock:
    """Detected ICT order block zone."""
    block_type: OrderBlockType
    high: float                  # upper boundary of the order block zone
    low: float                   # lower boundary of the order block zone
    mid: float                   # center of the zone
    strength: float              # 0.0-1.0 (higher = more volume in zone, cleaner breakout)
    formed_at: pd.Timestamp      # when the order block was formed (time of consolidation)
    breakout_time: pd.Timestamp  # when price broke out of this zone
    breakout_direction: str      # 'bullish' or 'bearish'
    consolidation_bars: int      # how many bars consolidated in this zone
    breakout_bars: int           # how many bars since breakout
    volume_in_block: float       # total volume in consolidation
    volume_during_breakout: float # volume during breakout candle
    details: dict = None


class OrderBlockDetector:
    """
    Detects ICT order blocks from footprint bars.
    
    Algorithm:
    ----------
    1. Scan for consolidation zones (multiple consecutive bars, tight range, high volume)
    2. Check if a breakout follows (candle with larger range breaks out of zone)
    3. Tag that consolidation zone as an ORDER BLOCK
    4. Track when price returns to it for sniper entries
    """

    def __init__(self, tick_size: float):
        self.tick_size = tick_size

    def detect_order_blocks(
        self,
        fp_bars: List[FootprintBar],
        lookback: int = 20,  # scan last 20 bars for order blocks
    ) -> List[OrderBlock]:
        """
        Scan recent bars for order block formations.
        
        Parameters
        ----------
        fp_bars : List[FootprintBar]
            Historical footprint bars
        lookback : int
            How many bars back to scan for blocks
            
        Returns
        -------
        List[OrderBlock]
            Detected order blocks, sorted by recency and strength
        """
        if len(fp_bars) < 5:
            return []

        order_blocks = []
        recent_bars = fp_bars[-lookback:] if len(fp_bars) >= lookback else fp_bars

        # Scan for consolidation zones followed by breakouts
        for i in range(2, len(recent_bars) - 1):
            prev_bars = recent_bars[:i]
            current_bar = recent_bars[i]
            future_bars = recent_bars[i + 1:]

            # Check if consolidation happened before current bar
            consolidation = self._find_consolidation(prev_bars, min_bars=3)
            if not consolidation:
                continue

            cons_high, cons_low, cons_start_idx, cons_bars, cons_vol = consolidation

            # Check if current bar breaks out of consolidation
            if not self._is_breakout(current_bar, cons_high, cons_low):
                continue

            # Determine breakout direction
            if current_bar.bar_low > cons_high:
                breakout_direction = "bullish"
                block_type = OrderBlockType.ACCUMULATION
            elif current_bar.bar_high < cons_low:
                breakout_direction = "bearish"
                block_type = OrderBlockType.DISTRIBUTION
            else:
                continue

            # Calculate order block properties
            block_strength = self._calculate_block_strength(
                consolidation_bars=cons_bars,
                breakout_bar=current_bar,
                consolidation_high=cons_high,
                consolidation_low=cons_low,
                consolidation_vol=cons_vol,
            )

            # Create order block
            ob = OrderBlock(
                block_type=block_type,
                high=cons_high,
                low=cons_low,
                mid=(cons_high + cons_low) / 2.0,
                strength=block_strength,
                formed_at=prev_bars[cons_start_idx].bar_time,
                breakout_time=current_bar.bar_time,
                breakout_direction=breakout_direction,
                consolidation_bars=cons_bars,
                breakout_bars=len(future_bars),  # how many bars since breakout
                volume_in_block=cons_vol,
                volume_during_breakout=current_bar.total_buy_vol + current_bar.total_sell_vol,
                details={
                    "consolidation_high": cons_high,
                    "consolidation_low": cons_low,
                    "consolidation_vol": cons_vol,
                    "consolidation_duration_bars": cons_bars,
                    "breakout_range": abs(current_bar.bar_high - current_bar.bar_low),
                },
            )

            order_blocks.append(ob)

        # Sort by recency (most recent first) then by strength
        order_blocks.sort(
            key=lambda ob: (-ob.breakout_bars, -ob.strength)
        )

        return order_blocks

    def _find_consolidation(
        self,
        bars: List[FootprintBar],
        min_bars: int = 3,
    ) -> Optional[Tuple[float, float, int, int, float]]:
        """
        Find the most recent consolidation zone.
        
        Returns
        -------
        Tuple of (high, low, start_idx, num_bars, total_volume) or None
        """
        if len(bars) < min_bars:
            return None

        # Work backwards from the end
        best_consolidation = None
        current_idx = len(bars) - 1

        while current_idx >= min_bars - 1:
            # Check if bars from (current_idx - min_bars + 1) to current_idx form a consolidation
            test_bars = bars[current_idx - min_bars + 1:current_idx + 1]

            # Consolidation criteria:
            # 1. All bars touch roughly the same price range
            # 2. Total volume is high (accumulation/distribution)
            # 3. Range is tight (no large wicks)

            highs = [b.bar_high for b in test_bars]
            lows = [b.bar_low for b in test_bars]
            range_max = max(highs)
            range_min = min(lows)
            range_size = range_max - range_min

            total_vol = sum(b.total_buy_vol + b.total_sell_vol for b in test_bars)

            # Tight range check: range should be small relative to individual candles
            avg_candle_range = np.mean([b.bar_high - b.bar_low for b in test_bars])
            if avg_candle_range == 0:
                avg_candle_range = 0.01
            range_ratio = range_size / avg_candle_range

            # Consolidation = tight range, multiple bars, decent volume
            is_tight = range_ratio < 3.0  # allow up to 3x avg candle size
            has_volume = total_vol > (config.CONSOLIDATION_MIN_VOLUME if hasattr(config, 'CONSOLIDATION_MIN_VOLUME') else 100)

            if is_tight and has_volume:
                if best_consolidation is None or len(test_bars) > best_consolidation[3]:
                    best_consolidation = (range_max, range_min, current_idx - min_bars + 1, len(test_bars), total_vol)

            current_idx -= 1

        return best_consolidation

    def _is_breakout(self, bar: FootprintBar, cons_high: float, cons_low: float) -> bool:
        """
        Check if a bar represents a breakout from consolidation.
        Breakout = price goes cleanly above/below the consolidation zone.
        """
        cons_range = cons_high - cons_low
        tolerance = cons_range * 0.1  # allow 10% overlap

        bullish_breakout = bar.bar_low > (cons_high - tolerance)
        bearish_breakout = bar.bar_high < (cons_low + tolerance)

        return bullish_breakout or bearish_breakout

    def _calculate_block_strength(
        self,
        consolidation_bars: int,
        breakout_bar: FootprintBar,
        consolidation_high: float,
        consolidation_low: float,
        consolidation_vol: float,
    ) -> float:
        """
        Calculate strength of order block (0.0 to 1.0).
        Stronger = more bars consolidated, higher volume, cleaner breakout.
        """
        strength = 0.0

        # Factor 1: Number of consolidation bars (longer = stronger)
        strength += min(consolidation_bars / 10.0, 0.5)

        # Factor 2: Volume in consolidation (higher = stronger)
        # Normalize by breakout volume
        breakout_vol = breakout_bar.total_buy_vol + breakout_bar.total_sell_vol
        if breakout_vol > 0:
            vol_ratio = consolidation_vol / (breakout_vol + 1)
            strength += min(vol_ratio / 5.0, 0.3)

        # Factor 3: Breakout cleanness (candle range relative to consolidation)
        cons_range = consolidation_high - consolidation_low
        breakout_range = breakout_bar.bar_high - breakout_bar.bar_low
        if cons_range > 0:
            breakout_ratio = breakout_range / cons_range
            strength += min(breakout_ratio / 3.0, 0.2)

        return min(strength, 1.0)

    def find_triggered_blocks(
        self,
        current_price: float,
        order_blocks: List[OrderBlock],
        proximity_ticks: int = 5,
    ) -> List[OrderBlock]:
        """
        Find order blocks that price is currently testing/retesting.
        This is where sniper entries happen.
        
        Parameters
        ----------
        current_price : float
            Current market price
        order_blocks : List[OrderBlock]
            All detected order blocks
        proximity_ticks : int
            How many ticks away from block to consider "at block"
            
        Returns
        -------
        List[OrderBlock]
            Blocks being tested, sorted by proximity
        """
        proximity_distance = proximity_ticks * self.tick_size
        triggered = []

        for ob in order_blocks:
            # Check if price is within block zone
            dist_to_high = abs(current_price - ob.high)
            dist_to_low = abs(current_price - ob.low)
            dist_to_block = min(dist_to_high, dist_to_low)

            if dist_to_block <= proximity_distance:
                triggered.append(ob)

        # Sort by proximity (closest first)
        triggered.sort(key=lambda ob: abs(current_price - ob.mid))
        return triggered
