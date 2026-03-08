"""
Journal — Trade logging to CSV + running statistics.
Tracks every trade with full context for post-session review.
"""
import csv
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional

log = logging.getLogger(__name__)

JOURNAL_DIR = os.path.join(os.path.dirname(__file__), "..", "journal_output")
JOURNAL_CSV = os.path.join(JOURNAL_DIR, "trades.csv")

CSV_FIELDS = [
    "trade_id",
    "opened_at",
    "closed_at",
    "symbol",
    "direction",
    "signal_type",
    "key_level",
    "confidence",
    "entry_price",
    "stop_loss",
    "tp1",
    "tp2",
    "tp3",
    "volume",
    "exit_price",
    "pnl",
    "r_multiple",
    "is_win",
    "exit_reason",
    "notes",
]


@dataclass
class TradeRecord:
    trade_id: int
    opened_at: str
    closed_at: str
    symbol: str
    direction: str
    signal_type: str
    key_level: float
    confidence: float
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    volume: float
    exit_price: float
    pnl: float
    r_multiple: float
    is_win: bool
    exit_reason: str
    notes: str = ""


class Journal:
    """
    Append-only CSV journal with running stats.
    """

    def __init__(self, csv_path: str = None):
        self._csv_path = csv_path or JOURNAL_CSV
        self._ensure_file()
        self._records: List[TradeRecord] = []
        self._trade_counter = self._count_existing()

    def _ensure_file(self):
        os.makedirs(os.path.dirname(self._csv_path), exist_ok=True)
        if not os.path.exists(self._csv_path):
            with open(self._csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                writer.writeheader()
            log.info("Created trade journal: %s", self._csv_path)

    def _count_existing(self) -> int:
        try:
            with open(self._csv_path, "r") as f:
                return max(0, sum(1 for _ in f) - 1)
        except Exception:
            return 0

    def log_trade(
        self,
        symbol: str,
        direction: str,
        signal_type: str,
        key_level: float,
        confidence: float,
        entry_price: float,
        stop_loss: float,
        take_profits: List[float],
        volume: float,
        exit_price: float,
        pnl: float,
        risk_amount: float,
        exit_reason: str,
        opened_at: datetime = None,
        notes: str = "",
    ):
        self._trade_counter += 1
        r_mult = pnl / risk_amount if risk_amount != 0 else 0.0
        tps = take_profits + [0.0] * (3 - len(take_profits))

        record = TradeRecord(
            trade_id=self._trade_counter,
            opened_at=str(opened_at or ""),
            closed_at=str(datetime.now(timezone.utc)),
            symbol=symbol,
            direction=direction,
            signal_type=signal_type,
            key_level=round(key_level, 5),
            confidence=round(confidence, 2),
            entry_price=round(entry_price, 5),
            stop_loss=round(stop_loss, 5),
            tp1=round(tps[0], 5),
            tp2=round(tps[1], 5),
            tp3=round(tps[2], 5),
            volume=volume,
            exit_price=round(exit_price, 5),
            pnl=round(pnl, 2),
            r_multiple=round(r_mult, 2),
            is_win=pnl > 0,
            exit_reason=exit_reason,
            notes=notes,
        )
        self._records.append(record)
        self._write_row(record)
        log.info("Journal #%d: %s %s %.2f lots → P&L=%.2f R=%.2f (%s)",
                 record.trade_id, direction, symbol, volume, pnl, r_mult, exit_reason)

    def _write_row(self, rec: TradeRecord):
        try:
            with open(self._csv_path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                writer.writerow(asdict(rec))
        except Exception as e:
            log.error("Failed to write journal row: %s", e)

    # ── Running Stats ──────────────────────────────
    def session_stats(self) -> dict:
        """Return stats for the current session (records loaded in memory)."""
        if not self._records:
            return {"trades": 0}

        trades = self._records
        wins = [t for t in trades if t.is_win]
        losses = [t for t in trades if not t.is_win]
        total_pnl = sum(t.pnl for t in trades)
        gross_profit = sum(t.pnl for t in wins) if wins else 0.0
        gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0.0

        return {
            "trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(trades), 2) if trades else 0,
            "total_pnl": round(total_pnl, 2),
            "avg_win": round(gross_profit / len(wins), 2) if wins else 0,
            "avg_loss": round(gross_loss / len(losses), 2) if losses else 0,
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf"),
            "avg_r": round(sum(t.r_multiple for t in trades) / len(trades), 2),
            "max_r": max(t.r_multiple for t in trades),
            "min_r": min(t.r_multiple for t in trades),
            "max_drawdown_trade": round(min(t.pnl for t in trades), 2),
            "expectancy": round(total_pnl / len(trades), 2),
        }

    def print_summary(self):
        stats = self.session_stats()
        if stats["trades"] == 0:
            log.info("No trades this session.")
            return
        log.info("═" * 50)
        log.info("SESSION SUMMARY")
        log.info("═" * 50)
        log.info("Trades: %d  (W:%d / L:%d)", stats["trades"], stats["wins"], stats["losses"])
        log.info("Win Rate: %.0f%%", stats["win_rate"] * 100)
        log.info("Total P&L: %.2f", stats["total_pnl"])
        log.info("Avg Win: %.2f  |  Avg Loss: %.2f", stats["avg_win"], stats["avg_loss"])
        log.info("Profit Factor: %.2f", stats["profit_factor"])
        log.info("Avg R: %.2f  |  Best: %.2f  |  Worst: %.2f",
                 stats["avg_r"], stats["max_r"], stats["min_r"])
        log.info("Expectancy: %.2f per trade", stats["expectancy"])
        log.info("═" * 50)
