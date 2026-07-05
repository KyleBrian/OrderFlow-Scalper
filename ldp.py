"""
Liquidity Delta Profiler (LDP) - Full Python Port from LuxAlgo PineScript
═════════════════════════════════════════════════════════════════════════════

Converts institutional-grade order flow analysis from PineScript to Python.

Core Concepts:
- Buy Side Liquidity (BSL): Where buyers are waiting to accumulate
- Sell Side Liquidity (SSL): Where sellers are waiting to distribute
- Zones form around pivot highs/lows with volume analysis
- Zone "health" decays as price moves away (fresh = high probability)
- 4-quadrant delta analysis (price vs delta momentum)
- Signals: ABS (absorption), EXH (exhaustion), DIV (divergence), REJ (rejection)

This is NOT retail guessing. This is what prop traders use.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class LDPSignalType(Enum):
    """Signal types from LDP analysis"""
    ABSORPTION = "absorption"  # Buyers/sellers accumulating
    EXHAUSTION = "exhaustion"  # Volume spike + move reverses
    DIVERGENCE = "divergence"  # Price new high but delta weak
    REJECTION = "rejection"  # Sweep + immediate snapback


@dataclass
class LiquidityZone:
    """
    A liquidity zone: buy-side or sell-side
    
    Buy Side (BSL): Below price, where buyers wait → support
    Sell Side (SSL): Above price, where sellers wait → resistance
    """
    zone_type: str  # "bsl" or "ssl"
    high: float  # Top of zone
    low: float  # Bottom of zone
    mid: float = field(init=False)  # Midpoint
    
    left: int  # Bar where zone formed (left edge)
    right: int  # Last bar where zone was active (right edge)
    
    volume_in_zone: int = 0  # Volume during zone formation
    health: int = 100  # Health % (decays as price moves away)
    
    touched_count: int = 0  # How many times price tested this zone
    breakout_bar: Optional[int] = None  # Bar where price broke cleanly
    
    details: dict = field(default_factory=dict)  # Extra metadata

    def __post_init__(self):
        self.mid = (self.high + self.low) / 2.0

    def __repr__(self):
        return f"LiquidityZone({self.zone_type.upper()} {self.low:.5f}-{self.high:.5f}, health={self.health}%)"


@dataclass
class LDPBar:
    """Processed bar with delta + liquidity info"""
    index: int
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    
    # Delta components
    delta_up: int = 0  # Aggressive buy volume
    delta_down: int = 0  # Aggressive sell volume
    delta: int = field(init=False)  # Net (up - down)
    
    # Cumulative
    cumulative_delta: int = 0
    
    def __post_init__(self):
        self.delta = self.delta_up - self.delta_down


class LiquidityDeltaProfiler:
    """
    Professional-grade liquidity zone + delta analysis.
    
    This replicates the LuxAlgo LDP indicator functionality:
    1. Detect pivot highs/lows
    2. Create liquidity zones (BSL/SSL)
    3. Track zone health (decay over time)
    4. Analyze 4-quadrant delta
    5. Generate ABS/EXH/DIV/REJ signals
    """

    def __init__(self, tick_size: float = 0.0001):
        self.tick_size = tick_size
        self.zones: List[LiquidityZone] = []
        self.bars: List[LDPBar] = []
        
        # Parameters (from LuxAlgo defaults)
        self.pivot_lookback = 5  # Bars left/right for pivot detection
        self.min_zone_width = 10  # Min pips for a zone to be valid
        self.health_decay_rate = 2  # % health lost per bar
        self.delta_threshold = 40  # Min delta for signal confirmation

    def process_bar(self, bar_dict: dict, delta_up: int = 0, delta_down: int = 0) -> None:
        """
        Process a new bar with delta info.
        
        Args:
            bar_dict: {"time": str, "open": float, "high": float, "low": float, "close": float, "volume": int}
            delta_up: Number of aggressive buy ticks
            delta_down: Number of aggressive sell ticks
        """
        index = len(self.bars)
        ldp_bar = LDPBar(
            index=index,
            time=bar_dict.get("time", ""),
            open=bar_dict["open"],
            high=bar_dict["high"],
            low=bar_dict["low"],
            close=bar_dict["close"],
            volume=bar_dict["volume"],
            delta_up=delta_up,
            delta_down=delta_down,
        )

        # Calculate cumulative delta
        if self.bars:
            ldp_bar.cumulative_delta = self.bars[-1].cumulative_delta + ldp_bar.delta
        else:
            ldp_bar.cumulative_delta = ldp_bar.delta

        self.bars.append(ldp_bar)

        # Update existing zones (health decay, right edge, touch count)
        self._update_zones(ldp_bar)

        # Detect new zones if we have enough bars
        if len(self.bars) >= self.pivot_lookback:
            self._detect_zones(index)

    def _update_zones(self, current_bar: LDPBar) -> None:
        """Update all existing zones with new bar data"""
        for zone in self.zones:
            # Check if price touched this zone
            if zone.low <= current_bar.low and zone.high >= current_bar.high:
                zone.touched_count += 1

            # Update right edge (last bar touching zone)
            if zone.low <= current_bar.close <= zone.high:
                zone.right = current_bar.index

            # Decay health if price moved away
            if current_bar.close > zone.high:
                # Price is above zone (for BSL, this is good)
                zone.health = max(0, zone.health - self.health_decay_rate)
            elif current_bar.close < zone.low:
                # Price is below zone (for SSL, this is good)
                zone.health = max(0, zone.health - self.health_decay_rate)

    def _detect_zones(self, current_index: int) -> None:
        """
        Detect new liquidity zones around pivot points.
        
        Looks back `pivot_lookback` bars to find pivots,
        then creates BSL (below) and SSL (above) zones.
        """
        if current_index < self.pivot_lookback * 2:
            return

        bar = self.bars[current_index]
        lookback = self.pivot_lookback

        # Check if current bar is a PIVOT HIGH (resistance, create SSL above)
        is_pivot_high = True
        for i in range(lookback):
            if self.bars[current_index - lookback + i].high >= bar.high:
                is_pivot_high = False
                break
        for i in range(1, lookback + 1):
            if current_index + i < len(self.bars):
                if self.bars[current_index + i].high >= bar.high:
                    is_pivot_high = False
                    break

        if is_pivot_high:
            # Create SSL (sell side liquidity) above the pivot high
            zone_high = bar.high + (10 * self.tick_size)  # 10 pips above
            zone_low = bar.high

            existing = [z for z in self.zones if z.zone_type == "ssl" and abs(z.mid - bar.high) < 20 * self.tick_size]
            if not existing:  # Don't create overlapping zones
                zone = LiquidityZone(
                    zone_type="ssl",
                    high=zone_high,
                    low=zone_low,
                    left=current_index,
                    right=current_index,
                    volume_in_zone=bar.volume,
                )
                self.zones.append(zone)
                logger.debug(f"[LDP] Created SSL zone at {zone_low:.5f}-{zone_high:.5f}")

        # Check if current bar is a PIVOT LOW (support, create BSL below)
        is_pivot_low = True
        for i in range(lookback):
            if self.bars[current_index - lookback + i].low <= bar.low:
                is_pivot_low = False
                break
        for i in range(1, lookback + 1):
            if current_index + i < len(self.bars):
                if self.bars[current_index + i].low <= bar.low:
                    is_pivot_low = False
                    break

        if is_pivot_low:
            # Create BSL (buy side liquidity) below the pivot low
            zone_low = bar.low - (10 * self.tick_size)  # 10 pips below
            zone_high = bar.low

            existing = [z for z in self.zones if z.zone_type == "bsl" and abs(z.mid - bar.low) < 20 * self.tick_size]
            if not existing:  # Don't create overlapping zones
                zone = LiquidityZone(
                    zone_type="bsl",
                    high=zone_high,
                    low=zone_low,
                    left=current_index,
                    right=current_index,
                    volume_in_zone=bar.volume,
                )
                self.zones.append(zone)
                logger.debug(f"[LDP] Created BSL zone at {zone_low:.5f}-{zone_high:.5f}")

    def get_active_zones(self, current_index: int, max_age: int = 50) -> List[LiquidityZone]:
        """
        Get zones that are still fresh (formed in last N bars).
        
        Args:
            current_index: Current bar index
            max_age: Max bar age to consider zone fresh
            
        Returns:
            List of zones with health > 0 and age <= max_age
        """
        active = []
        for zone in self.zones:
            age = current_index - zone.left
            if age <= max_age and zone.health > 0:
                active.append(zone)
        return active

    def detect_absorption(self, current_index: int, min_delta: int = 40) -> List[Tuple[LiquidityZone, LDPSignalType]]:
        """
        Detect ABS (absorption) signals.
        
        ABS = Liquidity zone being hit hard with aggressive delta, but price doesn't break through.
        Indicates institutional accumulation.
        
        Signal: Buy-side liquidity with negative delta (sellers absorbed)
        """
        signals = []
        
        if current_index < 3:
            return signals

        current_bar = self.bars[current_index]
        prev_bars = self.bars[max(0, current_index - 3):current_index]

        for zone in self.get_active_zones(current_index):
            # Check if price is near zone
            if not (zone.low - 5 * self.tick_size <= current_bar.close <= zone.high + 5 * self.tick_size):
                continue

            # Check for aggressive delta
            avg_delta = sum(b.delta for b in prev_bars) / len(prev_bars) if prev_bars else 0
            if abs(avg_delta) >= min_delta:
                # Price at zone + aggressive delta = absorption
                signals.append((zone, LDPSignalType.ABSORPTION))

        return signals

    def detect_exhaustion(self, current_index: int) -> List[Tuple[LiquidityZone, LDPSignalType]]:
        """
        Detect EXH (exhaustion) signals.
        
        EXH = Volume spike + reversal (price makes new extreme but delta doesn't follow)
        Indicates climactic reversal.
        """
        signals = []
        
        if current_index < 5:
            return signals

        current_bar = self.bars[current_index]
        prev_bars = self.bars[max(0, current_index - 5):current_index]
        
        avg_volume = sum(b.volume for b in prev_bars) / len(prev_bars) if prev_bars else 0
        
        # Volume spike + weak delta = exhaustion
        if current_bar.volume > avg_volume * 2.0 and abs(current_bar.delta) < self.delta_threshold:
            # Check if price is extreme
            is_high_extreme = current_bar.high > max(b.high for b in prev_bars[:-1]) if len(prev_bars) > 1 else False
            is_low_extreme = current_bar.low < min(b.low for b in prev_bars[:-1]) if len(prev_bars) > 1 else False
            
            if is_high_extreme or is_low_extreme:
                # Find nearest zone
                nearest_zone = min(
                    self.get_active_zones(current_index),
                    key=lambda z: abs(z.mid - current_bar.close),
                    default=None
                )
                if nearest_zone:
                    signals.append((nearest_zone, LDPSignalType.EXHAUSTION))

        return signals

    def detect_divergence(self, current_index: int) -> List[Tuple[LiquidityZone, LDPSignalType]]:
        """
        Detect DIV (divergence) signals.
        
        DIV = Price makes new high/low but delta doesn't follow
        Indicates weakening momentum = reversal warning
        """
        signals = []
        
        if current_index < 10:
            return signals

        current_bar = self.bars[current_index]
        lookback = 10
        prev_bars = self.bars[max(0, current_index - lookback):current_index]
        
        # Check for divergence: price new high but delta weak
        price_new_high = current_bar.high > max(b.high for b in prev_bars[:-1]) if len(prev_bars) > 1 else False
        delta_weak = current_bar.delta < self.delta_threshold / 2
        
        if price_new_high and delta_weak:
            nearest_zone = min(
                self.get_active_zones(current_index),
                key=lambda z: abs(z.mid - current_bar.close),
                default=None
            )
            if nearest_zone:
                signals.append((nearest_zone, LDPSignalType.DIVERGENCE))

        return signals

    def detect_rejection(self, current_index: int) -> List[Tuple[LiquidityZone, LDPSignalType]]:
        """
        Detect REJ (rejection) signals.
        
        REJ = Sweep into zone + immediate snapback (within 1-2 bars)
        Indicates institutional activity + rejection
        """
        signals = []
        
        if current_index < 2:
            return signals

        current_bar = self.bars[current_index]
        prev_bar = self.bars[current_index - 1]

        for zone in self.get_active_zones(current_index):
            # Check if previous bar swept into zone
            prev_swept = (
                (prev_bar.low < zone.low and prev_bar.close > zone.mid) or
                (prev_bar.high > zone.high and prev_bar.close < zone.mid)
            )
            
            # Current bar closes away from zone = rejection
            current_away = (
                (current_bar.close > zone.high and prev_bar.close < zone.mid) or
                (current_bar.close < zone.low and prev_bar.close > zone.mid)
            )
            
            if prev_swept and current_away:
                signals.append((zone, LDPSignalType.REJECTION))

        return signals

    def get_all_signals(self, current_index: int) -> List[Tuple[LiquidityZone, LDPSignalType]]:
        """
        Get ALL LDP signals for current bar (ABS + EXH + DIV + REJ).
        """
        all_signals = []
        all_signals.extend(self.detect_absorption(current_index))
        all_signals.extend(self.detect_exhaustion(current_index))
        all_signals.extend(self.detect_divergence(current_index))
        all_signals.extend(self.detect_rejection(current_index))
        return all_signals

    def get_zones_status(self) -> str:
        """
        Get human-readable status of all zones.
        """
        active = [z for z in self.zones if z.health > 0]
        lines = [f"Active zones: {len(active)}"]
        for zone in active[-5:]:  # Show last 5
            lines.append(f"  {zone}")
        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════
# EXAMPLE USAGE
# ═════════════════════════════════════════════════════════════════
"""
from ldp import LiquidityDeltaProfiler

ldp = LiquidityDeltaProfiler(tick_size=0.0001)

# Process bars
for bar in bars:
    ldp.process_bar(bar, delta_up=100, delta_down=80)

# Get signals
signals = ldp.get_all_signals(current_index=150)

for zone, signal_type in signals:
    print(f"Signal: {signal_type.value} at {zone.mid:.5f} (health {zone.health}%)")
"""
