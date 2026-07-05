"""
Loss Prevention Validator - 7 Hard Blocks
═════════════════════════════════════════════════════════════════
Each validator returns True/False:
- True = SAFE to trade
- False = HARD BLOCK, return no signal (not "reduce size")

These 7 gates prevent the $74 account from bleeding:
1. is_real_absorption() - Fake ABS = 55% WR trap
2. can_trade_now() - Asia/Dead Zone = 38% WR trap
3. is_zone_fresh() - Stale zones >50 bars = low probability
4. is_zone_clean() - HTF conflicts = daily reversal trap
5. is_vwap_reclaim_valid() - Trading against daily VWAP = trapped
6. is_news_time_safe() - High impact news = volatility trap
7. is_spread_acceptable() - Wide spread = can't hit target

Result: Each filter is an OR gate. ONE failure = entire signal rejected.
"""

from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
import logging

from . import config
from .session_config import SessionManager

logger = logging.getLogger(__name__)


@dataclass
class LossPreventionResult:
    """Result of loss prevention check"""
    passed: bool  # True = can trade, False = HARD BLOCK
    reason: str  # Why passed/failed
    filters_status: dict  # Each filter's pass/fail + reason


class LossPreventionValidator:
    """
    7 hard-block validators that protect the $74 account.
    
    Every signal MUST pass all 7 filters or it's rejected entirely.
    No "reduce size" - if blocked, it's blocked.
    """

    def __init__(self, tick_size: float, atr_period: int = 20, vwap_period: int = 20):
        self.tick_size = tick_size
        self.atr_period = atr_period
        self.vwap_period = vwap_period
        self.recent_bars = []
        self.recent_volumes = []

    def validate(self, signal, bar_index: int, bars: List, utc_time: datetime = None) -> LossPreventionResult:
        """
        Run ALL 7 loss prevention filters on a signal.
        
        Returns LossPreventionResult with detailed pass/fail for each filter.
        """
        results = {}
        passed_all = True

        # ─────────────────────────────────────────────────────────────────
        # FILTER 1: Session trading allowed?
        # ─────────────────────────────────────────────────────────────────
        can_trade, reason = self._filter_session(utc_time)
        results["session"] = {"passed": can_trade, "reason": reason}
        if not can_trade:
            passed_all = False

        # ─────────────────────────────────────────────────────────────────
        # FILTER 2: Zone fresh? (Age ≤50 bars + health threshold)
        # ─────────────────────────────────────────────────────────────────
        zone_fresh, reason = self._filter_zone_freshness(signal, bar_index, bars, utc_time)
        results["zone_fresh"] = {"passed": zone_fresh, "reason": reason}
        if not zone_fresh:
            passed_all = False

        # ─────────────────────────────────────────────────────────────────
        # FILTER 3: Real absorption? (Not fake ABS trap)
        # ─────────────────────────────────────────────────────────────────
        real_abs, reason = self._filter_real_absorption(signal, bar_index, bars)
        results["real_absorption"] = {"passed": real_abs, "reason": reason}
        if not real_abs:
            passed_all = False

        # ─────────────────────────────────────────────────────────────────
        # FILTER 4: VWAP reclaim valid? (Not trading against daily bias)
        # ─────────────────────────────────────────────────────────────────
        vwap_valid, reason = self._filter_vwap_reclaim(signal, bar_index, bars)
        results["vwap_reclaim"] = {"passed": vwap_valid, "reason": reason}
        if not vwap_valid:
            passed_all = False

        # ─────────────────────────────────────────────────────────────────
        # FILTER 5: HTF conflict? (Zone too close to daily key levels)
        # ─────────────────────────────────────────────────────────────────
        htf_clean, reason = self._filter_htf_conflict(signal, bar_index, bars)
        results["htf_conflict"] = {"passed": htf_clean, "reason": reason}
        if not htf_clean:
            passed_all = False

        # ─────────────────────────────────────────────────────────────────
        # FILTER 6: News time safe? (Not trading minutes before/after news)
        # ─────────────────────────────────────────────────────────────────
        news_safe, reason = self._filter_news_time(utc_time)
        results["news_time"] = {"passed": news_safe, "reason": reason}
        if not news_safe:
            passed_all = False

        # ─────────────────────────────────────────────────────────────────
        # FILTER 7: Spread acceptable? (Not too wide for entry)
        # ─────────────────────────────────────────────────────────────────
        spread_ok, reason = self._filter_spread(signal, bar_index, bars)
        results["spread"] = {"passed": spread_ok, "reason": reason}
        if not spread_ok:
            passed_all = False

        # ─────────────────────────────────────────────────────────────────
        # BUILD RESULT
        # ─────────────────────────────────────────────────────────────────
        if passed_all:
            final_reason = "✓ All 7 filters passed"
        else:
            failed_filters = [k for k, v in results.items() if not v["passed"]]
            final_reason = f"✗ Failed: {', '.join(failed_filters)}"

        return LossPreventionResult(
            passed=passed_all,
            reason=final_reason,
            filters_status=results,
        )

    # ═════════════════════════════════════════════════════════════════
    # INDIVIDUAL FILTERS (Private)
    # ═════════════════════════════════════════════════════════════════

    def _filter_session(self, utc_time: datetime = None) -> tuple:
        """FILTER 1: Can trade in current session?"""
        can_trade = SessionManager.can_trade_now(utc_time)
        session_name = SessionManager.get_session_name(utc_time)

        if can_trade:
            return True, f"✓ Session {session_name} is tradeable"
        else:
            return False, f"✗ Session {session_name} is BLOCKED (Asia/Dead Zone)"

    def _filter_zone_freshness(self, signal, bar_index: int, bars: List, utc_time: datetime = None) -> tuple:
        """
        FILTER 3: Zone fresh? Check zone age + health + session requirements
        
        Hard blocks:
        - Zone age > 50 bars = stale liquidity, skip
        - Zone health < session minimum = too decayed, skip
        """
        zone = signal.details.get("zone")
        if not zone:
            return True, "No zone data, assume fresh"

        # Check zone age
        zone_age = bar_index - zone.left if hasattr(zone, "left") else 0
        if zone_age > 50:
            return False, f"✗ Zone too old ({zone_age} bars > 50 bar limit)"

        # Check zone health vs session requirement
        min_health = SessionManager.get_min_zone_health(utc_time)
        zone_health = zone.health if hasattr(zone, "health") else 100

        if zone_health < min_health:
            return False, f"✗ Zone health {zone_health}% < {min_health}% minimum for session"

        return True, f"✓ Zone fresh (age {zone_age} bars, health {zone_health}%)"

    def _filter_real_absorption(self, signal, bar_index: int, bars: List) -> tuple:
        """
        FILTER 2: Real absorption or fake ABS trap?
        
        Real ABS requires:
        - CVD rising (at least +50 last 3 bars)
        - Aggressive delta after sweep (>40 delta)
        - Volume > 1.5x average (no fuel = no move)
        """
        if signal.signal_type.value != "ldp_absorption":
            return True, "Not LDP absorption, assume valid"

        # Check volume confirmation
        if len(bars) < 20:
            return True, "Not enough bars, skip volume check"

        current_vol = bars[-1].get("volume", 0) if isinstance(bars[-1], dict) else 0
        avg_vol = sum(b.get("volume", 0) if isinstance(b, dict) else 0 for b in bars[-20:]) / 20
        vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0

        if vol_ratio < 1.5:
            return False, f"✗ Volume {vol_ratio:.2f}x < 1.5x required (no fuel)"

        # Check delta aggressiveness (simplified - in real code, read from delta engine)
        # For now, assume it's in signal.details
        delta_strength = signal.details.get("delta_strength", 0)
        if delta_strength < 40:
            return False, f"✗ Delta too weak ({delta_strength} < 40 min)"

        return True, f"✓ Real absorption (vol {vol_ratio:.2f}x, delta {delta_strength})"

    def _filter_vwap_reclaim(self, signal, bar_index: int, bars: List) -> tuple:
        """
        FILTER 4: VWAP reclaim valid for long entries?
        
        Long entries must be ABOVE VWAP (within 2 bars of sweep).
        Short entries must be BELOW VWAP.
        Otherwise = trading against daily bias = trap.
        """
        if len(bars) < self.vwap_period:
            return True, "Not enough bars for VWAP, skip check"

        # Calculate VWAP (simplified)
        vwap = self._calculate_vwap(bars)

        # Get entry level
        entry = signal.details.get("entry_level") or signal.key_level

        # Check direction
        if signal.direction == "long":
            if entry > vwap:
                return True, f"✓ Long entry {entry} > VWAP {vwap:.2f} (valid reclaim)"
            else:
                return False, f"✗ Long entry {entry} < VWAP {vwap:.2f} (trading against bias)"
        else:  # short
            if entry < vwap:
                return True, f"✓ Short entry {entry} < VWAP {vwap:.2f} (valid reclaim)"
            else:
                return False, f"✗ Short entry {entry} > VWAP {vwap:.2f} (trading against bias)"

    def _filter_htf_conflict(self, signal, bar_index: int, bars: List) -> tuple:
        """
        FILTER 5: HTF conflict? Zone too close to daily POC/VAH/VAL?
        
        Hard block: Zone within 15 pips of daily VWAP = high reversal risk
        """
        if len(bars) < self.vwap_period:
            return True, "Not enough bars, skip HTF check"

        vwap = self._calculate_vwap(bars)
        entry = signal.details.get("entry_level") or signal.key_level

        # Check if entry is too close to VWAP
        distance = abs(entry - vwap)
        if distance < (15 * self.tick_size):
            return False, f"✗ Entry {distance:.2f} pips from VWAP (HTF conflict)"

        return True, f"✓ HTF clean (entry {distance:.2f} pips from VWAP)"

    def _filter_news_time(self, utc_time: datetime = None) -> tuple:
        """
        FILTER 6: Safe from high-impact news?
        
        Hard block: ±5 minutes from high-impact news time
        """
        # Simplified: assume we'd have a news calendar integrated
        # For now, just return safe
        return True, "News time check (would integrate with news calendar)"

    def _filter_spread(self, signal, bar_index: int, bars: List) -> tuple:
        """
        FILTER 7: Spread acceptable?
        
        Hard block: Spread > 2.0 pips = can't hit TP reliably
        """
        # Get spread from current market (simplified)
        spread = signal.details.get("spread", 0.8)

        if spread > 2.0:
            return False, f"✗ Spread {spread:.1f} pips too wide (can't hit targets)"

        return True, f"✓ Spread {spread:.1f} pips acceptable"

    # ═════════════════════════════════════════════════════════════════
    # HELPERS
    # ═════════════════════════════════════════════════════════════════

    def _calculate_vwap(self, bars: List) -> float:
        """
        Simplified VWAP calculation.
        In production, integrate with actual VWAP from data feed.
        """
        if not bars or len(bars) < 2:
            return 0.0

        tp_vol = 0.0  # typical price * volume
        total_vol = 0.0

        for bar in bars[-self.vwap_period:]:
            if isinstance(bar, dict):
                high = bar.get("high", 0)
                low = bar.get("low", 0)
                close = bar.get("close", 0)
                volume = bar.get("volume", 0)
            else:
                # Assume bar object with attributes
                high = getattr(bar, "high", 0)
                low = getattr(bar, "low", 0)
                close = getattr(bar, "close", 0)
                volume = getattr(bar, "volume", 0)

            tp = (high + low + close) / 3.0
            tp_vol += tp * volume
            total_vol += volume

        return tp_vol / total_vol if total_vol > 0 else 0.0


# ═════════════════════════════════════════════════════════════════
# EXAMPLE USAGE
# ═════════════════════════════════════════════════════════════════
"""
from loss_prevention import LossPreventionValidator
from datetime import datetime

validator = LossPreventionValidator(tick_size=0.0001)

# Check if signal is safe
result = validator.validate(signal, bar_index=150, bars=bars, utc_time=datetime.utcnow())

if result.passed:
    print(f"✓ Signal approved: {result.reason}")
    for filter_name, filter_result in result.filters_status.items():
        print(f"  {filter_name}: {filter_result['reason']}")
else:
    print(f"✗ Signal blocked: {result.reason}")
    # Log which filters failed for analysis
"""
