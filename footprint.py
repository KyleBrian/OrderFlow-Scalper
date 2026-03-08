"""
Footprint Chart Builder — Bid×Ask volume matrix per bar per price level.
Detects diagonal imbalances, absorption, and exhaustion patterns.
"""
import numpy as np
import pandas as pd
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import config

log = logging.getLogger(__name__)


@dataclass
class FootprintLevel:
    """Volume breakdown at a single price level within one bar."""
    price: float
    bid_vol: float  # volume from sellers hitting the bid (TICK_FLAG_SELL)
    ask_vol: float  # volume from buyers lifting the ask (TICK_FLAG_BUY)

    @property
    def delta(self) -> float:
        return self.ask_vol - self.bid_vol

    @property
    def total(self) -> float:
        return self.bid_vol + self.ask_vol


@dataclass
class FootprintBar:
    """Footprint data for one bar (M1 or M5)."""
    bar_time: pd.Timestamp
    bar_open: float
    bar_high: float
    bar_low: float
    bar_close: float
    levels: Dict[float, FootprintLevel]  # price → FootprintLevel
    total_buy_vol: float = 0.0
    total_sell_vol: float = 0.0

    @property
    def bar_delta(self) -> float:
        return self.total_buy_vol - self.total_sell_vol

    @property
    def is_bullish(self) -> bool:
        return self.bar_close >= self.bar_open


@dataclass
class DiagonalImbalance:
    """A detected diagonal imbalance in the footprint."""
    price: float
    ratio: float  # ask_vol[price] / bid_vol[price - tick]
    direction: str  # 'bullish' or 'bearish'


@dataclass
class ImbalanceStack:
    """Consecutive diagonal imbalances in one direction."""
    bar_time: pd.Timestamp
    imbalances: List[DiagonalImbalance]
    direction: str  # 'bullish' or 'bearish'
    count: int

    @property
    def is_significant(self) -> bool:
        return self.count >= config.MIN_CONSECUTIVE_IMBALANCES


class FootprintBuilder:
    """
    Builds footprint charts from tick data aligned to OHLCV bar boundaries.
    """

    def __init__(self, tick_size: float):
        self.tick_size = tick_size

    def build_footprint(
        self,
        tick_df: pd.DataFrame,
        bar_df: pd.DataFrame,
    ) -> List[FootprintBar]:
        """
        Build footprint bars by mapping ticks to their parent bar.

        Parameters
        ----------
        tick_df : DataFrame from DataPuller with columns
                  [datetime, last, volume_real, buy_vol, sell_vol, is_buy, is_sell]
        bar_df  : M1 bar DataFrame with columns [datetime, open, high, low, close]
        """
        if tick_df.empty or bar_df.empty:
            return []

        footprint_bars: List[FootprintBar] = []
        bar_times = bar_df["datetime"].values
        bar_durations = np.diff(bar_times)

        for i in range(len(bar_df)):
            row = bar_df.iloc[i]
            bar_start = row["datetime"]

            # Determine bar end
            if i < len(bar_df) - 1:
                bar_end = bar_df.iloc[i + 1]["datetime"]
            else:
                # Last bar: extend 1 minute (for M1)
                bar_end = bar_start + pd.Timedelta(minutes=1)

            # Filter ticks within this bar window
            mask = (tick_df["datetime"] >= bar_start) & (tick_df["datetime"] < bar_end)
            bar_ticks = tick_df[mask]

            if bar_ticks.empty:
                continue

            # Build levels: round each trade price → aggregate buy/sell vol
            fp_bar = self._build_single_bar(bar_ticks, row, bar_start)
            footprint_bars.append(fp_bar)

        return footprint_bars

    def _build_single_bar(
        self,
        ticks: pd.DataFrame,
        bar_row: pd.Series,
        bar_time: pd.Timestamp,
    ) -> FootprintBar:
        """Build FootprintBar from ticks belonging to one bar."""
        # Use 'last' price if available, else midprice
        price_col = "last"
        if (ticks[price_col] <= 0).all():
            ticks = ticks.copy()
            ticks[price_col] = (ticks["bid"] + ticks["ask"]) / 2

        # Round to tick size
        prices = (ticks[price_col] / self.tick_size).round() * self.tick_size

        levels: Dict[float, FootprintLevel] = {}
        for price_level in prices.unique():
            level_mask = prices == price_level
            level_ticks = ticks[level_mask]
            bid_v = float(level_ticks["sell_vol"].sum())  # sells hit the bid
            ask_v = float(level_ticks["buy_vol"].sum())   # buys lift the ask
            levels[price_level] = FootprintLevel(
                price=price_level,
                bid_vol=bid_v,
                ask_vol=ask_v,
            )

        total_buy = float(ticks["buy_vol"].sum())
        total_sell = float(ticks["sell_vol"].sum())

        return FootprintBar(
            bar_time=bar_time,
            bar_open=float(bar_row["open"]),
            bar_high=float(bar_row["high"]),
            bar_low=float(bar_row["low"]),
            bar_close=float(bar_row["close"]),
            levels=levels,
            total_buy_vol=total_buy,
            total_sell_vol=total_sell,
        )

    # ── Diagonal Imbalance Detection ───────────────
    def detect_imbalances(
        self,
        fp_bar: FootprintBar,
        ratio_threshold: float = None,
    ) -> List[DiagonalImbalance]:
        """
        Find diagonal imbalances in a single footprint bar.

        Bullish imbalance:  ask_vol[price] / bid_vol[price - tick_size] >= ratio
        Bearish imbalance:  bid_vol[price] / ask_vol[price + tick_size] >= ratio
        """
        threshold = ratio_threshold or config.IMBALANCE_RATIO
        imbalances: List[DiagonalImbalance] = []
        sorted_prices = sorted(fp_bar.levels.keys())

        for i in range(1, len(sorted_prices)):
            price = sorted_prices[i]
            price_below = sorted_prices[i - 1]
            above = fp_bar.levels[price]
            below = fp_bar.levels[price_below]

            # Bullish: ask_vol at current vs bid_vol at price below
            if below.bid_vol > 0:
                bull_ratio = above.ask_vol / below.bid_vol
                if bull_ratio >= threshold:
                    imbalances.append(DiagonalImbalance(
                        price=price, ratio=bull_ratio, direction="bullish",
                    ))

            # Bearish: bid_vol at current vs ask_vol at price above
            if above.ask_vol > 0:
                bear_ratio = below.bid_vol / above.ask_vol
                if bear_ratio >= threshold:
                    imbalances.append(DiagonalImbalance(
                        price=price_below, ratio=bear_ratio, direction="bearish",
                    ))

        return imbalances

    def find_imbalance_stacks(
        self,
        fp_bar: FootprintBar,
        min_consecutive: int = None,
    ) -> List[ImbalanceStack]:
        """
        Find consecutive diagonal imbalances stacking in one direction.
        3+ consecutive = strong signal.
        """
        min_c = min_consecutive or config.MIN_CONSECUTIVE_IMBALANCES
        imbalances = self.detect_imbalances(fp_bar)
        if len(imbalances) < min_c:
            return []

        stacks: List[ImbalanceStack] = []
        current_dir = imbalances[0].direction
        current_group: List[DiagonalImbalance] = [imbalances[0]]

        for imb in imbalances[1:]:
            if imb.direction == current_dir:
                current_group.append(imb)
            else:
                if len(current_group) >= min_c:
                    stacks.append(ImbalanceStack(
                        bar_time=fp_bar.bar_time,
                        imbalances=current_group,
                        direction=current_dir,
                        count=len(current_group),
                    ))
                current_dir = imb.direction
                current_group = [imb]

        # Final group
        if len(current_group) >= min_c:
            stacks.append(ImbalanceStack(
                bar_time=fp_bar.bar_time,
                imbalances=current_group,
                direction=current_dir,
                count=len(current_group),
            ))

        return stacks

    # ── Absorption Detection ───────────────────────
    def detect_absorption(
        self,
        fp_bar: FootprintBar,
        key_level: float,
        tolerance_ticks: int = None,
    ) -> Optional[dict]:
        """
        Detect absorption at a key level within a footprint bar.

        Bullish absorption: high sell_vol at key level but price held / bounced.
        Bearish absorption: high buy_vol at key level but price held / dropped.

        Returns dict with direction, volume, price if detected, else None.
        """
        tol = (tolerance_ticks or config.ABSORPTION_PRICE_HOLD_TICKS) * self.tick_size
        nearby_levels = {
            p: lv for p, lv in fp_bar.levels.items()
            if abs(p - key_level) <= tol
        }
        if not nearby_levels:
            return None

        total_bid = sum(lv.bid_vol for lv in nearby_levels.values())
        total_ask = sum(lv.ask_vol for lv in nearby_levels.values())
        avg_vol = np.mean([lv.total for lv in fp_bar.levels.values()]) if fp_bar.levels else 0

        threshold = avg_vol * config.ABSORPTION_VOL_MULTIPLIER

        # Bullish absorption: sellers hit bid hard but price didn't drop
        if total_bid > threshold and fp_bar.bar_close >= key_level - tol:
            return {
                "direction": "bullish",
                "absorbed_vol": total_bid,
                "level": key_level,
                "held": True,
                "bar_time": fp_bar.bar_time,
            }

        # Bearish absorption: buyers bought hard but price didn't rise
        if total_ask > threshold and fp_bar.bar_close <= key_level + tol:
            return {
                "direction": "bearish",
                "absorbed_vol": total_ask,
                "level": key_level,
                "held": True,
                "bar_time": fp_bar.bar_time,
            }

        return None

    # ── Exhaustion Detection ───────────────────────
    def detect_exhaustion(self, fp_bar: FootprintBar) -> Optional[dict]:
        """
        Detect exhaustion prints: very low delta at the extreme of a bar.
        At bar high (for bearish exhaustion): ask_vol ≈ bid_vol → auction finishing.
        At bar low (for bullish exhaustion): bid_vol ≈ ask_vol → sellers exhausted.
        """
        if not fp_bar.levels:
            return None

        sorted_prices = sorted(fp_bar.levels.keys())
        if len(sorted_prices) < 3:
            return None

        # Check top 2 levels for bearish exhaustion
        top_levels = [fp_bar.levels[p] for p in sorted_prices[-2:]]
        top_delta = sum(lv.delta for lv in top_levels)
        top_total = sum(lv.total for lv in top_levels)
        if top_total > 0 and abs(top_delta / top_total) < 0.15:
            return {"direction": "bearish_exhaustion", "zone": "high", "delta_ratio": abs(top_delta / top_total)}

        # Check bottom 2 levels for bullish exhaustion
        bot_levels = [fp_bar.levels[p] for p in sorted_prices[:2]]
        bot_delta = sum(lv.delta for lv in bot_levels)
        bot_total = sum(lv.total for lv in bot_levels)
        if bot_total > 0 and abs(bot_delta / bot_total) < 0.15:
            return {"direction": "bullish_exhaustion", "zone": "low", "delta_ratio": abs(bot_delta / bot_total)}

        return None
