# Order Flow Scalper - Complete System Overview

**Visual summary of the entire system, all modules, and how they work together.**

---

## SYSTEM AT A GLANCE

```
┌─────────────────────────────────────────────────────────────┐
│                    ORDER FLOW SCALPER v3+                   │
│        3-Thread Order Flow Scalping System for MT5           │
└─────────────────────────────────────────────────────────────┘

PURPOSE: Detect high-probability scalping entries using:
  • Order flow analysis (footprint, absorption, imbalance)
  • Delta divergence detection
  • Volume profile with key levels
  • Risk-managed position sizing (1% rule)
  • Automated scale-out exits (50%/30%/20%)

TARGET: Crypto & Forex scalpers trading on MetaTrader 5
TIMEFRAME: 1-minute (M1) analysis with 5-minute (M5) context
RISK MANAGEMENT: 3% daily loss limit, 3 consecutive loss limit
TRADING HOURS: London Open (02:00-05:00 EST) + NY Open (08:30-11:00 EST)
                (24/7 for crypto)
```

---

## CORE ARCHITECTURE: 3-THREAD MODEL

```
┌─────────────────────────────────────────────────────────────┐
│                      MAIN THREAD                            │
│        OrderFlowScalper Controller (Orchestrator)           │
│                                                              │
│  • Initialize MT5 & components                              │
│  • Launch analyzer & manager threads                        │
│  • Handle Ctrl+C gracefully                                 │
│  • Cleanup on shutdown                                      │
└──────────┬──────────────────────────────┬──────────────────┘
           │                              │
    ┌──────▼─────────┐          ┌─────────▼──────────┐
    │  THREAD 2      │          │   THREAD 3         │
    │  ANALYZER      │          │   MANAGER          │
    │  (500ms)       │          │   (100ms)          │
    ├────────────────┤          ├────────────────────┤
    │                │          │                    │
    │ Scanner        │          │ Position           │
    │ • Pull data    │          │ Management:        │
    │ • Analyze      │          │ • Check TP/SL      │
    │ • Detect       │          │ • Scale-out        │
    │   signals      │          │ • Trail stops      │
    │ • Place        │          │                    │
    │   trades       │          │                    │
    └────────────────┘          └────────────────────┘
           │
           │ Shared Data Structures:
           ├─ Executor._positions dict
           ├─ DataPuller (always fresh)
           └─ Journal (append-only)
```

---

## DATA FLOW: MT5 → ANALYSIS → TRADE

```
╔════════════════════════════════════════════════════════════╗
║              LIVE MARKET DATA (MT5 Terminal)              ║
║                                                            ║
║  Ticks (100ms)  +  DOM (200ms)  +  Bars (M1/M5/D1)       ║
╚════════════════════════╤═══════════════════════════════════╝
                         │
                         ▼
╔════════════════════════════════════════════════════════════╗
║                  DATA PULLER (100ms)                       ║
║                                                            ║
║  • Pull trade ticks (buy/sell flags)                       ║
║  • Pull 1-min & 5-min bars                                ║
║  • Pull DOM snapshot (order book)                         ║
║  • Get current bid/ask                                    ║
╚════════════════════════╤═══════════════════════════════════╝
                         │
                         ▼
╔════════════════════════════════════════════════════════════╗
║               ANALYSIS PIPELINE (500ms)                    ║
║                                                            ║
║  1. DELTA ENGINE                                           ║
║     ├─ Compute buy/sell volume per bar                    ║
║     ├─ Detect divergences                                 ║
║     └─ Track cumulative delta                             ║
║                                                            ║
║  2. FOOTPRINT BUILDER                                      ║
║     ├─ Build bid×ask volume matrix                        ║
║     ├─ Detect imbalance stacks                            ║
║     ├─ Detect absorption                                  ║
║     └─ Detect exhaustion                                  ║
║                                                            ║
║  3. VOLUME PROFILE (every 60s)                            ║
║     ├─ Compute POC (point of control)                     ║
║     ├─ Find VAH/VAL (value area)                          ║
║     ├─ Identify HVN/LVN                                   ║
║     └─ Build 5-day composite                              ║
║                                                            ║
║  4. KEY LEVELS (every 60s)                                ║
║     ├─ Find PDH/PDL                                       ║
║     ├─ Find opening range                                 ║
║     ├─ Find VPOC                                          ║
║     └─ Identify session levels                            ║
║                                                            ║
║  5. SIGNAL DETECTION                                       ║
║     ├─ Check all 5 confirmations                          ║
║     ├─ Generate signals (if 3-5 match)                    ║
║     └─ Score confidence 0-100%                            ║
║                                                            ║
║  6. RISK VALIDATION                                        ║
║     ├─ Can we trade? (killzone, daily loss, etc)          ║
║     ├─ Position sizing (1% rule)                          ║
║     ├─ Check R:R ratio (min 1:1.5)                        ║
║     └─ Final entry approval                               ║
╚════════════════════════╤═══════════════════════════════════╝
                         │
                         ▼
╔════════════════════════════════════════════════════════════╗
║               EXECUTOR (Order Placement)                    ║
║                                                            ║
║  ✓ Create ManagedPosition                                 ║
║  ✓ Place market order (or fake in DRY_RUN)               ║
║  ✓ Record entry in journal                                ║
║  ✓ Store SL/TPs for position management                  ║
╚════════════════════════╤═══════════════════════════════════╝
                         │
                         ▼
╔════════════════════════════════════════════════════════════╗
║        POSITION MANAGEMENT (100ms, separate thread)        ║
║                                                            ║
║  For each open position:                                   ║
║  ├─ Check vs TP1 (6 ticks) → Close 50%                   ║
║  ├─ Check vs TP2 (10 ticks) → Close 30%                  ║
║  ├─ Check vs TP3 (16 ticks) → Close 20%                  ║
║  ├─ Trail SL to breakeven after TP1                       ║
║  ├─ Delta-based trailing after TP2                        ║
║  └─ Emergency close if max loss hit                       ║
╚════════════════════════╤═══════════════════════════════════╝
                         │
                         ▼
╔════════════════════════════════════════════════════════════╗
║                   JOURNAL & RESULTS                        ║
║                                                            ║
║  • CSV export: trade_journal.csv                           ║
║  • SQLite: trade_journal.db                               ║
║  • Session summary on shutdown                             ║
║                                                            ║
║  Columns: trade_id, timestamp, symbol, direction,          ║
║           signal, entry/exit prices, volume, P&L,          ║
║           R-multiple, win/loss flag, duration              ║
╚════════════════════════════════════════════════════════════╝
```

---

## MODULE DEPENDENCY MAP

```
                          ┌─────────────┐
                          │  config.py  │
                          │  (ALL params)
                          └──────┬──────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ mt5_connector.py │   │ data_puller.py   │   │ risk_manager.py  │
│                  │   │                  │   │                  │
│ • Connect MT5    │   │ • Fetch ticks    │   │ • Size positions │
│ • Get account    │   │ • Fetch bars     │   │ • Check limits   │
│ • Symbol specs   │   │ • Fetch DOM      │   │ • Validate R:R   │
└────────┬─────────┘   └────────┬─────────┘   └────────┬─────────┘
         │                      │                      │
         └──────────────┬───────┴──────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
   ┌─────────┐   ┌──────────┐   ┌──────────────┐
   │delta.py │   │footprint │   │vol_profile.py
   │         │   │.py       │   │              │
   │ Delta   │   │          │   │ POC/VAH/VAL │
   │ analysis│   │Imbalance │   │ HVN/LVN     │
   └────┬────┘   │Absorption└───┴────┬────────┘
        │        └────────┬──────────┘
        │                 │
        └─────────┬───────┘
                  │
            ┌─────▼──────┐
            │key_levels  │
            │.py         │
            │PDH/PDL/OR  │
            └─────┬──────┘
                  │
                  │
            ┌─────▼──────────────────┐
            │   signals.py           │
            │ (ORCHESTRATOR)         │
            │                        │
            │ • Detect all signals   │
            │ • Validate confluence  │
            │ • Score confidence     │
            └─────┬──────────────────┘
                  │
        ┌─────────┼─────────┐
        │         │         │
        ▼         ▼         ▼
┌────────────┐┌────────────┐┌────────────┐
│ executor   ││ journal.py ││ scanner.py │
│.py         ││            ││            │
│            ││ Log trades ││ Orchestrate
│ Place      ││ CSV + DB   ││ all steps  │
│ orders     ││            ││            │
└─────┬──────┘└────────────┘└────┬───────┘
      │                          │
      └──────────────┬───────────┘
                     │
                ┌────▼──────┐
                │  main.py  │
                │           │
                │Controller │
                │3 threads  │
                └───────────┘
                     │
                     ▼
            ┌─────────────────┐
            │  __main__.py    │
            │  Entry Point    │
            └─────────────────┘
```

---

## MODULE REFERENCE TABLE

| Module | Thread | Frequency | Purpose | Key Classes |
|--------|--------|-----------|---------|-------------|
| **config.py** | All | Static | All parameters | (constants only) |
| **mt5_connector.py** | Main | Init | Connect MT5 | MT5Connector, SymbolSpec |
| **data_puller.py** | Analyzer | 100-500ms | Fetch data | DataPuller, TickData, BarData |
| **delta.py** | Analyzer | 500ms | Delta analysis | DeltaEngine, DeltaBar |
| **footprint.py** | Analyzer | 500ms | Footprint charts | FootprintBuilder, FootprintBar |
| **volume_profile.py** | Analyzer | 60s rebuild | Volume profile | VolumeProfiler, VolumeProfile |
| **key_levels.py** | Analyzer | 60s rebuild | Key levels | KeyLevelBuilder, KeyLevels |
| **signals.py** | Analyzer | 500ms | Signal detection | SignalDetector, Signal |
| **executor.py** | Both | Entry + 100ms | Order management | Executor, ManagedPosition |
| **risk_manager.py** | Analyzer | Per-trade | Risk checks | RiskManager, TradeResult |
| **journal.py** | Analyzer | Per-trade | Trade logging | Journal, TradeRecord |
| **scanner.py** | Analyzer | 500ms | Orchestrate | Scanner |
| **main.py** | Main | Init | Controller | OrderFlowScalper |

---

## SIGNAL DETECTION: 5 CONFIRMATIONS

```
Signal enters at price level X when 3-5 of these are true:

┌─────────────────────────────────────────────────────────────┐
│  CONFIRMATION 1: KEY LEVEL                                  │
│  ├─ Price within ±5 ticks of PDH/PDL                       │
│  ├─ Price within ±5 ticks of VPOC                          │
│  ├─ Price within ±5 ticks of VAH/VAL                       │
│  └─ Price within ±5 ticks of Opening Range                 │
│                                                              │
│  CONFIRMATION 2: ORDER FLOW SIGNAL                          │
│  ├─ Absorption (high vol with price hold)                   │
│  ├─ Imbalance stack (3+ diagonal imbalances)               │
│  ├─ Delta divergence (price high but delta low, etc)       │
│  ├─ Iceberg detection (repeated small fills)               │
│  └─ Exhaustion (declining vol on extension)                │
│                                                              │
│  CONFIRMATION 3: VOLUME PROFILE CONTEXT                     │
│  ├─ Rejection at VAH/VAL                                   │
│  └─ Bounce off VPOC                                        │
│                                                              │
│  CONFIRMATION 4: DELTA CONFIRMATION                         │
│  ├─ Cumulative delta trending in signal direction           │
│  └─ No divergence against signal                            │
│                                                              │
│  CONFIRMATION 5: TAPE (DOM) CONFIRMATION                    │
│  ├─ Order book shows passive support/resistance             │
│  └─ DOM imbalance aligns with signal                        │
│                                                              │
│  ENTRY RULE:                                                │
│  ├─ Need 3 minimum confirmations                            │
│  ├─ More than 3 available = need 4+                         │
│  └─ Confidence = (confirmations_met / total_available) × 100│
└─────────────────────────────────────────────────────────────┘
```

---

## RISK MANAGEMENT RULES

```
┌─────────────────────────────────────────────────────────────┐
│                    POSITION SIZING                           │
├─────────────────────────────────────────────────────────────┤
│  Risk amount = Account balance × 1%                         │
│  Stop distance = 4 ticks beyond absorption zone             │
│  Lots = Risk amount / (Stop ticks × Tick value)            │
│  Round down to nearest volume step, clamp to [min, max]    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  PRE-TRADE CHECKS                           │
├─────────────────────────────────────────────────────────────┤
│  ✓ Consecutive losses < 3 (stop if 3+ in a row)            │
│  ✓ Daily P&L > -3% of balance (stop if hit limit)          │
│  ✓ In killzone hours? (skip if not, unless crypto)         │
│  ✓ In dead zone? (skip if yes — 12:00-14:00 EST)          │
│  ✓ No open positions yet? (never stack)                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                 SCALE-OUT PLAN                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Entry: Market order at key level                           │
│  SL: 4 ticks below absorption zone                          │
│                                                              │
│  50% at TP1 = Entry + 6 ticks  [Early exit]               │
│  30% at TP2 = Entry + 10 ticks [Partial profit]           │
│  20% at TP3 = Entry + 16 ticks [Runner position]          │
│                                                              │
│  After TP1 hit:                                             │
│  └─ Move SL to breakeven (entry price)                     │
│                                                              │
│  After TP2 hit:                                             │
│  └─ Trail remaining 20% using delta reversal               │
│                                                              │
│  Max loss per trade: 4 ticks × account risk = 1% account   │
│  Reward per trade: 6-16 ticks × account risk = 1.5-4% max │
└─────────────────────────────────────────────────────────────┘
```

---

## CONFIGURATION CHECKLIST

```
CRITICAL (Must set before first run):
  ☐ MT5_LOGIN = your account number
  ☐ MT5_PASSWORD = your password
  ☐ MT5_SERVER = broker server name (from MT5)
  ☐ SYMBOL = trading symbol (from Market Watch)
  ☐ IS_CRYPTO = True or False (affects killzone)
  ☐ DRY_RUN = True (for first run!)

IMPORTANT (Tune for your account):
  ☐ RISK_PER_TRADE = 0.01 (1%) or 0.005 (0.5%) if conservative
  ☐ TP1_TICKS, TP2_TICKS, TP3_TICKS = for your symbol volatility
  ☐ STOP_TICKS = absorption zone size for your symbol

ADVANCED (Optional - defaults work):
  ☐ IMBALANCE_RATIO = 3.0 (imbalance threshold)
  ☐ ABSORPTION_VOL_MULTIPLIER = 2.0 (absorption threshold)
  ☐ PROFILE_REBUILD_SECS = 60 (60s profile rebuild)
  ☐ ANALYSIS_INTERVAL_MS = 500 (analysis frequency)

KILLZONE (For forex only):
  ☐ KILLZONES = trading hours (default: London + NY)
  ☐ DEAD_ZONE = avoid hours (default: 12:00-14:00 EST)
```

---

## ERROR RECOVERY FLOW

```
                    Error Occurs
                         │
                         ▼
              Is it recoverable?
                    /         \
                  YES          NO
                   │            │
                   ▼            ▼
             Log & retry    Log & exit
             Continue loop  Graceful shutdown
                             Cleanup
```

---

## TRADE LIFECYCLE

```
1. SIGNAL DETECTED
   └─ Scanner finds 3-5 confirmations at key level

2. RISK CHECK
   ├─ Can we trade? (killzone, daily loss, consecutive loss)
   ├─ Position size calculated (1% rule)
   └─ R:R validated (min 1:1.5)

3. ENTRY
   ├─ Market order placed (or simulated in DRY_RUN)
   ├─ ManagedPosition created
   └─ Logged in journal

4. POSITION MANAGEMENT (100ms loop)
   ├─ Check vs TP1 (6 ticks) → Close 50% if hit
   ├─ Check vs TP2 (10 ticks) → Close 30% if hit
   ├─ Check vs TP3 (16 ticks) → Close 20% if hit
   ├─ Trail SL to breakeven after TP1
   └─ Delta-based trailing after TP2

5. TRADE CLOSED
   ├─ P&L calculated
   ├─ R-multiple calculated
   ├─ Win/loss recorded
   └─ Logged in CSV + SQLite

6. SESSION END
   └─ Print summary:
      ├─ Trades today
      ├─ Win rate
      ├─ Gross P&L
      ├─ Avg winner / Avg loser
      └─ Best/worst trade
```

---

## PERFORMANCE EXPECTATIONS

```
TYPICAL LIVE SESSION (London + NY Open, 6 hours):
├─ Ticks processed: 50,000-100,000
├─ Bars analyzed: 300-500
├─ Signals generated: 50-200
├─ Valid signals (3-5 confirmations): 10-30
├─ Trades placed: 3-8
├─ P&L: -3% to +10% daily (before commission)
└─ Win rate: 55-70%

SYSTEM RESOURCES:
├─ CPU: <20% (mostly idle)
├─ Memory: <200MB
├─ Network: Stable connection (data streaming)
└─ Disk: <10MB logs + journal per day

REQUIRED UPTIME:
├─ MetaTrader 5 terminal: 24/7 running
├─ Python process: During trading hours
└─ System: Stable, minimal restarts
```

---

## FILE SIZES & STRUCTURE

```
/OrderFlow-Scalper
├── Code files: ~1500 lines total
│   ├── main.py (120 lines)
│   ├── scanner.py (400 lines)
│   ├── signals.py (600 lines)
│   ├── Other modules (300 lines)
│   └── ... (25+ total files)
│
├── Documentation: 3500+ lines
│   ├── ARCHITECTURE_MAP.md
│   ├── INSTALLATION_GUIDE.md
│   ├── IMPORT_REFERENCE.md
│   └── This file
│
├── Generated files (per day):
│   ├── order_flow_scalper.log (10-50KB)
│   ├── trade_journal.csv (1-10KB)
│   └── trade_journal.db (100-500KB)
│
└── Configuration:
    └── config.py (1KB, edit once)
```

---

## QUICK REFERENCE: KEY PARAMETERS

| Parameter | Default | Range | Purpose |
|-----------|---------|-------|---------|
| **RISK_PER_TRADE** | 0.01 | 0.005-0.02 | Risk % per trade |
| **MAX_DAILY_LOSS** | 0.03 | 0.02-0.05 | Stop trading at loss % |
| **MAX_CONSECUTIVE_LOSSES** | 3 | 2-5 | Loss streak limit |
| **MIN_RR_RATIO** | 1.5 | 1.2-2.0 | Min reward:risk |
| **TP1_TICKS** | 6 | 3-10 | First TP distance |
| **TP2_TICKS** | 10 | 5-15 | Second TP distance |
| **TP3_TICKS** | 16 | 10-25 | Third TP distance |
| **STOP_TICKS** | 4 | 2-6 | SL distance |
| **IMBALANCE_RATIO** | 3.0 | 2.0-4.0 | Imbalance threshold |
| **ANALYSIS_INTERVAL_MS** | 500 | 250-1000 | Analysis frequency |
| **PROFILE_REBUILD_SECS** | 60 | 30-120 | Profile refresh |
| **DRY_RUN** | True | True/False | Paper vs live |

---

## NEXT STEPS

1. ✅ Read this overview (you're reading it!)
2. ✅ Read INSTALLATION_GUIDE.md for setup
3. ✅ Read ARCHITECTURE_MAP.md for deep understanding
4. ✅ Read IMPORT_REFERENCE.md when coding
5. ✅ Run setup & verification steps
6. ✅ Run dry run for 1-2 trading sessions
7. ✅ Review results before going live

---

**System created for serious traders who understand order flow and risk management.**

*This is not a "set and forget" system — it requires active monitoring and configuration tuning.*

**Good luck! 🎯**
