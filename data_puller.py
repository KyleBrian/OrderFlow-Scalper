"""
Data Puller — Fresh tick data, OHLCV bars, and DOM snapshots from MT5.
All data is pulled on-demand, never cached stale.
"""
import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

from . import config

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Data Containers
# ─────────────────────────────────────────────
@dataclass
class TickData:
    """Processed tick DataFrame with buy/sell classification."""
    df: pd.DataFrame  # columns: time_msc, bid, ask, last, volume, volume_real, flags, is_buy, is_sell
    has_trade_flags: bool  # True if TICK_FLAG_BUY/SELL actually present
    symbol: str
    pulled_at: datetime


@dataclass
class BarData:
    """OHLCV bars as DataFrame."""
    df: pd.DataFrame  # columns: time, open, high, low, close, tick_volume, spread, real_volume
    timeframe: int
    symbol: str


@dataclass
class DOMLevel:
    """Single level in the order book."""
    side: str  # 'bid' or 'ask'
    price: float
    volume: float


@dataclass
class DOMSnapshot:
    """Full DOM snapshot: bid and ask sides."""
    bids: List[DOMLevel]
    asks: List[DOMLevel]
    timestamp: datetime

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None


class DataPuller:
    """Pulls fresh data from MT5 terminal."""

    def __init__(self, symbol: str = None):
        self.symbol = symbol or config.SYMBOL

    # ── Tick Data ──────────────────────────────────
    def pull_ticks_session(self, session_start: datetime = None) -> Optional[TickData]:
        """
        Pull all ticks from session start to now.
        session_start defaults to today 00:00 UTC.
        """
        if session_start is None:
            now_utc = datetime.now(timezone.utc)
            session_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

        ticks = mt5.copy_ticks_range(
            self.symbol,
            session_start,
            datetime.now(timezone.utc),
            mt5.COPY_TICKS_ALL,
        )
        if ticks is None or len(ticks) == 0:
            log.warning("No ticks returned for %s since %s", self.symbol, session_start)
            return None

        df = pd.DataFrame(ticks)
        return self._process_ticks(df)

    def pull_ticks_recent(self, count: int = 5000) -> Optional[TickData]:
        """Pull the N most recent ticks."""
        ticks = mt5.copy_ticks_from(
            self.symbol,
            datetime.now(timezone.utc) - timedelta(hours=1),
            count,
            mt5.COPY_TICKS_ALL,
        )
        if ticks is None or len(ticks) == 0:
            log.warning("No recent ticks for %s", self.symbol)
            return None

        df = pd.DataFrame(ticks)
        return self._process_ticks(df)

    def pull_trade_ticks(self, since: datetime = None, count: int = 10000) -> Optional[TickData]:
        """Pull only trade ticks (where last/volume changed) — best for footprint/delta."""
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(hours=4)

        ticks = mt5.copy_ticks_range(
            self.symbol,
            since,
            datetime.now(timezone.utc),
            mt5.COPY_TICKS_TRADE,
        )
        if ticks is None or len(ticks) == 0:
            log.debug("No trade ticks for %s since %s", self.symbol, since)
            return None

        df = pd.DataFrame(ticks)
        return self._process_ticks(df)

    def _process_ticks(self, df: pd.DataFrame) -> TickData:
        """Add buy/sell classification columns and datetime index."""
        # Convert timestamps
        df["datetime"] = pd.to_datetime(df["time_msc"], unit="ms", utc=True)

        # Classify direction using TICK_FLAG_BUY / TICK_FLAG_SELL
        df["is_buy"] = (df["flags"] & config.TICK_FLAG_BUY).astype(bool)
        df["is_sell"] = (df["flags"] & config.TICK_FLAG_SELL).astype(bool)

        # Check if trade flags are actually present
        has_flags = df["is_buy"].any() or df["is_sell"].any()

        if not has_flags and config.USE_HEURISTIC_DIRECTION:
            log.info("No TICK_FLAG_BUY/SELL detected — using heuristic direction")
            df = self._apply_heuristic_direction(df)
            has_flags = True  # heuristic always produces values

        # Buy/sell volume
        df["buy_vol"] = np.where(df["is_buy"], df["volume_real"], 0.0)
        df["sell_vol"] = np.where(df["is_sell"], df["volume_real"], 0.0)
        df["delta"] = df["buy_vol"] - df["sell_vol"]

        return TickData(
            df=df,
            has_trade_flags=has_flags,
            symbol=self.symbol,
            pulled_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _apply_heuristic_direction(df: pd.DataFrame) -> pd.DataFrame:
        """
        Forex fallback: infer buy/sell from tick-rule.
        If last >= ask → buyer aggressor (buy).
        If last <= bid → seller aggressor (sell).
        If last is 0, use mid-price change direction.
        """
        if (df["last"] > 0).any():
            df["is_buy"] = df["last"] >= df["ask"]
            df["is_sell"] = df["last"] <= df["bid"]
        else:
            # Pure forex with no last price — use bid/ask midpoint direction
            mid = (df["bid"] + df["ask"]) / 2
            mid_diff = mid.diff()
            df["is_buy"] = mid_diff > 0
            df["is_sell"] = mid_diff < 0
        return df

    # ── OHLCV Bars ─────────────────────────────────
    def pull_bars(
        self,
        timeframe: int = None,
        count: int = 500,
    ) -> Optional[BarData]:
        """Pull the most recent N bars for a timeframe."""
        tf = timeframe or config.TIMEFRAME_PRIMARY
        rates = mt5.copy_rates_from_pos(self.symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            log.warning("No bars for %s tf=%s", self.symbol, tf)
            return None

        df = pd.DataFrame(rates)
        df["datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)
        return BarData(df=df, timeframe=tf, symbol=self.symbol)

    def pull_daily_bars(self, count: int = 10) -> Optional[BarData]:
        """Pull recent daily bars for key level computation."""
        return self.pull_bars(timeframe=mt5.TIMEFRAME_D1, count=count)

    def pull_bars_range(
        self,
        timeframe: int,
        date_from: datetime,
        date_to: datetime,
    ) -> Optional[BarData]:
        """Pull bars within a date range."""
        rates = mt5.copy_rates_range(self.symbol, timeframe, date_from, date_to)
        if rates is None or len(rates) == 0:
            return None
        df = pd.DataFrame(rates)
        df["datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)
        return BarData(df=df, timeframe=timeframe, symbol=self.symbol)

    # ── DOM / Market Depth ─────────────────────────
    def pull_dom(self) -> Optional[DOMSnapshot]:
        """Get current DOM snapshot (requires prior market_book_add)."""
        book = mt5.market_book_get(self.symbol)
        if book is None or len(book) == 0:
            return None

        bids: List[DOMLevel] = []
        asks: List[DOMLevel] = []
        for entry in book:
            level = DOMLevel(
                side="bid" if entry.type in (mt5.BOOK_TYPE_BUY, mt5.BOOK_TYPE_BUY_MARKET) else "ask",
                price=entry.price,
                volume=entry.volume_real if entry.volume_real > 0 else float(entry.volume),
            )
            if level.side == "bid":
                bids.append(level)
            else:
                asks.append(level)

        # Sort: bids descending, asks ascending
        bids.sort(key=lambda x: x.price, reverse=True)
        asks.sort(key=lambda x: x.price)

        return DOMSnapshot(
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc),
        )

    # ── Current Price ──────────────────────────────
    def get_current_tick(self):
        """Fast: get the single latest tick (no DataFrame overhead)."""
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return None
        return tick  # mt5 Tick object — has .bid, .ask, .last, .volume, etc.
