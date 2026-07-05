"""
Configuration for Order Flow Scalper - Strategy 1
All tunable parameters in one place.
"""
from dataclasses import dataclass, field
from typing import List, Tuple
import MetaTrader5 as mt5


# ─────────────────────────────────────────────
# MT5 CONNECTION
# ─────────────────────────────────────────────
MT5_PATH: str = ""  # Leave empty for default install path
MT5_LOGIN: int = 0  # Your MT5 account number
MT5_PASSWORD: str = ""
MT5_SERVER: str = ""
MT5_TIMEOUT: int = 10_000  # ms

# ─────────────────────────────────────────────
# SYMBOL & INSTRUMENT
# ─────────────────────────────────────────────
SYMBOL: str = "BTCUSDm"  # Change to your broker's symbol name
IS_CRYPTO: bool = True   # True = skip killzone/dead-zone checks (crypto trades 24/7)
TIMEFRAME_PRIMARY = mt5.TIMEFRAME_M1  # 1-minute bars
TIMEFRAME_CONTEXT = mt5.TIMEFRAME_M5  # 5-minute context bars
TIMEFRAME_DAILY = mt5.TIMEFRAME_D1

# ─────────────────────────────────────────────
# TICK FLAGS (bitmask values from MT5)
# ─────────────────────────────────────────────
TICK_FLAG_BID = 2
TICK_FLAG_ASK = 4
TICK_FLAG_LAST = 8
TICK_FLAG_VOLUME = 16
TICK_FLAG_BUY = 32
TICK_FLAG_SELL = 64

# ─────────────────────────────────────────────
# RISK MANAGEMENT
# ─────────────────────────────────────────────
RISK_PER_TRADE: float = 0.01  # 1% of account per trade
MAX_DAILY_LOSS: float = 0.03  # 3% daily loss limit → stop
MAX_CONSECUTIVE_LOSSES: int = 3  # 3 losses in a row → stop
MIN_RR_RATIO: float = 1.5  # Minimum Risk:Reward = 1:1.5

# ─────────────────────────────────────────────
# SCALE-OUT PLAN  (50% / 30% / 20%)
# ─────────────────────────────────────────────
TP_SPLIT: List[float] = [0.50, 0.30, 0.20]

# TP distances in ticks from entry
TP1_TICKS: int = 6   # First liquidity pocket / next HVN
TP2_TICKS: int = 10  # Next resistance / LVN
TP3_TICKS: int = 16  # Extended target / VPOC
STOP_TICKS: int = 4  # 2-4 ticks beyond absorption zone

# ─────────────────────────────────────────────
# ORDER FLOW THRESHOLDS
# ─────────────────────────────────────────────
# Footprint imbalance ratio: ask_vol / bid_vol (diagonal)
IMBALANCE_RATIO: float = 3.0  # 300% = strong imbalance
MIN_CONSECUTIVE_IMBALANCES: int = 3  # 3+ diagonal imbalances

# Absorption detection
ABSORPTION_VOL_MULTIPLIER: float = 2.0  # bid_vol at level > 2× avg
ABSORPTION_PRICE_HOLD_TICKS: int = 2  # price must not drop more than N ticks

# Iceberg detection
ICEBERG_MIN_REPEATS: int = 10  # 10+ small fills at same price
ICEBERG_VOL_TOLERANCE: float = 0.2  # ±20% volume consistency
ICEBERG_TOTAL_VS_DISPLAY: float = 5.0  # total > 5× individual size

# Volume spike for confirmation
VOLUME_SPIKE_MULTIPLIER: float = 1.5  # current > 1.5× avg 20-bar volume

# Delta divergence: swing detection
DELTA_DIVERGENCE_LOOKBACK: int = 20  # bars to look back for swings
DELTA_DIVERGENCE_MIN_SWING: int = 3  # min bars between pivot points

# ─────────────────────────────────────────────
# VOLUME PROFILE
# ─────────────────────────────────────────────
VALUE_AREA_PCT: float = 0.70  # 70% of volume = value area
HVN_THRESHOLD: float = 1.5  # volume > 1.5× mean = HVN
LVN_THRESHOLD: float = 0.5  # volume < 0.5× mean = LVN
COMPOSITE_DAYS: int = 5  # 5-day composite profile

# ─────────────────────────────────────────────
# KEY LEVEL PROXIMITY
# ─────────────────────────────────────────────
PROXIMITY_TICKS: int = 5  # price within 5 ticks of a key level

# ─────────────────────────────────────────────
# KILLZONES (EST / New York time)
# ─────────────────────────────────────────────
# Tuples of (hour_start, minute_start, hour_end, minute_end)
KILLZONES: List[Tuple[int, int, int, int]] = [
    (2, 0, 5, 0),     # London Open:  02:00 - 05:00 EST
    (8, 30, 11, 0),   # NY Open:      08:30 - 11:00 EST
]
# Dead zone — avoid trading
DEAD_ZONE: Tuple[int, int, int, int] = (12, 0, 14, 0)  # 12:00 - 14:00 EST

# ─────────────────────────────────────────────
# SCANNING / POLLING
# ─────────────────────────────────────────────
TICK_POLL_INTERVAL_MS: int = 100  # tick polling every 100ms
DOM_POLL_INTERVAL_MS: int = 200  # DOM polling every 200ms
ANALYSIS_INTERVAL_MS: int = 500  # run analysis every 500ms
PROFILE_REBUILD_SECS: int = 60  # rebuild volume profile every 60s

# ─────────────────────────────────────────────
# EXECUTION
# ─────────────────────────────────────────────
MAGIC_NUMBER: int = 240001  # EA identifier for our orders
DEVIATION: int = 5  # max slippage in points
DRY_RUN: bool = True  # True = no real orders, just log signals

# ─────────────────────────────────────────────
# JOURNAL
# ─────────────────────────────────────────────
JOURNAL_CSV: str = "trade_journal.csv"
JOURNAL_DB: str = "trade_journal.db"

# ─────────────────────────────────────────────
# CANDLE IMBALANCE (CRT) - NEW FEATURE
# ─────────────────────────────────────────────
CANDLE_IMBALANCE_VOLUME_RATIO_THRESHOLD: float = 0.60  # one side > 60% = imbalance
CANDLE_IMBALANCE_MIN_CONFIRMATION: int = 2  # require 2+ candles with imbalance

# ─────────────────────────────────────────────
# ICT ORDER BLOCKS - NEW FEATURE
# ─────────────────────────────────────────────
CONSOLIDATION_MIN_VOLUME: int = 100  # min volume to qualify as consolidation
ORDER_BLOCK_LOOKBACK: int = 20  # scan last 20 bars for blocks
ORDER_BLOCK_PROXIMITY_TICKS: int = 10  # within 10 ticks = triggered

# ─────────────────────────────────────────────
# FOREX HEURISTIC FALLBACK
# ─────────────────────────────────────────────
USE_HEURISTIC_DIRECTION: bool = False  # auto-enabled if TICK_FLAG_BUY/SELL absent
