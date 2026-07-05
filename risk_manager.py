"""
Risk Manager — Position sizing (1% rule), daily P&L tracking,
consecutive loss counter, killzone filtering, R:R validation.
Maps to the Risk section of Strategy 1.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, time
from typing import List, Optional, Tuple

import config

log = logging.getLogger(__name__)


@dataclass
class TradeResult:
    """Outcome of a closed trade for risk tracking."""
    pnl: float
    r_multiple: float
    is_win: bool
    closed_at: datetime


class RiskManager:
    """
    Enforces all risk rules from Strategy 1:
    - Max 1% risk per trade
    - Max 3 consecutive losses → stop
    - Max 3% daily loss → stop
    - Minimum R:R ≥ 1:1.5
    - Killzone / dead zone filtering
    """

    def __init__(self):
        self._trades_today: List[TradeResult] = []
        self._starting_balance: float = 0.0

    def reset_day(self, starting_balance: float):
        """Call at start of each trading day."""
        self._trades_today.clear()
        self._starting_balance = starting_balance
        log.info("Risk manager reset — starting balance: %.2f", starting_balance)

    # ── Position Sizing ────────────────────────────
    def calculate_position_size(
        self,
        account_balance: float,
        stop_distance_ticks: int,
        tick_value: float,
        volume_min: float,
        volume_step: float,
        volume_max: float,
    ) -> float:
        """
        Position size based on 1% risk rule.
        
        Formula:
          risk_amount = balance × RISK_PER_TRADE
          lots = risk_amount / (stop_distance × tick_value)
          
        Round down to nearest volume_step, clamp to [volume_min, volume_max].
        """
        risk_amount = account_balance * config.RISK_PER_TRADE
        if stop_distance_ticks <= 0 or tick_value <= 0:
            log.error("Invalid stop/tick_value: stop=%d, tick_val=%.4f",
                      stop_distance_ticks, tick_value)
            return 0.0

        raw_lots = risk_amount / (stop_distance_ticks * tick_value)

        # Round down to volume_step
        if volume_step > 0:
            lots = int(raw_lots / volume_step) * volume_step
        else:
            lots = raw_lots

        # Clamp
        lots = max(lots, volume_min)
        lots = min(lots, volume_max)

        log.info(
            "Position size: risk=%.2f, stop=%d ticks, tick_val=%.2f → %.2f lots",
            risk_amount, stop_distance_ticks, tick_value, lots,
        )
        return lots

    # ── Pre-Trade Checks ───────────────────────────
    def can_trade(self, current_time: datetime = None) -> Tuple[bool, str]:
        """
        Master check: can we take a new trade right now?
        Returns (allowed, reason).
        """
        # Check consecutive losses
        consec = self._consecutive_losses()
        if consec >= config.MAX_CONSECUTIVE_LOSSES:
            return False, f"Hit {consec} consecutive losses (max {config.MAX_CONSECUTIVE_LOSSES})"

        # Check daily loss limit
        daily_pnl = self.daily_pnl()
        max_loss = self._starting_balance * config.MAX_DAILY_LOSS
        if daily_pnl < 0 and abs(daily_pnl) >= max_loss:
            return False, f"Daily loss {daily_pnl:.2f} exceeds limit {-max_loss:.2f}"

        # Check killzone (skip for crypto — trades 24/7)
        t = current_time or datetime.now(timezone.utc)
        if not config.IS_CRYPTO:
            if not self.is_in_killzone(t):
                return False, "Outside killzone hours"

            if self.is_in_dead_zone(t):
                return False, "Inside dead zone (12:00-14:00 EST)"

        return True, "OK"

    def check_rr_ratio(
        self,
        entry: float,
        stop: float,
        tp1: float,
    ) -> Tuple[bool, float]:
        """
        Validate minimum Risk:Reward ratio.
        Returns (passes, actual_rr).
        """
        risk = abs(entry - stop)
        reward = abs(tp1 - entry)
        if risk == 0:
            return False, 0.0
        rr = reward / risk
        passes = rr >= config.MIN_RR_RATIO
        if not passes:
            log.info("R:R %.2f below minimum %.2f", rr, config.MIN_RR_RATIO)
        return passes, round(rr, 2)

    # ── Record Trade Result ────────────────────────
    def record_trade(self, pnl: float, risk_amount: float):
        """Log a completed trade for daily tracking."""
        r_mult = pnl / risk_amount if risk_amount != 0 else 0.0
        result = TradeResult(
            pnl=pnl,
            r_multiple=round(r_mult, 2),
            is_win=pnl > 0,
            closed_at=datetime.now(timezone.utc),
        )
        self._trades_today.append(result)
        log.info(
            "Trade recorded: P&L=%.2f R=%.2f (today: %d trades, cum P&L=%.2f)",
            pnl, r_mult, len(self._trades_today), self.daily_pnl(),
        )

    # ── Daily Stats ────────────────────────────────
    def daily_pnl(self) -> float:
        return sum(t.pnl for t in self._trades_today)

    def daily_trades(self) -> int:
        return len(self._trades_today)

    def daily_win_rate(self) -> float:
        if not self._trades_today:
            return 0.0
        wins = sum(1 for t in self._trades_today if t.is_win)
        return wins / len(self._trades_today)

    def _consecutive_losses(self) -> int:
        """Count consecutive losses from the end of today's trades."""
        count = 0
        for t in reversed(self._trades_today):
            if not t.is_win:
                count += 1
            else:
                break
        return count

    # ── Killzone / Dead Zone ───────────────────────
    @staticmethod
    def is_in_killzone(dt: datetime) -> bool:
        """
        Check if current time falls within any defined killzone.
        Times in config are EST; we convert dt (expected UTC) to EST.
        """
        est_offset = -5  # EST = UTC-5 (simplification; DST not handled)
        est_hour = (dt.hour + est_offset) % 24
        est_minute = dt.minute

        est_minutes_total = est_hour * 60 + est_minute

        for h_start, m_start, h_end, m_end in config.KILLZONES:
            kz_start = h_start * 60 + m_start
            kz_end = h_end * 60 + m_end
            if kz_start <= est_minutes_total < kz_end:
                return True
        return False

    @staticmethod
    def is_in_dead_zone(dt: datetime) -> bool:
        """Check if current time is in the dead zone (avoid trading)."""
        est_offset = -5
        est_hour = (dt.hour + est_offset) % 24
        est_minute = dt.minute
        est_minutes_total = est_hour * 60 + est_minute

        dz = config.DEAD_ZONE
        dz_start = dz[0] * 60 + dz[1]
        dz_end = dz[2] * 60 + dz[3]
        return dz_start <= est_minutes_total < dz_end
