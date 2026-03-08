# MT5 Order Flow Scalper

**3-Thread Order Flow Scalping System for MetaTrader 5**

A real-time order flow scalping system that uses tick-level data, footprint charts, delta analysis, volume profile, and DOM (Depth of Market) data to detect high-probability scalping entries. Runs on a 3-thread architecture: data polling at 100ms, analysis at 500ms, and position management in parallel.

---

## Architecture

```
+-------------------+
|   MetaTrader 5    |
|  (Ticks + DOM)    |
+--------+----------+
         |
         v
+--------+----------+     Thread 1: Data Poller (100ms)
|    Data Puller     | --> Ticks, DOM snapshots, M1/M5/D1 bars
+--------+----------+
         |
         +----------------------------+
         |                            |
         v                            v
+--------+----------+     +-----------+---------+
|  Volume Profile   |     |    Key Levels       |
|  POC, VAH, VAL    |     |  PDH/PDL, OR,       |
|  HVN, LVN         |     |  VPOC, Sessions      |
+--------+----------+     +-----------+---------+
         |                            |
         +------------+---------------+
                      |
                      v               Thread 2: Analyzer (500ms)
              +-------+-------+
              |    Scanner    |
              | Footprint +   |
              | Delta +       |
              | Signal Detect |
              +-------+-------+
                      |
             Signal (5 confirmations)
                      |
                      v               Thread 3: Executor
              +-------+-------+
              |   Executor    |
              | Scale-out     |
              | Trail/Manage  |
              +-------+-------+
                      |
                      v
              +-------+-------+
              |   Journal     |
              | CSV + SQLite  |
              +---------------+
```

---

## Core Components

### Data Puller (`data_puller.py`)

Pulls live data from MT5 at high frequency:
- **Tick data**: Bid, ask, last, volume, buy/sell flags at 100ms polling
- **DOM snapshots**: Depth of Market (order book) at 200ms
- **OHLCV bars**: M1 (primary), M5 (context), D1 (daily levels)

### Delta Engine (`delta.py`)

Analyzes buying vs selling pressure:
- **Tick delta**: Classifies each tick as buy or sell using trade flags (or heuristic fallback for forex)
- **Cumulative delta**: Running total of buy - sell volume
- **Delta divergence**: Detects when price makes new high but delta doesn't (bearish) or vice versa
- **Delta reversal detection**: Identifies when delta momentum shifts direction

### Footprint Charts (`footprint.py`)

Builds price-volume distribution per bar:
- **Bid/Ask volume at each price level**: Shows where buyers and sellers are active
- **Imbalance detection**: Ask volume > 3x bid volume at a level (or vice versa)
- **Stacked imbalances**: 3+ consecutive price levels with directional imbalance
- **Absorption detection**: High volume at a level with price holding (passive orders absorbing)
- **Exhaustion detection**: Declining volume on price extension

### Volume Profile (`volume_profile.py`)

Computes intraday and composite volume distribution:
- **POC** (Point of Control): Price with highest volume
- **VAH/VAL** (Value Area High/Low): 70% of volume contained
- **HVN** (High Volume Nodes): Volume > 1.5x mean
- **LVN** (Low Volume Nodes): Volume < 0.5x mean
- **Composite profile**: 5-day rolling profile for context

### Key Levels (`key_levels.py`)

Identifies institutional reference levels:
- **PDH/PDL**: Previous Day High/Low
- **PWH/PWL**: Previous Week High/Low
- **Opening Range**: First 30 minutes high/low
- **VPOC**: Volume Point of Control from composite profile
- **Session levels**: Asian range, London open, NY open

### Signal Detector (`signals.py`)

Generates entry signals requiring 3-5 of 5 confirmations:

| # | Confirmation | Description |
|---|-------------|------------|
| 1 | Key Level | Price within 5 ticks of PDH/PDL, VPOC, VAH/VAL, or Opening Range |
| 2 | Order Flow Signal | Absorption, imbalance stack, delta divergence, iceberg, or exhaustion |
| 3 | Volume Profile Context | Rejection at VAH/VAL, bounce off VPOC, LVN breakout |
| 4 | Cumulative Delta | Delta direction supports trade direction |
| 5 | Tape/DOM | DOM shows passive support at the level (bid/ask imbalance) |

### Scanner (`scanner.py`)

Orchestrates the full analysis cycle every 500ms:
1. Pull fresh ticks, bars, and DOM
2. Rebuild key levels and volume profile (every 60s)
3. Check price proximity to key levels
4. Build footprint bars and detect signals
5. Validate confluences (need 3-5 of 5)
6. Pass valid signals to executor

### Executor (`executor.py`)

Handles order placement and position management:
- **Scale-out exits**: 50% at TP1 (6 ticks), 30% at TP2 (10 ticks), 20% at TP3 (16 ticks)
- **Stop loss**: 4 ticks beyond absorption zone
- **Trailing stops**: Dynamic trailing based on delta reversal detection
- **Emergency close**: Closes all positions on shutdown or max loss

### Risk Manager (`risk_manager.py`)

Controls exposure and prevents overtrading:
- **Risk per trade**: 1% of account
- **Daily loss limit**: 3% -- stops trading for the day
- **Consecutive loss limit**: 3 losses in a row -- stops trading
- **Min R:R ratio**: 1.5:1 required for all entries
- **Killzone enforcement**: Only trades during London Open (02:00-05:00 EST) and NY Open (08:30-11:00 EST)
- **Dead zone avoidance**: No trades 12:00-14:00 EST

### Journal (`journal.py`)

Records all trades for review:
- **CSV export**: `trade_journal.csv` with all fields
- **SQLite database**: `trade_journal.db` for querying
- **Session summary**: Printed on shutdown with P&L, win rate, trade count

---

## Installation

### Prerequisites

- Python 3.10+
- MetaTrader 5 terminal running on Windows
- Broker account with tick data access

### Setup

```bash
pip install MetaTrader5 pandas numpy
```

### Configuration

Edit `config.py`:

```python
# Symbol (match your broker's naming)
SYMBOL = "BTCUSDm"
IS_CRYPTO = True       # Set False for forex (enables killzone checks)

# MT5 credentials
MT5_LOGIN = 12345678
MT5_PASSWORD = "your_password"
MT5_SERVER = "YourBroker-Server"

# Risk
RISK_PER_TRADE = 0.01  # 1%
MAX_DAILY_LOSS = 0.03  # 3%
DRY_RUN = True         # True = paper trading, no real orders
```

Key parameters to tune:

| Parameter | Default | Description |
|-----------|---------|------------|
| `IMBALANCE_RATIO` | 3.0 | Min ask/bid ratio for imbalance signal |
| `MIN_CONSECUTIVE_IMBALANCES` | 3 | Stacked imbalances needed |
| `ABSORPTION_VOL_MULTIPLIER` | 2.0 | Volume vs avg for absorption |
| `VOLUME_SPIKE_MULTIPLIER` | 1.5 | Current vs 20-bar avg for spike |
| `DELTA_DIVERGENCE_LOOKBACK` | 20 | Bars for divergence detection |
| `TP1_TICKS` / `TP2_TICKS` / `TP3_TICKS` | 6/10/16 | Take profit distances |
| `STOP_TICKS` | 4 | Stop loss distance |

---

## Usage

```bash
# Start the scalper
python -m order_flow_scalper

# Or from parent directory
python -m order_flow_scalper.main
```

The system will:
1. Connect to MT5 and subscribe to DOM data
2. Print account info and symbol specifications
3. Launch 2 background threads (analyzer + position manager)
4. Main thread waits for Ctrl+C

### Dry Run Mode

Set `DRY_RUN = True` in config to log all signals without placing real orders. Recommended for initial testing.

---

## Results & Output

### Signal Log

```
[09:31:15] [INFO] scanner: SIGNAL DETECTED
  Type: ABSORPTION_LONG at 64250.00
  Confirmations: 4/5 [key_level, absorption, vp_bounce, delta_confirm]
  Entry: 64250.00 | SL: 64246.00 | TP1: 64256.00 | TP2: 64260.00 | TP3: 64266.00
```

### Position Management

```
[09:31:45] [INFO] executor: TP1 HIT - Closed 50% at 64256.00 (+6 ticks)
[09:32:10] [INFO] executor: TP2 HIT - Closed 30% at 64260.00 (+10 ticks)
[09:33:05] [INFO] executor: TRAILING STOP - Closed 20% at 64263.00 (+13 ticks)
```

### Session Summary (on shutdown)

```
============================================================
  ORDER FLOW SCALPER - SESSION SUMMARY
============================================================
  Trades: 8 | Wins: 6 | Losses: 2 | Win Rate: 75.0%
  Gross P&L: $342.50
  Avg Winner: $78.20 | Avg Loser: -$45.10
  Best Trade: +$156.00 | Worst Trade: -$52.00
  Max Consecutive Wins: 4 | Max Consecutive Losses: 1
============================================================
```

### Journal Output

All trades saved to `trade_journal.csv` and `trade_journal.db` with: timestamp, symbol, direction, entry/exit prices, volume, P&L, signal type, confirmations, and duration.

---

## Project Structure

```
order_flow_scalper/
  __init__.py
  __main__.py                      # python -m entry point
  main.py                          # OrderFlowScalper controller
  config.py                        # All configuration parameters
  mt5_connector.py                 # MT5 connection, tick/DOM subscription
  data_puller.py                   # High-frequency tick and bar data
  delta.py                         # Delta engine (buy/sell classification)
  footprint.py                     # Footprint chart builder
  volume_profile.py                # POC, VAH, VAL, HVN, LVN
  key_levels.py                    # PDH/PDL, OR, session levels
  signals.py                       # Signal detection (5 confirmations)
  scanner.py                       # Analysis cycle orchestrator
  executor.py                      # Order placement, scale-out, trailing
  risk_manager.py                  # Daily limits, consecutive loss control
  journal.py                       # CSV + SQLite trade journal
  chart.py                         # Footprint chart visualization
```
