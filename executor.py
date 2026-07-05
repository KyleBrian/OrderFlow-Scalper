"""
Executor — Order management: send, partial close (50/30/20),
SL-to-breakeven, delta trailing, emergency exit.
"""
import logging
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import MetaTrader5 as mt5

import config

log = logging.getLogger(__name__)


@dataclass
class ManagedPosition:
    """State for a live position being managed."""
    ticket: int
    direction: str           # "long" or "short"
    entry_price: float
    stop_loss: float
    take_profits: List[float]  # [TP1, TP2, TP3]
    total_volume: float
    remaining_volume: float
    risk_amount: float
    tp_stage: int = 0        # 0=none closed, 1=TP1 hit, 2=TP2 hit, 3=all closed
    breakeven_moved: bool = False
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class Executor:
    """
    Handles all execution logic:
    - Market entry (with DRY_RUN support)
    - Partial close at TP1/TP2/TP3 (50%/30%/20% scale-out)
    - SL to breakeven after TP1
    - Delta-based trailing after TP2
    - Emergency full close
    """

    def __init__(self, symbol_spec):
        self.spec = symbol_spec  # SymbolSpec from mt5_connector
        self._positions: dict[int, ManagedPosition] = {}

    # ── Entry ──────────────────────────────────────
    def open_trade(
        self,
        direction: str,
        volume: float,
        stop_loss: float,
        take_profits: List[float],
        risk_amount: float,
    ) -> Optional[ManagedPosition]:
        """
        Send a market order.  If DRY_RUN is True, simulate only.
        Returns ManagedPosition on success, None on failure.
        """
        symbol = config.SYMBOL

        if direction == "long":
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(symbol).ask
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(symbol).bid

        if config.DRY_RUN:
            fake_ticket = int(_time.time() * 1000) % 10_000_000
            pos = ManagedPosition(
                ticket=fake_ticket,
                direction=direction,
                entry_price=price,
                stop_loss=stop_loss,
                take_profits=take_profits,
                total_volume=volume,
                remaining_volume=volume,
                risk_amount=risk_amount,
            )
            self._positions[fake_ticket] = pos
            log.info("[DRY_RUN] Opened %s %.2f lots @ %.5f  SL=%.5f  TPs=%s",
                     direction, volume, price, stop_loss, take_profits)
            return pos

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": stop_loss,
            "tp": take_profits[0] if take_profits else 0.0,
            "deviation": config.DEVIATION,
            "magic": config.MAGIC_NUMBER,
            "comment": "OFScalper entry",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            code = result.retcode if result else "None"
            log.error("Order failed: retcode=%s  comment=%s",
                      code, getattr(result, "comment", ""))
            return None

        pos = ManagedPosition(
            ticket=result.order,
            direction=direction,
            entry_price=result.price,
            stop_loss=stop_loss,
            take_profits=take_profits,
            total_volume=volume,
            remaining_volume=volume,
            risk_amount=risk_amount,
        )
        self._positions[result.order] = pos
        log.info("Opened %s %.2f lots @ %.5f  ticket=%d",
                 direction, volume, result.price, result.order)
        return pos

    # ── Manage (called every analysis cycle) ──────
    def manage_positions(self, current_price: float, delta_reversing: bool = False):
        """
        Check all managed positions for TP hits / trailing / emergency.
        """
        closed_tickets = []
        for ticket, pos in self._positions.items():
            if pos.tp_stage >= 3:
                closed_tickets.append(ticket)
                continue
            self._check_tp_stages(pos, current_price)
            if delta_reversing and pos.tp_stage >= 2:
                self._emergency_close(pos, reason="delta reversal")
                closed_tickets.append(ticket)
        for t in closed_tickets:
            self._positions.pop(t, None)

    def _check_tp_stages(self, pos: ManagedPosition, price: float):
        """Scale-out logic: TP1 → 50%, TP2 → 30%, TP3 → 20%."""
        tps = pos.take_profits
        if not tps:
            return

        hit_long = pos.direction == "long"

        # TP1
        if pos.tp_stage == 0 and len(tps) > 0:
            if (hit_long and price >= tps[0]) or (not hit_long and price <= tps[0]):
                close_vol = round(pos.total_volume * config.TP_SPLIT[0], 2)
                close_vol = max(close_vol, self.spec.volume_min)
                self._partial_close(pos, close_vol, "TP1")
                pos.tp_stage = 1
                self._move_sl_to_breakeven(pos)

        # TP2
        if pos.tp_stage == 1 and len(tps) > 1:
            if (hit_long and price >= tps[1]) or (not hit_long and price <= tps[1]):
                close_vol = round(pos.total_volume * config.TP_SPLIT[1], 2)
                close_vol = max(close_vol, self.spec.volume_min)
                self._partial_close(pos, close_vol, "TP2")
                pos.tp_stage = 2

        # TP3
        if pos.tp_stage == 2 and len(tps) > 2:
            if (hit_long and price >= tps[2]) or (not hit_long and price <= tps[2]):
                self._close_remaining(pos, "TP3")
                pos.tp_stage = 3

    def _partial_close(self, pos: ManagedPosition, volume: float, label: str):
        volume = min(volume, pos.remaining_volume)
        if volume <= 0:
            return

        if config.DRY_RUN:
            pos.remaining_volume = round(pos.remaining_volume - volume, 2)
            log.info("[DRY_RUN] Partial close %s: %.2f lots  remaining=%.2f",
                     label, volume, pos.remaining_volume)
            return

        symbol = config.SYMBOL
        if pos.direction == "long":
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(symbol).bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(symbol).ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "position": pos.ticket,
            "deviation": config.DEVIATION,
            "magic": config.MAGIC_NUMBER,
            "comment": f"OFScalper {label}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            pos.remaining_volume = round(pos.remaining_volume - volume, 2)
            log.info("Partial close %s: %.2f lots @ %.5f  remaining=%.2f",
                     label, volume, result.price, pos.remaining_volume)
        else:
            code = result.retcode if result else "None"
            log.error("Partial close %s failed: %s", label, code)

    def _move_sl_to_breakeven(self, pos: ManagedPosition):
        """After TP1, move SL to entry price."""
        if pos.breakeven_moved:
            return
        pos.breakeven_moved = True
        new_sl = pos.entry_price

        if config.DRY_RUN:
            pos.stop_loss = new_sl
            log.info("[DRY_RUN] SL moved to breakeven %.5f", new_sl)
            return

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": config.SYMBOL,
            "position": pos.ticket,
            "sl": new_sl,
            "tp": pos.take_profits[1] if len(pos.take_profits) > 1 else 0.0,
            "magic": config.MAGIC_NUMBER,
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            pos.stop_loss = new_sl
            log.info("SL moved to breakeven %.5f for ticket %d", new_sl, pos.ticket)
        else:
            log.error("Failed to move SL to breakeven for ticket %d", pos.ticket)

    def trail_stop(self, pos: ManagedPosition, new_sl: float):
        """Trail SL further (e.g., after TP2 using delta-based logic)."""
        if pos.direction == "long" and new_sl <= pos.stop_loss:
            return
        if pos.direction == "short" and new_sl >= pos.stop_loss:
            return

        if config.DRY_RUN:
            pos.stop_loss = new_sl
            log.info("[DRY_RUN] Trailing SL to %.5f", new_sl)
            return

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": config.SYMBOL,
            "position": pos.ticket,
            "sl": new_sl,
            "tp": 0.0,
            "magic": config.MAGIC_NUMBER,
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            pos.stop_loss = new_sl
            log.info("Trailing SL to %.5f for ticket %d", new_sl, pos.ticket)

    def _close_remaining(self, pos: ManagedPosition, label: str):
        if pos.remaining_volume <= 0:
            return
        self._partial_close(pos, pos.remaining_volume, label)

    def _emergency_close(self, pos: ManagedPosition, reason: str = "emergency"):
        log.warning("Emergency close ticket %d — reason: %s", pos.ticket, reason)
        self._close_remaining(pos, f"EMERGENCY({reason})")
        pos.tp_stage = 3

    def emergency_close_all(self, reason: str = "shutdown"):
        """Close everything immediately (e.g., on shutdown or daily loss hit)."""
        for pos in list(self._positions.values()):
            self._emergency_close(pos, reason)
        self._positions.clear()

    # ── Helpers ────────────────────────────────────
    def has_open_positions(self) -> bool:
        return len(self._positions) > 0

    def get_positions(self) -> List[ManagedPosition]:
        return list(self._positions.values())

    def compute_tp_levels(self, entry: float, direction: str) -> List[float]:
        """
        Compute TP1/TP2/TP3 from entry price using config tick distances.
        """
        tick = self.spec.point
        if direction == "long":
            return [
                round(entry + config.TP1_TICKS * tick, self.spec.digits),
                round(entry + config.TP2_TICKS * tick, self.spec.digits),
                round(entry + config.TP3_TICKS * tick, self.spec.digits),
            ]
        else:
            return [
                round(entry - config.TP1_TICKS * tick, self.spec.digits),
                round(entry - config.TP2_TICKS * tick, self.spec.digits),
                round(entry - config.TP3_TICKS * tick, self.spec.digits),
            ]

    def compute_sl(self, entry: float, direction: str) -> float:
        """Compute SL from entry using config STOP_TICKS."""
        tick = self.spec.point
        if direction == "long":
            return round(entry - config.STOP_TICKS * tick, self.spec.digits)
        else:
            return round(entry + config.STOP_TICKS * tick, self.spec.digits)
