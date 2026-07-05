# Order Flow Scalper - Complete Installation & Setup Manual

**Last Updated:** July 2026  
**Version:** Strategy 1 with Advanced Features (v3+)

---

## TABLE OF CONTENTS

1. [Prerequisites](#prerequisites)
2. [Step 1: Environment Setup](#step-1-environment-setup)
3. [Step 2: Install Dependencies](#step-2-install-dependencies)
4. [Step 3: MetaTrader 5 Setup](#step-3-metatrader-5-setup)
5. [Step 4: Configuration](#step-4-configuration)
6. [Step 5: Verification](#step-5-verification)
7. [Step 6: Running the System](#step-6-running-the-system)
8. [Troubleshooting](#troubleshooting)
9. [Advanced Configuration](#advanced-configuration)

---

## PREREQUISITES

### System Requirements
- **OS**: Windows (MetaTrader 5 runs on Windows)
- **Python**: 3.10 or higher (3.11+ recommended)
- **MetaTrader 5**: Terminal installed and running
- **Disk**: ~500MB free (for code + logs)
- **Internet**: Stable connection for MT5 & data streaming

### Knowledge Requirements
- Basic Python understanding
- Familiarity with trading concepts (entry, exit, stop loss, take profit)
- Comfortable with command line / terminal

### Account Requirements
- Active MetaTrader 5 broker account
- Account credentials (login, password, server)
- Trading account with DOM data available (check with broker)

---

## STEP 1: ENVIRONMENT SETUP

### 1.1 Install Python

**Windows:**
1. Download Python 3.11+ from https://www.python.org/downloads/
2. **IMPORTANT**: Check "Add Python to PATH" during install
3. Verify: Open Command Prompt and run:
   ```bash
   python --version
   python -m pip --version
   ```

**Verify Installation:**
```bash
python --version
# Should print: Python 3.11.x (or higher)

pip --version
# Should print: pip 23.x from ...
```

### 1.2 Create a Project Directory

```bash
# Create directory
mkdir orderflow-scalper-env
cd orderflow-scalper-env

# Clone or extract the repository
git clone https://github.com/KyleBrian/OrderFlow-Scalper.git
cd OrderFlow-Scalper
```

### 1.3 Create a Python Virtual Environment

```bash
# Create venv
python -m venv venv

# Activate venv
# On Windows CMD:
venv\Scripts\activate.bat

# OR on Windows PowerShell:
venv\Scripts\Activate.ps1
# (If you get execution policy error, run: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser)

# On macOS/Linux:
source venv/bin/activate
```

**Verify Activation**: Your command prompt should show `(venv)` prefix.

---

## STEP 2: INSTALL DEPENDENCIES

### 2.1 Core Dependencies

These are **REQUIRED** and must be installed first:

```bash
# Ensure venv is activated (you should see (venv) in your prompt)

# Install core packages
pip install MetaTrader5==5.0.5113
pip install pandas>=2.0.0
pip install numpy>=1.24.0

# Verify installations
python -c "import MetaTrader5; print(f'MetaTrader5 version: {MetaTrader5.version()}')"
python -c "import pandas; print(f'Pandas version: {pandas.__version__}')"
python -c "import numpy; print(f'NumPy version: {numpy.__version__}')"
```

### 2.2 Optional Dependencies (for visualization & charting)

```bash
# For footprint chart visualization (optional)
pip install matplotlib>=3.7.0

# For enhanced data analysis (optional)
pip install scipy>=1.10.0
```

### 2.3 Verify All Imports

Create a test file `test_imports.py`:

```python
#!/usr/bin/env python3
"""Test script to verify all imports work."""

print("Testing core imports...")

try:
    import MetaTrader5 as mt5
    print(f"✓ MetaTrader5: {mt5.version()}")
except Exception as e:
    print(f"✗ MetaTrader5: {e}")

try:
    import pandas as pd
    print(f"✓ Pandas: {pd.__version__}")
except Exception as e:
    print(f"✗ Pandas: {e}")

try:
    import numpy as np
    print(f"✓ NumPy: {np.__version__}")
except Exception as e:
    print(f"✗ NumPy: {e}")

print("\nTesting project imports...")

try:
    from order_flow_scalper import config
    print("✓ config.py")
except Exception as e:
    print(f"✗ config.py: {e}")

try:
    from order_flow_scalper.mt5_connector import MT5Connector
    print("✓ mt5_connector.py")
except Exception as e:
    print(f"✗ mt5_connector.py: {e}")

try:
    from order_flow_scalper.data_puller import DataPuller
    print("✓ data_puller.py")
except Exception as e:
    print(f"✗ data_puller.py: {e}")

try:
    from order_flow_scalper.scanner import Scanner
    print("✓ scanner.py")
except Exception as e:
    print(f"✗ scanner.py: {e}")

try:
    from order_flow_scalper.main import OrderFlowScalper
    print("✓ main.py")
except Exception as e:
    print(f"✗ main.py: {e}")

print("\nAll tests completed!")
```

Run it:
```bash
python test_imports.py
```

Expected output: All lines should show ✓

---

## STEP 3: METATRADER 5 SETUP

### 3.1 MetaTrader 5 Terminal Installation

1. Download MT5 from your broker or https://www.metatrader5.com/
2. Install and launch the terminal
3. Log in with your account credentials
4. Ensure account is authorized (green checkmark in account tree)

### 3.2 Enable DOM Subscription

The system requires **Level 2 / DOM (Depth of Market)** data:

1. In MT5, open **Tools → Options → Expert Advisors**
   - Check "Allow automated trading"
   - Check "Allow DLL imports"
2. In **Tools → Market Watch**, right-click your trading symbol
   - Select **Market Depth** (or **DOM**)
   - This enables DOM snapshot reading via the API

### 3.3 Find Your Account Credentials

You'll need:
- **Login**: Your account number (e.g., `12345678`)
- **Password**: Your MetaTrader password
- **Server**: Broker server name (shown in MT5 bottom-left, e.g., `ICMarkets-MT5`)

Run this quick test to confirm:
```bash
python -c "import MetaTrader5 as mt5; mt5.initialize(); print(mt5.account_info())"
```

Should print account info (not an error).

---

## STEP 4: CONFIGURATION

### 4.1 Edit `config.py`

Open `/OrderFlow-Scalper/config.py` in a text editor (VS Code, Notepad++, etc.):

```python
# ─────────────────────────────────────────────
# MT5 CONNECTION
# ─────────────────────────────────────────────
MT5_PATH: str = ""                    # Leave empty (use default path)
MT5_LOGIN: int = 12345678             # YOUR LOGIN
MT5_PASSWORD: str = "your_password"   # YOUR PASSWORD
MT5_SERVER: str = "ICMarkets-MT5"     # YOUR SERVER (from MT5)
MT5_TIMEOUT: int = 10_000             # Leave as is

# ─────────────────────────────────────────────
# SYMBOL & INSTRUMENT
# ─────────────────────────────────────────────
SYMBOL: str = "BTCUSDm"               # Change to YOUR symbol
IS_CRYPTO: bool = True                # True for crypto, False for forex

# ─────────────────────────────────────────────
# RISK MANAGEMENT (Critical!)
# ─────────────────────────────────────────────
RISK_PER_TRADE: float = 0.01          # 1% per trade (reduce to 0.5% if conservative)
MAX_DAILY_LOSS: float = 0.03          # 3% daily loss limit (stop trading at this loss)
MAX_CONSECUTIVE_LOSSES: int = 3       # Stop trading after 3 losses in a row
MIN_RR_RATIO: float = 1.5             # Minimum 1:1.5 reward-to-risk

# ─────────────────────────────────────────────
# EXECUTION (CRITICAL!)
# ─────────────────────────────────────────────
DRY_RUN: bool = True                  # SET TO FALSE FOR LIVE TRADING
                                      # TRUE = Paper trading (no real orders)

# ─────────────────────────────────────────────
# SCALE-OUT PLAN
# ─────────────────────────────────────────────
TP1_TICKS: int = 6      # First take profit (50% of position)
TP2_TICKS: int = 10     # Second take profit (30% of position)
TP3_TICKS: int = 16     # Third take profit (20% of position)
STOP_TICKS: int = 4     # Stop loss distance from entry
```

### 4.2 Minimum Configuration Checklist

```
☐ MT5_LOGIN = your account number
☐ MT5_PASSWORD = your password (no spaces)
☐ MT5_SERVER = your broker server name
☐ SYMBOL = your trading symbol (from MT5 Market Watch)
☐ IS_CRYPTO = True or False (based on your symbol)
☐ DRY_RUN = True (for first run!)
☐ RISK_PER_TRADE = 0.01 (start conservative)
☐ TP1_TICKS, TP2_TICKS, TP3_TICKS = appropriate for your symbol
☐ MetaTrader 5 terminal is running
☐ You're logged into MT5
```

### 4.3 Advanced Configuration Options

See **Advanced Configuration** section below for:
- Killzone times (when to trade)
- Dead zone avoidance
- Order flow thresholds (imbalance ratio, absorption multiplier)
- Volume profile settings
- Delta divergence lookback
- And more...

---

## STEP 5: VERIFICATION

### 5.1 Connectivity Test

Create `test_connection.py`:

```python
#!/usr/bin/env python3
"""Test MT5 connection before running the system."""

import MetaTrader5 as mt5
from order_flow_scalper import config

print("=" * 60)
print("MT5 CONNECTIVITY TEST")
print("=" * 60)

# Initialize
kwargs = {"timeout": config.MT5_TIMEOUT}
if config.MT5_PATH:
    kwargs["path"] = config.MT5_PATH
if config.MT5_LOGIN:
    kwargs["login"] = config.MT5_LOGIN
    kwargs["password"] = config.MT5_PASSWORD
    kwargs["server"] = config.MT5_SERVER

print(f"\nInitializing MT5 with:")
print(f"  Server: {config.MT5_SERVER}")
print(f"  Login: {config.MT5_LOGIN}")

if not mt5.initialize(**kwargs):
    print(f"✗ FAILED: {mt5.last_error()}")
    print("\nDebugging tips:")
    print("1. Ensure MetaTrader 5 terminal is running")
    print("2. Verify login/password/server in config.py")
    print("3. Check terminal at the bottom-left for server name")
    exit(1)

print("✓ MT5 Initialized")

# Check symbol
if not mt5.symbol_select(config.SYMBOL, True):
    print(f"✗ Cannot select symbol {config.SYMBOL}")
    print(f"   Error: {mt5.last_error()}")
    print(f"\n   Available symbols:")
    symbols = mt5.symbols_get()
    for s in symbols[:10]:  # Show first 10
        print(f"     - {s.name}")
    mt5.shutdown()
    exit(1)

print(f"✓ Symbol {config.SYMBOL} selected")

# Check account
acct = mt5.account_info()
if acct is None:
    print(f"✗ Cannot read account: {mt5.last_error()}")
    mt5.shutdown()
    exit(1)

print(f"✓ Account info:")
print(f"  Balance: {acct.balance} {acct.currency}")
print(f"  Equity: {acct.equity} {acct.currency}")
print(f"  Leverage: 1:{acct.leverage}")

# Check DOM
if not mt5.market_book_add(config.SYMBOL):
    print(f"⚠ DOM not available (broker may not support it)")
    print(f"   System will work without DOM")
else:
    book = mt5.market_book_get(config.SYMBOL)
    print(f"✓ DOM available ({len(book) if book else 0} levels)")
    mt5.market_book_release(config.SYMBOL)

# Shutdown
mt5.shutdown()

print("\n" + "=" * 60)
print("✓ ALL CHECKS PASSED - Ready to run!")
print("=" * 60)
```

Run it:
```bash
python test_connection.py
```

Expected output: All ✓ marks

---

## STEP 6: RUNNING THE SYSTEM

### 6.1 Dry Run (Paper Trading) — RECOMMENDED FIRST

```bash
# Ensure venv is activated
(venv) C:\...> 

# Verify DRY_RUN = True in config.py

# Run the system
python -m order_flow_scalper

# You should see:
# ============================================================
# ORDER FLOW SCALPER  —  Strategy 1
# Symbol: BTCUSDm  |  DRY_RUN: True
# ============================================================
# [INFO] Connected. Spec: ...
# [INFO] Account: balance=... equity=... leverage=...
# [Analyzer] Started
# [Manager] Started
# Threads started. Press Ctrl+C to stop.
```

Let it run for 5-10 minutes to verify:
- No errors in the logs
- Threads are running
- Scanner is detecting/analyzing data

Press **Ctrl+C** to stop (graceful shutdown).

### 6.2 Review Dry Run Results

After shutdown, check:

```bash
# View the log file
type order_flow_scalper.log  # Windows
cat order_flow_scalper.log   # Mac/Linux

# View trade journal
type trade_journal.csv  # Windows
cat trade_journal.csv   # Mac/Linux
```

Expected journal columns:
```
trade_id, opened_at, closed_at, symbol, direction, signal_type, key_level, 
confidence, entry_price, stop_loss, tp1, tp2, tp3, volume, exit_price, pnl, 
r_multiple, is_win, exit_reason, notes
```

### 6.3 Live Trading — ONLY After Successful Dry Run

**CRITICAL STEPS:**

1. **Run several dry run sessions** (at least 1-2 trading sessions)
2. **Review all trades** in the journal
3. **Verify P&L calculations** are correct
4. **Check for any errors** in the log file
5. **Reduce risk** if you're nervous (set `RISK_PER_TRADE = 0.005` for 0.5%)

When confident:

```bash
# EDIT config.py and change:
DRY_RUN: bool = False  # ← SET TO FALSE

# Save and run
python -m order_flow_scalper

# You should see:
# ORDER FLOW SCALPER  —  Strategy 1
# Symbol: BTCUSDm  |  DRY_RUN: False  ← Confirms live mode
```

**NEVER skip dry run!**

---

## TROUBLESHOOTING

### Problem: ModuleNotFoundError: No module named 'order_flow_scalper'

**Solution:**
```bash
# Make sure you're in the right directory
cd OrderFlow-Scalper

# Verify __init__.py exists
ls __init__.py  # Mac/Linux
dir __init__.py # Windows

# If missing, create it:
type nul > __init__.py  # Windows
touch __init__.py       # Mac/Linux

# Run with absolute module path
python -m order_flow_scalper
```

### Problem: ModuleNotFoundError: No module named 'MetaTrader5'

**Solution:**
```bash
# Ensure venv is activated (you should see (venv) prefix)

# Reinstall
pip uninstall MetaTrader5 -y
pip install MetaTrader5==5.0.5113

# Verify
python -c "import MetaTrader5; print(MetaTrader5.version())"
```

### Problem: MT5 Connection Error

**Error:** `MT5 initialize failed` or `MT5 login failed`

**Solution:**
1. Open MetaTrader 5 terminal manually
2. Log in with your credentials
3. Verify the server name (bottom-left of MT5)
4. Update `config.py` with exact server name and credentials
5. Run test_connection.py to debug

### Problem: "Symbol not found" Error

**Error:** `Cannot select symbol BTCUSD`

**Solution:**
1. In MetaTrader 5, go to **Tools → Market Watch**
2. Find your trading symbol (it may be named differently)
   - Bitcoin might be `BTCUSD`, `BTCUSDm`, `BTC.m`, etc.
   - Depends on your broker
3. Update `SYMBOL` in `config.py` to match exactly
4. Ensure it's visible in Market Watch (right-click → Show)

### Problem: No Ticks or Data

**Error:** `No ticks returned for symbol` or `No bars available`

**Solution:**
1. Ensure MetaTrader 5 terminal is **running in foreground** (not minimized)
2. Ensure you're **logged in** to your account
3. Ensure the symbol is **selected in Market Watch**
4. Wait 1-2 minutes for data to populate
5. Check broker supports that symbol/pair

### Problem: DOM Not Available

**Warning:** `DOM not available for symbol`

**Solution:**
1. Some brokers don't provide Level 2 data
2. System will work without DOM (less accurate)
3. Contact your broker to enable DOM/Market Depth
4. Or switch to a broker that provides it

### Problem: Logger Won't Write to File

**Error:** `PermissionError` when writing to log

**Solution:**
```bash
# Ensure file isn't open in another program
# Close the log file if it's open in an editor

# Or run as administrator (Windows)
python -m order_flow_scalper
```

### Problem: Python Not Found

**Error:** `'python' is not recognized as an internal or external command`

**Solution:**
1. Python not installed or not in PATH
2. Reinstall Python and check "Add Python to PATH"
3. Or use full path: `C:\Python311\python.exe -m order_flow_scalper`

---

## ADVANCED CONFIGURATION

### A. Killzone Configuration (When to Trade)

By default, the system trades during **London Open** and **NY Open**:

```python
# In config.py:
KILLZONES: List[Tuple[int, int, int, int]] = [
    (2, 0, 5, 0),     # 02:00 - 05:00 EST (London Open)
    (8, 30, 11, 0),   # 08:30 - 11:00 EST (NY Open)
]

# Only these times allow trading (unless IS_CRYPTO = True)
# Times are in EST (UTC-5)
```

To trade at different times, modify the tuples. Example for London + Asia:
```python
KILLZONES: List[Tuple[int, int, int, int]] = [
    (22, 0, 1, 0),    # 22:00 - 01:00 EST (Tokyo)
    (2, 0, 5, 0),     # 02:00 - 05:00 EST (London)
    (8, 30, 11, 0),   # 08:30 - 11:00 EST (NY)
]
```

### B. Risk Parameters

```python
# Conservative (0.5% risk per trade)
RISK_PER_TRADE: float = 0.005
MAX_DAILY_LOSS: float = 0.02    # 2% stop
MAX_CONSECUTIVE_LOSSES: int = 2
MIN_RR_RATIO: float = 2.0       # Require 1:2 minimum

# Moderate (1% risk per trade)
RISK_PER_TRADE: float = 0.01
MAX_DAILY_LOSS: float = 0.03
MAX_CONSECUTIVE_LOSSES: int = 3
MIN_RR_RATIO: float = 1.5

# Aggressive (2% risk per trade) - NOT RECOMMENDED
RISK_PER_TRADE: float = 0.02
MAX_DAILY_LOSS: float = 0.05
MAX_CONSECUTIVE_LOSSES: int = 5
MIN_RR_RATIO: float = 1.2
```

### C. Order Flow Thresholds

```python
# More sensitive (more signals, more trades)
IMBALANCE_RATIO: float = 2.5              # Lower = easier imbalance
MIN_CONSECUTIVE_IMBALANCES: int = 2
ABSORPTION_VOL_MULTIPLIER: float = 1.5
VOLUME_SPIKE_MULTIPLIER: float = 1.2

# Standard (balanced)
IMBALANCE_RATIO: float = 3.0
MIN_CONSECUTIVE_IMBALANCES: int = 3
ABSORPTION_VOL_MULTIPLIER: float = 2.0
VOLUME_SPIKE_MULTIPLIER: float = 1.5

# Strict (fewer signals, higher quality)
IMBALANCE_RATIO: float = 4.0              # Higher = stricter imbalance
MIN_CONSECUTIVE_IMBALANCES: int = 4
ABSORPTION_VOL_MULTIPLIER: float = 2.5
VOLUME_SPIKE_MULTIPLIER: float = 2.0
```

### D. Take Profit & Stop Loss Distances

For different symbols, adjust tick distances:

```python
# Volatile crypto (larger moves)
TP1_TICKS: int = 10
TP2_TICKS: int = 15
TP3_TICKS: int = 25
STOP_TICKS: int = 6

# Normal forex (medium moves)
TP1_TICKS: int = 6
TP2_TICKS: int = 10
TP3_TICKS: int = 16
STOP_TICKS: int = 4

# Tight scalping (small, fast moves)
TP1_TICKS: int = 3
TP2_TICKS: int = 5
TP3_TICKS: int = 8
STOP_TICKS: int = 2
```

### E. Volume Profile Settings

```python
# Rebuild every 30 seconds (more responsive)
PROFILE_REBUILD_SECS: int = 30

# Rebuild every 120 seconds (less CPU, more stable)
PROFILE_REBUILD_SECS: int = 120

# Change value area percentage (default 70%)
VALUE_AREA_PCT: float = 0.75   # Wider value area
VALUE_AREA_PCT: float = 0.60   # Tighter value area
```

---

## PERFORMANCE MONITORING

### Check CPU/Memory Usage

During a run, you can monitor system resources:

**Windows Task Manager:**
- Press Ctrl+Shift+Esc
- Find "python.exe" process
- CPU should be <20% (mostly idle)
- Memory should be <200MB

**Linux/Mac (top):**
```bash
top -p $(pgrep -f "python -m order_flow_scalper")
```

### Check Log File in Real-Time

```bash
# Windows
Get-Content -Path order_flow_scalper.log -Wait

# Mac/Linux
tail -f order_flow_scalper.log
```

---

## BACKUP & RECOVERY

### Backup Your Configuration

```bash
# Create a backup before making changes
copy config.py config.py.backup  # Windows
cp config.py config.py.backup    # Mac/Linux
```

### Restore from Backup

```bash
copy config.py.backup config.py  # Windows
cp config.py.backup config.py    # Mac/Linux
```

### Backup Your Trade Journal

```bash
# Windows
copy trade_journal.csv trade_journal_backup.csv

# Mac/Linux
cp trade_journal.csv trade_journal_backup.csv
```

---

## NEXT STEPS

1. ✅ Install Python & MetaTrader 5
2. ✅ Install dependencies (MetaTrader5, pandas, numpy)
3. ✅ Configure MT5 credentials in config.py
4. ✅ Run test_connection.py
5. ✅ Run dry run (DRY_RUN = True) for 1-2 trading sessions
6. ✅ Review results in trade_journal.csv
7. ✅ Set DRY_RUN = False only when confident
8. ✅ Monitor live trading and adjust parameters as needed

---

## SUPPORT & RESOURCES

- **Architecture**: See `ARCHITECTURE_MAP.md`
- **Feature Details**: See `NEW_FEATURES_GUIDE.md` 
- **Quick Start**: See `QUICK_START.md`
- **Changelog**: See `CHANGELOG.md`

---

**Happy trading!**

---

**DISCLAIMER**: This system trades based on order flow analysis. Past performance does not guarantee future results. Always use a demo/paper account first. Start with minimal risk (0.5%) and only increase after consistent profitability. Use stop losses on all trades.
