"""
Scanner — Main analysis loop that orchestrates the full Strategy 1 pipeline:
  1. Pull fresh data (ticks, bars, DOM)
  2. Rebuild key levels & volume profile
  3. Check price proximity to key levels
  4. Build footprint → detect signals
  5. Validate confluences (5 confirmations)
  6. Pass valid signals to executor
"""
import logging
import time as _time
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import pandas as pd

import config
from mt5_connector import MT5Connector
from data_puller import DataPuller
from volume_profile import build_volume_profile, VolumeProfile
from key_levels import KeyLevelBuilder, KeyLevels
from footprint import FootprintBuilder, FootprintBar
from delta import DeltaEngine
from signals import SignalDetector, Signal
from risk_manager import RiskManager
from executor import Executor, ManagedPosition
from journal import Journal

log = logging.getLogger(__name__)


class Scanner:
    """
    Runs the repeating analysis cycle.  Called from main loop.
    
    Strategy 1 confirmation checklist (need 3-5 of 5):
      1. Price at key level (PDH/PDL, VPOC, VAH/VAL, Opening Range)
      2. Order-flow signal (absorption / imbalance stack / delta divergence / iceberg / exhaustion)
      3. Volume Profile context (rejection at VAH/VAL, bounce off VPOC)
      4. Cumulative Delta confirmation (delta supports direction)
      5. Tape confirmation (DOM shows passive support at level)
    """

    def __init__(
        self,
        connector: MT5Connector,
        puller: DataPuller,
        risk_mgr: RiskManager,
        executor: Executor,
        journal: Journal,
    ):
        self.conn = connector
        self.puller = puller
        self.risk = risk_mgr
        self.exec = executor
        self.journal = journal

        self.fp_builder = FootprintBuilder(
            tick_size=connector.spec.point if connector.spec else 0.00001
        )
        self.delta_engine = DeltaEngine()

        tick_size = connector.spec.point if connector.spec else 0.01
        self.signal_detector = SignalDetector(
            footprint_builder=self.fp_builder,
            delta_engine=self.delta_engine,
            tick_size=tick_size,
        )

        # Cached structures (rebuilt periodically)
        self._key_levels: Optional[KeyLevels] = None
        self._volume_profile: Optional[VolumeProfile] = None
        self._last_profile_time: float = 0
        self._last_keylevel_time: float = 0
        self._footprint_bars: List[FootprintBar] = []

    # ── One Full Scan Cycle ────────────────────────
    def run_cycle(self):
        """Execute one analysis cycle.  Returns True if a trade was opened."""
        now = datetime.now(timezone.utc)

        # 0. Manage existing positions first
        if self.exec.has_open_positions():
            self._manage_open_positions()

        # 1. Pre-trade risk check
        can, reason = self.risk.can_trade(now)
        if not can:
            log.info("Blocked: %s", reason)
            return False

        # Already in a position — don't stack
        if self.exec.has_open_positions():
            return False

        # 2. Pull fresh data
        tick_data = self.puller.pull_ticks_session()
        if tick_data is None or tick_data.df.empty:
            log.debug("No ticks available")
            return False
        ticks = tick_data.df  # work with the raw DataFrame from here

        # 3. Rebuild volume profile (throttled) — before key levels so VPOC is available
        elapsed = _time.time() - self._last_profile_time
        if self._volume_profile is None or elapsed > config.PROFILE_REBUILD_SECS:
            self._rebuild_volume_profile(ticks)

        # 4. Rebuild key levels (throttled — every 60s)
        tick_size = self.conn.spec.point if self.conn.spec else 0.01
        kl_elapsed = _time.time() - self._last_keylevel_time
        if self._key_levels is None or kl_elapsed > 60:
            kl_builder = KeyLevelBuilder(self.puller, tick_size)
            self._key_levels = kl_builder.build(self._volume_profile)
            self._last_keylevel_time = _time.time()

        # 5. Build footprint from recent ticks
        recent_bars = self.puller.pull_bars(config.TIMEFRAME_PRIMARY, count=20)
        if recent_bars is not None and not recent_bars.df.empty:
            self._footprint_bars = self.fp_builder.build_footprint(ticks, recent_bars.df)

        # 6. Build delta
        if self._footprint_bars:
            self.delta_engine.compute_from_footprint(self._footprint_bars)

        # 7. Detect signals
        if self._key_levels is None or not self._footprint_bars:
            log.info("No key_levels or footprint_bars — skipping signal detection (fp_bars=%d)",
                      len(self._footprint_bars) if self._footprint_bars else 0)
            return False

        current_tick = self.puller.get_current_tick()
        current_price = current_tick.bid if current_tick else ticks["bid"].iloc[-1] if "bid" in ticks.columns else ticks["close"].iloc[-1]
        log.info("Cycle: price=%.2f  fp_bars=%d  key_levels=%d",
                 current_price, len(self._footprint_bars),
                 len(self._key_levels.all_levels()) if self._key_levels else 0)
        signals = self.signal_detector.scan_all(
            fp_bars=self._footprint_bars,
            key_levels=self._key_levels,
            current_price=current_price,
            tick_df=ticks,
        )

        if not signals:
            log.debug("No signals — price=%.2f  nearest_levels=%s",
                     current_price,
                     [f"{l:.2f}" for l in sorted(self._key_levels.all_levels(),
                      key=lambda x: abs(x - current_price))[:3]] if self._key_levels else [])
            return False

        # 8. Take the best signal and validate confluences
        best = signals[0]
        confluences = self._count_confluences(best, ticks)
        log.info("Best signal: %s dir=%s conf=%.2f at_level=%.5f  confluences=%d/5",
                 best.signal_type.value, best.direction, best.confidence,
                 best.key_level, confluences)

        if confluences < 3:
            log.info("Insufficient confluences (%d < 3), skipping", confluences)
            return False

        # 9. Execute trade
        return self._execute_signal(best)

    # ── Confluence Counter ─────────────────────────
    def _count_confluences(self, signal: Signal, ticks: pd.DataFrame) -> int:
        """
        Count how many of the 5 confirmations are met:
          1. Price at key level
          2. Order-flow signal (always True if we got a signal)
          3. Volume profile context
          4. Delta confirmation
          5. DOM / tape confirmation
        """
        score = 0

        # 1. Key level — signal already anchored to nearest level
        if signal.key_level > 0:
            score += 1

        # 2. Order-flow signal — always 1 if signal exists
        score += 1

        # 3. Volume profile context
        if self._volume_profile and self._key_levels:
            vp = self._volume_profile
            price = signal.key_level
            # At VAH/VAL → potential reversal zone
            tolerance = self.conn.spec.point * 20
            at_vah = abs(price - vp.vah) <= tolerance
            at_val = abs(price - vp.val) <= tolerance
            at_vpoc = abs(price - vp.vpoc) <= tolerance
            if at_vah or at_val or at_vpoc:
                score += 1

        # 4. Delta confirmation
        if self.delta_engine.is_delta_supporting(signal.direction):
            score += 1

        # 5. DOM / tape — check if heavy passive volume exists at level
        dom = self.puller.pull_dom()
        if dom:
            total_bid = sum(l.volume for l in dom.bids[:5])
            total_ask = sum(l.volume for l in dom.asks[:5])
            if signal.direction == "long" and total_bid > total_ask * 1.5:
                score += 1
            elif signal.direction == "short" and total_ask > total_bid * 1.5:
                score += 1

        return score

    # ── Trade Execution ────────────────────────────
    def _execute_signal(self, signal: Signal) -> bool:
        """Size, validate R:R, and send the order."""
        self.conn.refresh_account()
        acct = self.conn.get_account_state()
        spec = self.conn.spec

        # Get current price
        tick = self.puller.get_current_tick()
        if tick is None:
            return False

        entry = tick.ask if signal.direction == "long" else tick.bid

        # Compute SL / TPs
        sl = self.exec.compute_sl(entry, signal.direction)
        tps = self.exec.compute_tp_levels(entry, signal.direction)

        # R:R check
        rr_ok, rr = self.risk.check_rr_ratio(entry, sl, tps[0])
        if not rr_ok:
            log.info("R:R %.2f below minimum, skipping", rr)
            return False

        # Position size
        stop_dist_ticks = config.STOP_TICKS
        volume = self.risk.calculate_position_size(
            acct.balance, stop_dist_ticks, spec.tick_value,
            spec.volume_min, spec.volume_step, spec.volume_max,
        )
        if volume <= 0:
            return False

        risk_amount = acct.balance * config.RISK_PER_TRADE

        # Open
        pos = self.exec.open_trade(
            direction=signal.direction,
            volume=volume,
            stop_loss=sl,
            take_profits=tps,
            risk_amount=risk_amount,
        )
        if pos is None:
            return False

        log.info("TRADE OPENED: %s %.2f lots @ %.5f  SL=%.5f  TPs=%s  R:R=%.2f  signal=%s",
                 signal.direction, volume, entry, sl, tps, rr, signal.signal_type.value)
        return True

    # ── Manage Open Positions ──────────────────────
    def _manage_open_positions(self):
        """Check TPs, trailing, delta reversal for open positions."""
        tick = self.puller.get_current_tick()
        if tick is None:
            return

        current_price = tick.bid  # use bid for management

        # Check if delta is reversing against us
        delta_reversing = False
        for pos in self.exec.get_positions():
            if self.delta_engine.is_delta_reversing(pos.direction):
                delta_reversing = True
                break

        self.exec.manage_positions(current_price, delta_reversing)

        # Check for fully closed positions to journal
        self._journal_closed_positions(current_price)

    def _journal_closed_positions(self, current_price: float):
        """If a position has been fully closed, log it to journal."""
        for pos in self.exec.get_positions():
            if pos.tp_stage >= 3 and pos.remaining_volume <= 0:
                pnl = self._estimate_pnl(pos, current_price)
                self.journal.log_trade(
                    symbol=config.SYMBOL,
                    direction=pos.direction,
                    signal_type="",
                    key_level=0.0,
                    confidence=0.0,
                    entry_price=pos.entry_price,
                    stop_loss=pos.stop_loss,
                    take_profits=pos.take_profits,
                    volume=pos.total_volume,
                    exit_price=current_price,
                    pnl=pnl,
                    risk_amount=pos.risk_amount,
                    exit_reason=f"TP{pos.tp_stage}",
                    opened_at=pos.opened_at,
                )
                self.risk.record_trade(pnl, pos.risk_amount)

    @staticmethod
    def _estimate_pnl(pos: ManagedPosition, exit_price: float) -> float:
        """Rough P&L estimate for dry-run logging."""
        if pos.direction == "long":
            return (exit_price - pos.entry_price) * pos.total_volume
        else:
            return (pos.entry_price - exit_price) * pos.total_volume

    # ── Volume Profile Rebuild ─────────────────────
    def _rebuild_volume_profile(self, ticks: pd.DataFrame):
        tick_size = self.conn.spec.point if self.conn.spec else 0.00001
        self._volume_profile = build_volume_profile(ticks, tick_size)
        self._last_profile_time = _time.time()
        if self._volume_profile:
            vp = self._volume_profile
            log.info("Volume Profile rebuilt: VPOC=%.5f  VAH=%.5f  VAL=%.5f  HVN=%d  LVN=%d",
                     vp.vpoc, vp.vah, vp.val,
                     len(vp.hvn_levels), len(vp.lvn_levels))
