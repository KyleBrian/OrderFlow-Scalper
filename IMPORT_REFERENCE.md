# Order Flow Scalper - Complete Import Reference Guide

**Quick lookup for all imports, modules, classes, and functions.**

---

## TABLE OF CONTENTS
1. [External Dependencies (pip install)](#external-dependencies)
2. [Python Standard Library](#python-standard-library)
3. [Project Internal Imports](#project-internal-imports)
4. [Class & Function Reference](#class--function-reference)
5. [Module Dependency Graph](#module-dependency-graph)
6. [Import Troubleshooting](#import-troubleshooting)

---

## EXTERNAL DEPENDENCIES

### Must Install with pip

```bash
pip install MetaTrader5==5.0.5113
pip install pandas>=2.0.0
pip install numpy>=1.24.0
```

| Package | Version | Used For | Priority |
|---------|---------|----------|----------|
| **MetaTrader5** | 5.0.5113+ | MT5 API connection, order placement | 🔴 **CRITICAL** |
| **pandas** | 2.0.0+ | DataFrame operations, data manipulation | 🔴 **CRITICAL** |
| **numpy** | 1.24.0+ | Numerical arrays, calculations | 🔴 **CRITICAL** |
| matplotlib | 3.7.0+ | Footprint chart visualization | 🟡 Optional |
| scipy | 1.10.0+ | Scientific calculations | 🟡 Optional |

### Import Statements

```python
# Core (REQUIRED)
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

# Optional
import matplotlib.pyplot as plt
from scipy import stats
```

### Troubleshooting

**"No module named 'MetaTrader5'"**
```bash
pip install MetaTrader5
python -c "import MetaTrader5; print(MetaTrader5.version())"
```

**Wrong version**
```bash
pip show MetaTrader5
# Should show version 5.0.5113 or higher

# Upgrade if needed
pip install --upgrade MetaTrader5
```

---

## PYTHON STANDARD LIBRARY

Used throughout the project (no installation needed):

```python
import logging              # Logging framework (used everywhere)
import signal              # Signal handling (SIGINT, SIGTERM)
import sys                 # stdout, exit codes
import threading           # 3-thread architecture
import time                # Sleep, timing
from datetime import datetime, timezone, timedelta, time
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Tuple, Dict, Set
from enum import Enum     # Signal type definitions
import csv                # CSV export (Journal)
import sqlite3            # SQLite database (Journal)
import os                 # File path operations
import json               # Config serialization (optional)
from abc import ABC, abstractmethod  # Base classes
import uuid               # Trade ID generation
```

---

## PROJECT INTERNAL IMPORTS

### Import Pattern (Relative Imports)

All internal imports use **relative imports** (prefix with `.`):

```python
from . import config                    # Config module
from .mt5_connector import MT5Connector # Class
from .module_name import ClassName     # Class from module
```

### All Modules & What They Export

#### **1. config.py**
```python
# No classes — all constants
MT5_LOGIN: int
MT5_PASSWORD: str
MT5_SERVER: str
SYMBOL: str
IS_CRYPTO: bool
RISK_PER_TRADE: float
MAX_DAILY_LOSS: float
DRY_RUN: bool
# ... 50+ more constants
```

**Imported by**: Every other module
**Usage**: `from . import config` then `config.SYMBOL`, `config.DRY_RUN`

---

#### **2. mt5_connector.py**
```python
# Classes
@dataclass
class SymbolSpec:
    name: str
    digits: int
    point: float
    tick_size: float
    tick_value: float
    volume_min: float
    volume_max: float
    volume_step: float
    trade_contract_size: float
    spread: int

@dataclass
class AccountState:
    balance: float
    equity: float
    margin: float
    margin_free: float
    leverage: int
    currency: str

class MT5Connector:
    def __init__(self)
    def connect(self) -> bool
    def disconnect(self)
    def subscribe_dom(self) -> bool
    def refresh_account(self) -> Optional[AccountState]
    def get_account_state(self) -> Optional[AccountState]
    @property spec(self) -> Optional[SymbolSpec]
    @property is_connected(self) -> bool
    @property has_dom(self) -> bool
```

**Imported by**: main.py, scanner.py
**Usage**: 
```python
from .mt5_connector import MT5Connector, SymbolSpec, AccountState
connector = MT5Connector()
connector.connect()
spec = connector.spec  # SymbolSpec
```

---

#### **3. data_puller.py**
```python
# Data classes
@dataclass
class TickData:
    df: pd.DataFrame
    has_trade_flags: bool
    symbol: str
    pulled_at: datetime

@dataclass
class BarData:
    df: pd.DataFrame
    timeframe: int
    symbol: str

@dataclass
class DOMLevel:
    side: str
    price: float
    volume: float

@dataclass
class DOMSnapshot:
    bids: List[DOMLevel]
    asks: List[DOMLevel]
    timestamp: datetime
    @property best_bid(self) -> Optional[float]
    @property best_ask(self) -> Optional[float]

# Main class
class DataPuller:
    def __init__(self, symbol: str = None)
    def pull_ticks_session(self, session_start: datetime = None) -> Optional[TickData]
    def pull_ticks_recent(self, count: int = 5000) -> Optional[TickData]
    def pull_trade_ticks(self, since: datetime = None, count: int = 10000) -> Optional[TickData]
    def pull_bars(self, timeframe: int = None, count: int = 500) -> Optional[BarData]
    def pull_daily_bars(self, count: int = 10) -> Optional[BarData]
    def pull_bars_range(self, timeframe: int, date_from: datetime, date_to: datetime) -> Optional[BarData]
    def pull_dom(self) -> Optional[DOMSnapshot]
    def get_current_tick(self)
```

**Imported by**: main.py, scanner.py
**Usage**:
```python
from .data_puller import DataPuller, TickData, BarData, DOMSnapshot
puller = DataPuller(config.SYMBOL)
ticks = puller.pull_ticks_session()
bars = puller.pull_bars(mt5.TIMEFRAME_M1, count=500)
```

---

#### **4. risk_manager.py**
```python
@dataclass
class TradeResult:
    pnl: float
    r_multiple: float
    is_win: bool
    closed_at: datetime

class RiskManager:
    def __init__(self)
    def reset_day(self, starting_balance: float)
    def calculate_position_size(self, account_balance: float, stop_distance_ticks: int, 
                               tick_value: float, volume_min: float, volume_step: float, 
                               volume_max: float) -> float
    def can_trade(self, current_time: datetime = None) -> Tuple[bool, str]
    def check_rr_ratio(self, entry: float, stop: float, tp1: float) -> Tuple[bool, float]
    def record_trade(self, pnl: float, risk_amount: float)
    def daily_pnl(self) -> float
    def daily_trades(self) -> int
    def daily_win_rate(self) -> float
    @staticmethod is_in_killzone(dt: datetime) -> bool
    @staticmethod is_in_dead_zone(dt: datetime) -> bool
```

**Imported by**: main.py, scanner.py
**Usage**:
```python
from .risk_manager import RiskManager
risk = RiskManager()
risk.reset_day(account_balance)
can_trade, reason = risk.can_trade()
```

---

#### **5. delta.py**
```python
@dataclass
class DeltaBar:
    bar_time: pd.Timestamp
    buy_vol: float
    sell_vol: float
    delta: float
    cum_delta: float
    close: float

@dataclass
class Divergence:
    direction: str  # 'bullish' or 'bearish'
    price_swing1: float
    price_swing2: float
    delta_swing1: float
    delta_swing2: float
    bar_time: pd.Timestamp
    strength: float

class DeltaEngine:
    def __init__(self)
    def reset(self)
    def compute_bars(self, tick_data: TickData, bars: BarData) -> List[DeltaBar]
    def detect_divergences(self, bars: BarData) -> List[Divergence]
    def is_delta_reversing(self, direction: str) -> bool
```

**Imported by**: scanner.py, signals.py
**Usage**:
```python
from .delta import DeltaEngine, DeltaBar, Divergence
delta_engine = DeltaEngine()
delta_bars = delta_engine.compute_bars(tick_data, bars)
divergences = delta_engine.detect_divergences(bars)
```

---

#### **6. footprint.py**
```python
@dataclass
class FootprintLevel:
    price: float
    bid_vol: float
    ask_vol: float
    @property delta(self) -> float
    @property total(self) -> float

@dataclass
class FootprintBar:
    bar_time: pd.Timestamp
    bar_open: float
    bar_high: float
    bar_low: float
    bar_close: float
    levels: Dict[float, FootprintLevel]
    total_buy_vol: float
    total_sell_vol: float
    @property bar_delta(self) -> float
    @property is_bullish(self) -> bool

@dataclass
class ImbalanceStack:
    prices: List[float]
    direction: str  # 'long' or 'short'
    avg_ratio: float

class FootprintBuilder:
    def __init__(self, tick_size: float)
    def build_bars(self, tick_data: TickData, bars: BarData) -> List[FootprintBar]
    def detect_imbalances(self, bars: List[FootprintBar]) -> List[ImbalanceStack]
    def detect_absorption(self, bars: List[FootprintBar]) -> Dict[float, float]
    def detect_exhaustion(self, bars: List[FootprintBar]) -> Dict[float, bool]
```

**Imported by**: scanner.py, signals.py
**Usage**:
```python
from .footprint import FootprintBuilder, FootprintBar
builder = FootprintBuilder(tick_size=0.01)
footprints = builder.build_bars(tick_data, bars)
imbalances = builder.detect_imbalances(footprints)
```

---

#### **7. volume_profile.py**
```python
@dataclass
class VolumeProfile:
    poc: float
    vah: float
    val: float
    hvn: List[float]
    lvn: List[float]
    price_to_volume: Dict[float, float]
    timestamp: datetime

class VolumeProfiler:
    def __init__(self)
    def compute(self, tick_data: TickData, bars: BarData) -> VolumeProfile
    def compute_composite(self, tick_data_list: List[TickData], days: int = 5) -> VolumeProfile

def build_volume_profile(tick_data: TickData, bars: BarData) -> VolumeProfile:
    """Standalone function"""
```

**Imported by**: scanner.py
**Usage**:
```python
from .volume_profile import VolumeProfiler, VolumeProfile, build_volume_profile
profiler = VolumeProfiler()
profile = profiler.compute(tick_data, bars)
print(f"POC: {profile.poc}, VAH: {profile.vah}, VAL: {profile.val}")
```

---

#### **8. key_levels.py**
```python
@dataclass
class KeyLevels:
    pdh: float
    pdl: float
    vpoc: float
    opening_range_high: float
    opening_range_low: float
    vah: float
    val: float
    session_levels: Dict[str, float]

class KeyLevelBuilder:
    def __init__(self)
    def rebuild(self, bars: BarData, volume_profile: VolumeProfile) -> KeyLevels
```

**Imported by**: scanner.py, signals.py
**Usage**:
```python
from .key_levels import KeyLevelBuilder, KeyLevels
builder = KeyLevelBuilder()
levels = builder.rebuild(bars, volume_profile)
print(f"PDH: {levels.pdh}, PDL: {levels.pdl}")
```

---

#### **9. signals.py** (LARGE - Core signal detection)
```python
class SignalType(Enum):
    ABSORPTION = "absorption"
    IMBALANCE_STACK = "imbalance_stack"
    DELTA_DIVERGENCE = "delta_divergence"
    ICEBERG = "iceberg"
    EXHAUSTION = "exhaustion"
    CANDLE_IMBALANCE = "candle_imbalance"
    ORDER_BLOCK = "order_block"
    LDP_ABSORPTION = "ldp_absorption"
    LDP_EXHAUSTION = "ldp_exhaustion"
    LDP_DIVERGENCE = "ldp_divergence"
    LDP_REJECTION = "ldp_rejection"

@dataclass
class Signal:
    signal_type: SignalType
    direction: str
    key_level: float
    confidence: float
    bar_time: pd.Timestamp
    details: dict = field(default_factory=dict)
    def __str__(self) -> str

class SignalDetector:
    def __init__(self, footprint_builder: FootprintBuilder, delta_engine: DeltaEngine, tick_size: float)
    def detect_signals(self, tick_data: TickData, bars: BarData, 
                      volume_profile: VolumeProfile, key_levels: KeyLevels) -> List[Signal]
    def validate_confluence(self, signals: List[Signal]) -> List[Signal]
```

**Imported by**: scanner.py
**Usage**:
```python
from .signals import SignalDetector, Signal, SignalType
detector = SignalDetector(footprint_builder, delta_engine, tick_size=0.01)
signals = detector.detect_signals(tick_data, bars, volume_profile, key_levels)
valid_signals = detector.validate_confluence(signals)
```

---

#### **10. executor.py**
```python
@dataclass
class ManagedPosition:
    ticket: int
    direction: str  # 'long' or 'short'
    entry_price: float
    stop_loss: float
    take_profits: List[float]
    total_volume: float
    remaining_volume: float
    risk_amount: float
    tp_stage: int = 0
    breakeven_moved: bool = False
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class Executor:
    def __init__(self, symbol_spec: SymbolSpec)
    def open_trade(self, direction: str, volume: float, stop_loss: float, 
                  take_profits: List[float], risk_amount: float) -> Optional[ManagedPosition]
    def manage_positions(self, current_bid: float, delta_reversing: bool = False)
    def has_open_positions(self) -> bool
    def get_positions(self) -> List[ManagedPosition]
    def emergency_close_all(self, reason: str)
```

**Imported by**: main.py, scanner.py
**Usage**:
```python
from .executor import Executor, ManagedPosition
executor = Executor(symbol_spec)
pos = executor.open_trade("long", volume=0.1, stop_loss=100.0, take_profits=[106,110,116], risk_amount=50.0)
executor.manage_positions(current_bid=102.5)
```

---

#### **11. journal.py**
```python
@dataclass
class TradeRecord:
    trade_id: int
    opened_at: str
    closed_at: str
    symbol: str
    direction: str
    signal_type: str
    # ... 15+ more fields

class Journal:
    def __init__(self)
    def record_trade(self, record: TradeRecord)
    def print_summary(self)
```

**Imported by**: main.py, scanner.py
**Usage**:
```python
from .journal import Journal, TradeRecord
journal = Journal()
# After trade closes:
record = TradeRecord(trade_id=1, opened_at="...", closed_at="...", ...)
journal.record_trade(record)
journal.print_summary()  # On shutdown
```

---

#### **12. scanner.py** (Orchestrator - brings everything together)
```python
class Scanner:
    def __init__(self, connector: MT5Connector, puller: DataPuller, 
                 risk_mgr: RiskManager, executor: Executor, journal: Journal)
    def run_cycle(self) -> bool
    # Internal methods for each step
```

**Imported by**: main.py
**Usage**:
```python
from .scanner import Scanner
scanner = Scanner(connector, puller, risk_mgr, executor, journal)
# In main loop:
scanner.run_cycle()  # Called every 500ms
```

---

#### **13. main.py** (Entry point controller)
```python
class OrderFlowScalper:
    def __init__(self)
    def start(self)
    def _analysis_loop(self)
    def _management_loop(self)
    def _cleanup(self)

def main():
    scalper = OrderFlowScalper()
    scalper.start()

if __name__ == "__main__":
    main()
```

**Entry point**: `python -m order_flow_scalper`

---

#### **14. Advanced Modules**

```python
# candle_imbalance.py
class CandleImbalanceDetector
class CandleImbalance
class ImbalanceDirection(Enum)

# ict_order_blocks.py
class OrderBlockDetector
class OrderBlock
class OrderBlockType(Enum)

# ldp.py
class LiquidityDeltaProfiler
class LDPSignalType(Enum)

# session_config.py
class SessionManager

# loss_prevention.py
class LossPreventionValidator

# trade_reasoner.py
class TradeReasoner
```

All are imported by `signals.py` for unified signal generation.

---

## CLASS & FUNCTION REFERENCE

### Most-Used Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `MT5Connector` | mt5_connector | Connect/manage MT5 terminal |
| `DataPuller` | data_puller | Fetch ticks, bars, DOM |
| `RiskManager` | risk_manager | Position sizing, risk checks |
| `DeltaEngine` | delta | Delta analysis |
| `FootprintBuilder` | footprint | Build footprint charts |
| `VolumeProfiler` | volume_profile | Volume profile computation |
| `KeyLevelBuilder` | key_levels | Key level identification |
| `SignalDetector` | signals | Signal detection + validation |
| `Executor` | executor | Order placement & management |
| `Journal` | journal | Trade logging |
| `Scanner` | scanner | Analysis orchestrator |
| `OrderFlowScalper` | main | System controller |

### Most-Used Functions

| Function | Module | Signature |
|----------|--------|-----------|
| `pull_ticks_session()` | data_puller | `(session_start: datetime = None) -> Optional[TickData]` |
| `pull_bars()` | data_puller | `(timeframe: int, count: int) -> Optional[BarData]` |
| `pull_dom()` | data_puller | `() -> Optional[DOMSnapshot]` |
| `can_trade()` | risk_manager | `(current_time: datetime) -> Tuple[bool, str]` |
| `calculate_position_size()` | risk_manager | `(...) -> float` |
| `open_trade()` | executor | `(direction, volume, stop_loss, take_profits, risk_amount) -> Optional[ManagedPosition]` |
| `manage_positions()` | executor | `(current_bid: float, delta_reversing: bool)` |
| `detect_signals()` | signals | `(tick_data, bars, volume_profile, key_levels) -> List[Signal]` |
| `run_cycle()` | scanner | `() -> bool` |

---

## MODULE DEPENDENCY GRAPH

```
config.py (↑ imported by ALL)
    ↑
    ├─ mt5_connector.py
    │  ├─ main.py
    │  └─ scanner.py
    │
    ├─ data_puller.py
    │  ├─ main.py
    │  └─ scanner.py
    │
    ├─ risk_manager.py
    │  ├─ main.py
    │  └─ scanner.py
    │
    ├─ delta.py
    │  ├─ footprint.py
    │  ├─ signals.py
    │  └─ scanner.py
    │
    ├─ footprint.py
    │  ├─ signals.py
    │  └─ scanner.py
    │
    ├─ volume_profile.py
    │  ├─ signals.py
    │  └─ scanner.py
    │
    ├─ key_levels.py
    │  ├─ signals.py
    │  └─ scanner.py
    │
    ├─ signals.py
    │  ├─ candle_imbalance.py
    │  ├─ ict_order_blocks.py
    │  ├─ ldp.py
    │  ├─ session_config.py
    │  ├─ loss_prevention.py
    │  ├─ trade_reasoner.py
    │  └─ scanner.py
    │
    ├─ executor.py
    │  ├─ main.py
    │  └─ scanner.py
    │
    ├─ journal.py
    │  ├─ main.py
    │  └─ scanner.py
    │
    └─ scanner.py
       └─ main.py
           └─ __main__.py
               └─ [ENTRY POINT]
```

---

## IMPORT TROUBLESHOOTING

### Problem: "Cannot import name 'X' from 'order_flow_scalper.Y'"

**Solution:**
1. Check class/function exists in the module file
2. Ensure correct spelling (case-sensitive)
3. Check module hasn't been renamed

Example:
```python
# ✓ Correct
from .delta import DeltaEngine, DeltaBar

# ✗ Wrong (class doesn't exist)
from .delta import DeltaEngine, DeltaBars  # DeltaBars → DeltaBar
```

### Problem: "Circular import"

**Symptom**: Module imports A, A imports B, B imports A

**Solution**: Refactor to move shared code to a utility module, or use late imports inside functions.

*This project avoids circular imports by design.*

### Problem: "ModuleNotFoundError: No module named 'order_flow_scalper'"

**Solution:**
```bash
# Ensure you're in the correct directory
cd OrderFlow-Scalper

# Verify __init__.py exists
ls __init__.py

# Run from parent directory
cd ..
python -m order_flow_scalper
```

### Problem: "ImportError: cannot import name 'mt5' from 'MetaTrader5'"

**Solution:**
```bash
pip uninstall MetaTrader5 -y
pip install MetaTrader5==5.0.5113
python -c "import MetaTrader5 as mt5; print(mt5.version())"
```

---

## QUICK IMPORT CHEAT SHEET

```python
# Most common imports in your code:

# External
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timezone

# Internal
from . import config
from .mt5_connector import MT5Connector
from .data_puller import DataPuller, TickData, BarData, DOMSnapshot
from .risk_manager import RiskManager
from .delta import DeltaEngine
from .footprint import FootprintBuilder
from .volume_profile import VolumeProfiler, build_volume_profile
from .key_levels import KeyLevelBuilder
from .signals import SignalDetector, Signal, SignalType
from .executor import Executor, ManagedPosition
from .journal import Journal
from .scanner import Scanner
```

---

**End of Import Reference Guide**
