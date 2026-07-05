"""
Volume Profile Engine — Build volume-at-price histogram from tick data.
Identifies VPOC, Value Area (VAH/VAL), HVN, LVN.
"""
import numpy as np
import pandas as pd
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import config

log = logging.getLogger(__name__)


@dataclass
class VolumeProfile:
    """Result of a volume profile computation."""
    profile_df: pd.DataFrame  # columns: price, total_vol, buy_vol, sell_vol, pct
    vpoc: float              # Volume Point of Control (price with max volume)
    vah: float               # Value Area High
    val: float               # Value Area Low
    hvn_levels: List[float]  # High Volume Nodes
    lvn_levels: List[float]  # Low Volume Nodes
    total_volume: float


def build_volume_profile(
    tick_df: pd.DataFrame,
    tick_size: float,
    value_area_pct: float = None,
    hvn_threshold: float = None,
    lvn_threshold: float = None,
) -> Optional[VolumeProfile]:
    """
    Build a volume profile from trade tick data.

    Parameters
    ----------
    tick_df : DataFrame with columns [last, volume_real, buy_vol, sell_vol]
              (output of DataPuller._process_ticks)
    tick_size : minimum price increment for rounding
    value_area_pct : fraction of total volume for value area (default from config)
    hvn_threshold : volume > threshold × mean = HVN
    lvn_threshold : volume < threshold × mean = LVN
    """
    va_pct = value_area_pct or config.VALUE_AREA_PCT
    hvn_t = hvn_threshold or config.HVN_THRESHOLD
    lvn_t = lvn_threshold or config.LVN_THRESHOLD

    # Filter to trade ticks (where last > 0 and volume > 0)
    trades = tick_df[(tick_df["last"] > 0) & (tick_df["volume_real"] > 0)].copy()
    if trades.empty:
        # Forex fallback: use bid as price proxy, tick_volume = 1 per tick
        trades = tick_df.copy()
        trades["last"] = (trades["bid"] + trades["ask"]) / 2
        trades["volume_real"] = 1.0
        trades["buy_vol"] = np.where(trades["is_buy"], 1.0, 0.0)
        trades["sell_vol"] = np.where(trades["is_sell"], 1.0, 0.0)
        if trades.empty:
            log.warning("No data to build volume profile")
            return None

    # Round prices to tick_size
    trades["price_level"] = (trades["last"] / tick_size).round() * tick_size

    # Aggregate volume at each price level
    profile = trades.groupby("price_level").agg(
        total_vol=("volume_real", "sum"),
        buy_vol=("buy_vol", "sum"),
        sell_vol=("sell_vol", "sum"),
        tick_count=("volume_real", "count"),
    ).reset_index()
    profile.rename(columns={"price_level": "price"}, inplace=True)
    profile.sort_values("price", inplace=True, ignore_index=True)

    total_volume = profile["total_vol"].sum()
    if total_volume == 0:
        return None

    profile["pct"] = profile["total_vol"] / total_volume

    # ── VPOC: price with maximum volume ──
    vpoc_idx = profile["total_vol"].idxmax()
    vpoc = profile.loc[vpoc_idx, "price"]

    # ── Value Area (70% of volume centered on VPOC) ──
    vah, val = _compute_value_area(profile, vpoc_idx, va_pct)

    # ── HVN / LVN ──
    mean_vol = profile["total_vol"].mean()
    hvn_levels = profile.loc[profile["total_vol"] > hvn_t * mean_vol, "price"].tolist()
    lvn_levels = profile.loc[profile["total_vol"] < lvn_t * mean_vol, "price"].tolist()

    return VolumeProfile(
        profile_df=profile,
        vpoc=vpoc,
        vah=vah,
        val=val,
        hvn_levels=hvn_levels,
        lvn_levels=lvn_levels,
        total_volume=total_volume,
    )


def _compute_value_area(
    profile: pd.DataFrame, vpoc_idx: int, pct: float
) -> tuple:
    """
    Expand outward from VPOC to find Value Area containing pct of total volume.
    Returns (VAH, VAL).
    """
    total = profile["total_vol"].sum()
    target = total * pct

    accumulated = profile.loc[vpoc_idx, "total_vol"]
    upper_idx = vpoc_idx
    lower_idx = vpoc_idx
    max_idx = len(profile) - 1

    while accumulated < target:
        # Look one step above and below, pick whichever adds more volume
        above_vol = profile.loc[upper_idx + 1, "total_vol"] if upper_idx < max_idx else 0
        below_vol = profile.loc[lower_idx - 1, "total_vol"] if lower_idx > 0 else 0

        if above_vol == 0 and below_vol == 0:
            break

        if above_vol >= below_vol:
            upper_idx += 1
            accumulated += above_vol
        else:
            lower_idx -= 1
            accumulated += below_vol

    vah = profile.loc[upper_idx, "price"]
    val = profile.loc[lower_idx, "price"]
    return vah, val


def build_composite_profile(
    daily_profiles: List[VolumeProfile],
) -> Optional[VolumeProfile]:
    """
    Merge multiple daily profiles into a composite.
    Used for multi-day support/resistance and Naked POC detection.
    """
    if not daily_profiles:
        return None

    # Concatenate all profile DataFrames
    frames = [p.profile_df[["price", "total_vol", "buy_vol", "sell_vol"]] for p in daily_profiles]
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.groupby("price").sum().reset_index()
    combined.sort_values("price", inplace=True, ignore_index=True)

    total_volume = combined["total_vol"].sum()
    if total_volume == 0:
        return None

    combined["pct"] = combined["total_vol"] / total_volume
    combined["tick_count"] = 0  # not meaningful for composite

    vpoc_idx = combined["total_vol"].idxmax()
    vpoc = combined.loc[vpoc_idx, "price"]
    vah, val = _compute_value_area(combined, vpoc_idx, config.VALUE_AREA_PCT)

    mean_vol = combined["total_vol"].mean()
    hvn = combined.loc[combined["total_vol"] > config.HVN_THRESHOLD * mean_vol, "price"].tolist()
    lvn = combined.loc[combined["total_vol"] < config.LVN_THRESHOLD * mean_vol, "price"].tolist()

    return VolumeProfile(
        profile_df=combined,
        vpoc=vpoc,
        vah=vah,
        val=val,
        hvn_levels=hvn,
        lvn_levels=lvn,
        total_volume=total_volume,
    )
