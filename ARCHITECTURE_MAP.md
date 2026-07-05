# Order Flow Scalper - Complete Architecture Map & Import Guide

**Last Updated:** July 2026  
**Version:** Strategy 1 with Advanced Features (v3+)  
**Status:** Full feature-complete system

---

## 1. PROJECT STRUCTURE

```
order_flow_scalper/
├── __init__.py                          # Package init (minimal)
├── __main__.py                          # Entry point: python -m order_flow_scalper
├── main.py                              # OrderFlowScalper controller (3-thread orchestrator)
├── config.py                            # ALL configuration in one file
│
├── CORE ENGINE (Real-time trading)
├── mt5_connector.py                     # MT5 connection lifecycle, symbol specs, account
├── data_puller.py                       # Tick polling, bar fetching, DOM snapshots
├── scanner.py                           # Main analysis cycle orchestrator (500ms)
├── executor.py                          # Order placement, partial closes, trailing stops
├── risk_manager.py                      # Position sizing, daily limits, killzones
│
├── ANALYSIS MODULES (Detect signals)
├── delta.py                             # Buy/sell volume, cumulative delta, divergences
├── footprint.py                         # Bid×Ask volume matrix, imbalances, absorption
├── volume_profile.py                    # POC, VAH, VAL, HVN, LVN, composite profile
├── key_levels.py                        # PDH/PDL, Opening Range, VPOC, Session levels
├── signals.py                           # Signal detector (orchestrates all 5 confirmations)
├── journal.py                           # CSV + SQLite trade logging
│
├── ADVANCED FEATURES
├── candle_imbalance.py                  # CRT (Candle Range Technique) imbalance detection
├── ict_order_blocks.py                  # ICT Order Block detection & triggered zones
├── ldp.py                               # Liquidity Delta Profiler (advanced delta analysis)
├── session_config.py                    # Session hours, killzone management
├── loss_prevention.py                   # Anomaly detection, drawdown prevention
├── trade_reasoner.py                    # Trade justification & reasoning engine
│
├── UTILITIES
├── chart.py                             # Footprint visualization (charting)
│
└── README.md                            # Feature overview
   CHANGELOG.md                          # Version history
   IMPLEMENTATION_SUMMARY.md             # Feature details
   NEW_FEATURES_GUIDE.md                 # Advanced module guide
   QUICK_START.md                        # Setup & first run
```

---

## 2. EXECUTION FLOW & THREADING

```
START
  │
  ├─► MAIN THREAD (Blocking orchestrator)
  │   │
  │   ├─► OrderFlowScalper.start()
  │   │   ├─ Connect MT5
  │   │   ├─ Subscribe to DOM
  │   │   ├─ Build components
  │   │   ├─ Reset risk manager
  │   │   └─ Launch analysis & manager threads
  │   │
  │   └─ Wait for Ctrl+C → _cleanup()
  │       ├─ Emergency close all positions
  │       ├─ Print session summary
  │       └─ Disconnect MT5
  │
  ├─► THREAD 2: _analysis_loop() [ANALYZER]
  │   │   Interval: ANALYSIS_INTERVAL_MS (default 500ms)
  │   │
  │   └─► scanner.run_cycle()  ← Main analysis engine
  │       ├─ Pre-trade checks (risk, killzone, position state)
  │       ├─ Pull fresh data (ticks, bars, DOM)
  │       ├─ Rebuild key levels (every 60s)
  │       ├─ Rebuild volume profile (every 60s)
  │       ├─ Build footprint & analyze order flow
  │       ├─ Detect signals (delta, imbalances, etc)
  │       ├─ Validate confluences (need 3-5 of 5 confirmations)
  │       └─ Executor.open_trade() if all checks pass
  │
  ├─► THREAD 3: _management_loop() [MANAGER]
  │   │   Interval: TICK_POLL_INTERVAL_MS (default 100ms)
  │   │
  │   └─► executor.manage_positions(bid_price, delta_reversing)
  │       ├─ Check each open position
  │       ├─ Execute TP1 (50% at 6 ticks)
  │       ├─ Execute TP2 (30% at 10 ticks)
  │       ├─ Execute TP3 (20% at 16 ticks)
  │       ├─ Trail SL to breakeven after TP1
  │       └─ Delta-based trailing after TP2
  │
  └─► ON SHUTDOWN
      ├─ Emergency close all positions
      ├─ Journal.print_summary()
      └─ MT5 disconnect

```

---

## 3. DATA FLOW DIAGRAM

```
MT5 Terminal (Live Market)
    │
    ├─► TICK DATA (Bid/Ask/Last, Flags, Volume) @100ms polling
    │   └─► DataPuller.pull_ticks_session()
    │       └─► returns TickData(df, has_trade_flags)
    │
    ├─► DOM SNAPSHOTS (Order Book) @200ms polling
    │   └─► DataPuller.pull_dom()
    │       └─► returns DOMSnapshot(bids[], asks[])
    │
    └─► OHLCV BARS (M1, M5, D1)
        └─► DataPuller.pull_bars(timeframe, count)
            └─► returns BarData(df, timeframe)

            ↓ ↓ ↓

SCANNER.RUN_CYCLE() - Main Pipeline (500ms)
│
├─ RISK CHECKS
│  └─► RiskManager.can_trade()
│      ├─ Check consecutive losses
│      ├─ Check daily P&L limit
│      ├─ Check killzone/dead zone
│      └─ Return (can_trade: bool, reason: str)
│
├─ DATA ANALYSIS
│  ├─► DeltaEngine.compute_bars(tick_data)
│  │   ├─ Classify each tick as buy/sell
│  │   ├─ Sum buy_vol & sell_vol per bar
│  │   ├─ Compute cumulative delta
│  │   └─ Detect divergences
│  │
│  ├─► FootprintBuilder.build_bars(tick_data)
│  │   ├─ Build bid×ask matrix per price level
│  │   ├─ Detect diagonal imbalances (ask > 3× bid)
│  │   ├─ Detect absorption (high volume with price hold)
│  │   └─ Detect exhaustion (low volume on extension)
│  │
│  ├─► VolumeProfile.rebuild() [every 60s]
│  │   ├─ Compute POC (point of control)
│  │   ├─ Compute VAH/VAL (70% volume)
│  │   ├─ Identify HVN & LVN
│  │   └─ Build 5-day composite
│  │
│  └─► KeyLevelBuilder.rebuild() [every 60s]
│      ├─ Find PDH/PDL (previous day high/low)
│      ├─ Find Opening Range (first 30 min)
│      ├─ Identify VPOC
│      └─ Find session levels (Asian, London, NY)
│
├─ SIGNAL DETECTION
│  └─► SignalDetector.detect_signals()
│      ├─ Check price proximity to key levels (±5 ticks)
│      ├─ Detect order flow signals:
│      │  ├─ Absorption
│      │  ├─ Imbalance stacking (3+ consecutive)
│      │  ├─ Delta divergence
│      │  ├─ Iceberg detection
│      │  └─ Exhaustion
│      ├─ Additional signals:
│      │  ├─ Candle imbalance (CRT)
│      │  ├─ ICT order blocks
│      │  └─ Liquidity delta profiles
│      │
│      └─► Signal validation: need 3-5 of 5 confirmations
│          1. Key level proximity ✓
│          2. Order flow signal ✓
│          3. Volume profile context ✓
│          4. Delta confirmation ✓
│          5. Tape (DOM) confirmation ✓
│
├─ POSITION SIZING & ENTRY
│  ├─► RiskManager.calculate_position_size()
│  │   ├─ risk_amount = balance × 1%
│  │   ├─ lots = risk_amount / (SL_ticks × tick_value)
│  │   └─ Clamp to [volume_min, volume_max]
│  │
│  ├─► RiskManager.check_rr_ratio()
│  │   └─ Validate minimum R:R ≥ 1:1.5
│  │
│  └─► Executor.open_trade(direction, volume, SL, TPs)
│      ├─ [DRY_RUN=False] → MT5: send market order
│      ├─ [DRY_RUN=True]  → Simulate only
│      └─ Create ManagedPosition object
│
└─► POSITION MANAGEMENT (100ms, separate thread)
    └─► Executor.manage_positions(current_bid, delta_reversing)
        ├─ Check each open position vs TP levels
        ├─ Execute partial closes (50% → TP1, 30% → TP2, 20% → TP3)
        ├─ Trail SL to breakeven after TP1
        ├─ Delta-based trailing after TP2
        └─ Record trade in Journal

        ↓ ↓ ↓

JOURNAL LOGGING
└─► Journal.record_trade()
    ├─ Append to CSV (trade_journal.csv)
    ├─ Insert into SQLite (trade_journal.db)
    └─ Running session summary (on shutdown)

```

---

## 4. OBJECT HIERARCHY & ATTRIBUTES

### Core Data Classes

#### **SymbolSpec** (mt5_connector.py)
```python
@dataclass
class SymbolSpec:
    name: str                    # e.g., "BTCUSDm"
    digits: int                  # decimal places
    point: float                 # minimum price change
    tick_size: float             # price step
    tick_value: float            # monetary value of 1 tick × 1 lot
    volume_min: float            # minimum lot size
    volume_max: float            # maximum lot size
    volume_step: float           # lot rounding step
    trade_contract_size: float   # contract multiplier
    spread: int                  # current bid-ask spread in points
```

#### **AccountState** (mt5_connector.py)
```python
@dataclass
class AccountState:
    balance: float      # account balance
    equity: float       # current equity (balance ± P&L)
    margin: float       # margin used
    margin_free: float  # available margin
    leverage: int       # leverage ratio
    currency: str       # account currency
```

#### **TickData** (data_puller.py)
```python
@dataclass
class TickData:
    df: pd.DataFrame      # Columns: time_msc, bid, ask, last, volume, flags, 
                          #          is_buy, is_sell, buy_vol, sell_vol, delta
    has_trade_flags: bool # True if TICK_FLAG_BUY/SELL present in data
    symbol: str
    pulled_at: datetime
```

#### **BarData** (data_puller.py)
```python
@dataclass
class BarData:
    df: pd.DataFrame      # Columns: time, open, high, low, close, tick_volume, 
                          #          spread, real_volume, datetime
    timeframe: int        # mt5.TIMEFRAME_M1, M5, D1, etc.
    symbol: str
```

#### **DOMSnapshot** (data_puller.py)
```python
@dataclass
class DOMSnapshot:
    bids: List[DOMLevel]  # Bid side order book levels
    asks: List[DOMLevel]  # Ask side order book levels
    timestamp: datetime
    
    # Properties:
    best_bid: Optional[float]  # bids[0].price
    best_ask: Optional[float]  # asks[0].price
```

#### **FootprintBar** (footprint.py)
```python
@dataclass
class FootprintBar:
    bar_time: pd.Timestamp
    bar_open: float
    bar_high: float
    bar_low: float
    bar_close: float
    levels: Dict[float, FootprintLevel]  # price → FootprintLevel
    total_buy_vol: float
    total_sell_vol: float
    
    # Properties:
    bar_delta: float      # total_buy_vol - total_sell_vol
    is_bullish: bool      # close >= open
```

#### **Signal** (signals.py)
```python
@dataclass
class Signal:
    signal_type: SignalType    # ABSORPTION, IMBALANCE_STACK, DELTA_DIVERGENCE, etc.
    direction: str             # 'long' or 'short'
    key_level: float           # price level where signal detected
    confidence: float          # 0.0 - 1.0
    bar_time: pd.Timestamp
    details: dict              # Extra context (imbalance ratio, absorption vol, etc.)
```

#### **ManagedPosition** (executor.py)
```python
@dataclass
class ManagedPosition:
    ticket: int                # MT5 order ticket (or fake ID in DRY_RUN)
    direction: str             # 'long' or 'short'
    entry_price: float
    stop_loss: float
    take_profits: List[float]  # [TP1, TP2, TP3]
    total_volume: float
    remaining_volume: float
    risk_amount: float
    tp_stage: int              # 0=none, 1=TP1 hit, 2=TP2 hit, 3=all closed
    breakeven_moved: bool
    opened_at: datetime
```

#### **VolumeProfile** (volume_profile.py)
```python
@dataclass
class VolumeProfile:
    poc: float                          # Point of Control (price with most volume)
    vah: float                          # Value Area High (70% volume)
    val: float                          # Value Area Low
    hvn: List[float]                    # High Volume Nodes
    lvn: List[float]                    # Low Volume Nodes
    price_to_volume: Dict[float, float] # price → total volume
    timestamp: datetime
```

#### **KeyLevels** (key_levels.py)
```python
@dataclass
class KeyLevels:
    pdh: float          # Previous Day High
    pdl: float          # Previous Day Low
    vpoc: float         # Volume POC
    opening_range_high: float
    opening_range_low: float
    vah: float          # Value Area High
    val: float          # Value Area Low
    session_levels: Dict[str, float]  # 'london_open', 'ny_open', etc.
```

---

## 5. KEY IMPORT DEPENDENCIES

### Python Standard Library
```python
import logging          # Logging setup
import signal          # Shutdown handling (SIGINT, SIGTERM)
import sys             # stdout/stderr
import threading       # 3-thread architecture
import time
from datetime import datetime, timezone, timedelta, time
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict
from enum import Enum
import csv             # Journal CSV export
import sqlite3         # Trade database
import os
```

### Third-Party (Must Install)
```python
import MetaTrader5 as mt5  # CRITICAL: pip install MetaTrader5
import pandas as pd        # CRITICAL: pip install pandas
import numpy as np         # CRITICAL: pip install numpy
```

### Internal Project Imports (Relative)
```python
# These are all inside the order_flow_scalper package:

from . import config                    # All configuration

# Core components
from .mt5_connector import MT5Connector, SymbolSpec, AccountState
from .data_puller import DataPuller, TickData, BarData, DOMSnapshot
from .risk_manager import RiskManager, TradeResult
from .executor import Executor, ManagedPosition
from .journal import Journal, TradeRecord
from .scanner import Scanner

# Analysis modules
from .delta import DeltaEngine, DeltaBar, Divergence
from .footprint import FootprintBuilder, FootprintBar, FootprintLevel, ImbalanceStack
from .volume_profile import build_volume_profile, VolumeProfile, VolumeProfiler
from .key_levels import KeyLevelBuilder, KeyLevels
from .signals import SignalDetector, Signal, SignalType

# Advanced features
from .candle_imbalance import CandleImbalanceDetector, CandleImbalance, ImbalanceDirection
from .ict_order_blocks import OrderBlockDetector, OrderBlock, OrderBlockType
from .ldp import LiquidityDeltaProfiler, LDPSignalType
from .session_config import SessionManager
from .loss_prevention import LossPreventionValidator
from .trade_reasoner import TradeReasoner
```

---

## 6. CONFIGURATION HIERARCHY

All settings in **`config.py`**:

```python
# Connection
MT5_PATH, MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_TIMEOUT

# Symbol
SYMBOL, IS_CRYPTO, TIMEFRAME_PRIMARY, TIMEFRAME_CONTEXT, TIMEFRAME_DAILY

# Risk (1% rule, daily limits, R:R validation)
RISK_PER_TRADE = 0.01     # 1% per trade
MAX_DAILY_LOSS = 0.03     # Stop at 3% loss
MAX_CONSECUTIVE_LOSSES = 3
MIN_RR_RATIO = 1.5        # Minimum Risk:Reward

# Scale-out plan
TP1_TICKS, TP2_TICKS, TP3_TICKS, STOP_TICKS
TP_SPLIT = [0.50, 0.30, 0.20]

# Order flow thresholds
IMBALANCE_RATIO = 3.0
MIN_CONSECUTIVE_IMBALANCES = 3
ABSORPTION_VOL_MULTIPLIER = 2.0
VOLUME_SPIKE_MULTIPLIER = 1.5
DELTA_DIVERGENCE_LOOKBACK = 20

# Volume profile
VALUE_AREA_PCT = 0.70
HVN_THRESHOLD = 1.5
LVN_THRESHOLD = 0.5
COMPOSITE_DAYS = 5

# Key level proximity
PROXIMITY_TICKS = 5

# Killzones (EST)
KILLZONES = [(2,0, 5,0), (8,30, 11,0)]  # London Open, NY Open
DEAD_ZONE = (12,0, 14,0)                # 12:00-14:00 EST

# Polling intervals
TICK_POLL_INTERVAL_MS = 100     # Data thread
DOM_POLL_INTERVAL_MS = 200
ANALYSIS_INTERVAL_MS = 500      # Scanner thread
PROFILE_REBUILD_SECS = 60

# Execution
MAGIC_NUMBER = 240001
DEVIATION = 5
DRY_RUN = True              # CRITICAL: Set False for live trading

# Advanced features
CANDLE_IMBALANCE_VOLUME_RATIO_THRESHOLD = 0.60
ORDER_BLOCK_LOOKBACK = 20
USE_HEURISTIC_DIRECTION = False
```

---

## 7. MODULE INTER-DEPENDENCIES

```
config.py (imports nothing else)
    ↑ ↑ ↑ (ALL modules depend on config)

mt5_connector.py
    └─ config, logging

data_puller.py
    └─ config, logging, mt5 API (MetaTrader5)

risk_manager.py
    └─ config, logging

delta.py
    └─ config, logging, footprint

footprint.py
    └─ config, logging

volume_profile.py
    └─ config, logging

key_levels.py
    └─ config, logging, data_puller (for bar data)

signals.py
    ├─ config, logging
    ├─ footprint, delta
    ├─ key_levels
    ├─ data_puller (DOMSnapshot)
    ├─ candle_imbalance
    ├─ ict_order_blocks
    ├─ ldp
    ├─ session_config
    ├─ loss_prevention
    └─ trade_reasoner

executor.py
    └─ config, logging, mt5 API

journal.py
    └─ config, logging, csv, sqlite3

scanner.py
    ├─ config, logging
    ├─ mt5_connector
    ├─ data_puller
    ├─ volume_profile
    ├─ key_levels
    ├─ footprint
    ├─ delta
    ├─ signals
    ├─ risk_manager
    ├─ executor
    └─ journal

main.py (OrderFlowScalper)
    ├─ config, logging, signal, sys, threading, time
    ├─ mt5_connector
    ├─ data_puller
    ├─ risk_manager
    ├─ executor
    ├─ journal
    └─ scanner

__main__.py
    └─ main

candle_imbalance.py
    └─ config, logging

ict_order_blocks.py
    └─ config, logging

ldp.py
    └─ config, logging, delta

session_config.py
    └─ config, logging

loss_prevention.py
    └─ config, logging

trade_reasoner.py
    └─ config, logging

chart.py (Visualization)
    └─ config, logging, matplotlib (optional)
```

---

## 8. SIGNAL CONFIRMATION LOGIC

All signals require **3-5 of 5 confirmations**:

```python
class SignalConfirmation(Enum):
    KEY_LEVEL = "key_level"           # Price within ±5 ticks of PDH/PDL/VPOC/VAH/VAL/OR
    ORDER_FLOW = "order_flow"         # Absorption / imbalance / delta divergence / iceberg
    VOLUME_PROFILE = "volume_profile" # Rejection at VAH/VAL, bounce off VPOC
    DELTA = "delta_confirm"           # Cumulative delta supports trade direction
    TAPE = "tape_confirm"             # DOM shows passive support/resistance at level
```

A trade is placed when:
- **At least 3 confirmations** trigger at the same price level, OR
- **More than 5 confirmations** are available and 4+ are present

---

## 9. THREADING & SYNCHRONIZATION

```
MAIN THREAD
│
├─ OrderFlowScalper.start()
│  ├─ Connect to MT5
│  ├─ Subscribe to DOM
│  ├─ Create shared objects:
│  │  ├─ MT5Connector (thread-safe)
│  │  ├─ DataPuller (thread-safe)
│  │  ├─ RiskManager (shared state)
│  │  ├─ Executor (shared _positions dict)
│  │  ├─ Journal (shared CSV/DB)
│  │  └─ Scanner (orchestrator)
│  │
│  ├─ Thread 1: _analysis_loop() every 500ms
│  │  └─ scanner.run_cycle()
│  │
│  ├─ Thread 2: _management_loop() every 100ms
│  │  └─ executor.manage_positions()
│  │
│  └─ BLOCKING WAIT for Ctrl+C
│     └─ _cleanup()

SYNCHRONIZATION NOTES:
- No explicit locks (assumes GIL for single-threaded Python bytecode access)
- DataPuller pulls fresh data each cycle (never cached)
- Executor._positions dict accessed by both threads
- Journal appends are atomic (each record is one write)
```

---

## 10. COMMON PATTERNS & CONVENTIONS

### Error Handling
```python
if condition is None:
    log.error("Descriptive error message")
    return None  # Graceful failure (no exceptions)
```

### Logging
```python
log = logging.getLogger(__name__)
log.info("Normal operation")
log.warning("Non-critical issue")
log.error("Recoverable error")
log.critical("Fatal error — shutting down")
log.debug("Dev-only, not shown in INFO mode")
```

### Dataclass Usage
```python
@dataclass
class MyData:
    field1: type
    field2: type = field(default_factory=list)  # Mutable default
```

### Optional Returns
```python
Optional[ReturnType]  # Could be ReturnType or None
```

### DataFrame Columns
```python
df['time_msc']      # Tick timestamp in milliseconds
df['bid'], df['ask'] # Bid/ask prices
df['last'], df['volume'] # Last trade price & volume
df['flags']         # Bit flags (TICK_FLAG_BUY, TICK_FLAG_SELL, etc.)
df['datetime']      # Converted to UTC datetime
```

---

## 11. ENTRY POINTS

### For v0 Deployment / Standalone
```python
# In __main__.py:
python -m order_flow_scalper
```

### Programmatic
```python
from order_flow_scalper.main import OrderFlowScalper
scalper = OrderFlowScalper()
scalper.start()
```

---

## 12. QUICK REFERENCE: OBJECTS & ATTRIBUTES

| Object | Module | Key Attributes |
|--------|--------|-----------------|
| **SymbolSpec** | mt5_connector | name, digits, point, tick_size, tick_value, volume_min/max, spread |
| **AccountState** | mt5_connector | balance, equity, margin, margin_free, leverage, currency |
| **TickData** | data_puller | df (DataFrame), has_trade_flags, symbol, pulled_at |
| **BarData** | data_puller | df, timeframe, symbol |
| **DOMSnapshot** | data_puller | bids[], asks[], timestamp, best_bid, best_ask |
| **FootprintBar** | footprint | bar_time, bar_open/high/low/close, levels{}, bar_delta, is_bullish |
| **VolumeProfile** | volume_profile | poc, vah, val, hvn[], lvn[], price_to_volume{} |
| **KeyLevels** | key_levels | pdh, pdl, vpoc, opening_range_high/low, vah, val, session_levels{} |
| **Signal** | signals | signal_type, direction, key_level, confidence, bar_time, details{} |
| **ManagedPosition** | executor | ticket, direction, entry_price, stop_loss, take_profits[], tp_stage, opened_at |
| **RiskManager** | risk_manager | _trades_today[], _starting_balance, can_trade(), record_trade() |
| **Executor** | executor | spec, _positions{}, open_trade(), manage_positions(), has_open_positions() |
| **Journal** | journal | trades[], record_trade(), print_summary() |

---

## 13. ADVANCED FEATURES (v3+)

### New Modules Added
- **candle_imbalance.py**: CRT (Candle Range Technique) detection
- **ict_order_blocks.py**: ICT Smart Money concepts
- **ldp.py**: Liquidity Delta Profiler (advanced delta analysis)
- **session_config.py**: Session awareness (Asian, London, NY)
- **loss_prevention.py**: Drawdown & anomaly protection
- **trade_reasoner.py**: Structured trade reasoning/justification

All integrated into `SignalDetector` in `signals.py` for unified signal generation.

---

## 14. TROUBLESHOOTING IMPORT ERRORS

If you see `ModuleNotFoundError: No module named 'order_flow_scalper'`:

1. **Verify package structure**: `__init__.py` must exist in the root directory
2. **Run from parent**: If in `/home/user/projects/order_flow_scalper/`, run from `/home/user/projects/`
3. **Add to PYTHONPATH**: `export PYTHONPATH=/home/user/projects:$PYTHONPATH`
4. **Use absolute imports**: Already done in all files (using `from . import config`)

---

**End of Architecture Map**
