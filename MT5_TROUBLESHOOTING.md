# MT5 Connection Troubleshooting Guide

## Error You're Hitting

```
ERROR mt5_connector: MT5 initialize failed: (-10005, 'IPC timeout')
CRITICAL OFScalper: MT5 connection failed — aborting
```

**Error Code: -10005 = IPC timeout**
This means: Python can't communicate with MetaTrader5

---

## Quick Fix Checklist (Do These First!)

### 1. Is MetaTrader5 Running?
```
✓ Check: Is MT5 window visible on your screen right now?
✓ If NO: Open MetaTrader5, log in, wait for it to fully load
✓ If YES: Continue to next step
```

### 2. Is MT5 Fully Loaded?
```
✓ Check: Can you see quotes and charts in MT5?
✓ Check: Does the status bar at the bottom show "Connected"?
✓ If GRAY status: Wait 30 seconds for MT5 to fully connect
✓ If RED status: Your login/server is wrong
```

### 3. Are Your Account Details Correct?

Edit `config.py` and verify these settings:

```python
# These MUST match your MT5 account exactly
MT5_LOGIN = 123456789      # Your account number (usually 8-9 digits)
MT5_PASSWORD = "password"  # Your password
MT5_SERVER = "ICMarketsSC-Demo"  # Check MT5 window title bar for exact server name
```

**How to find your server name:**
1. Open MetaTrader5
2. Look at the window title bar
3. It shows: `MetaTrader 5 - YourName @ ServerName`
4. Copy the exact server name (case-sensitive!)

---

## Detailed Troubleshooting Steps

### Step 1: Restart MetaTrader5

```
1. Close MetaTrader5 completely (exit the program)
2. Wait 5 seconds
3. Open MetaTrader5 again
4. Let it fully load (wait until "Connected" shows at bottom)
5. Try running the bot again
```

### Step 2: Verify Account Login

```python
# Test in Python console:
import MetaTrader5 as mt5

if mt5.initialize(login=123456789, password="password", server="ICMarketsSC-Demo"):
    print("✓ Connection successful!")
    print("Account:", mt5.account_info())
    mt5.shutdown()
else:
    print("✗ Connection failed")
    print("Error:", mt5.last_error())
```

### Step 3: Check Your config.py

Make sure you're using the RIGHT account:

```python
# ✓ CORRECT format:
MT5_LOGIN = 123456789
MT5_PASSWORD = "myPassword123"
MT5_SERVER = "ICMarketsSC-Demo"

# ✗ WRONG format (common mistakes):
MT5_LOGIN = "123456789"        # Should be INT, not string
MT5_PASSWORD = myPassword      # Should have quotes
MT5_SERVER = "icmarketssс-demo" # Wrong case or special characters
```

### Step 4: Check Symbol Availability

Make sure your symbol exists on your broker:

```python
# In config.py, verify:
SYMBOL = "BTCUSDm"  # Some brokers use BTCUSD, others BTCUSDm, etc

# To check what symbols are available:
# 1. Open MetaTrader5
# 2. Go to View → Market Watch
# 3. Look for your symbol in the list
# 4. If you don't see it, add it (right-click → Add)
```

### Step 5: Enable Algo Trading

MetaTrader5 has security restrictions for automated trading:

```
1. Open MetaTrader5
2. Click Tools → Options
3. Go to Expert Advisors tab
4. Check: "Allow automated trading"
5. Check: "Allow DLL imports"
6. Check: "Allow WebRequests" (if needed)
7. Click OK
8. Restart MetaTrader5
```

### Step 6: Check Windows Firewall

```
1. Windows Defender Firewall → Allow an app through firewall
2. Find: "terminal64.exe" (MetaTrader5)
3. Make sure it's checked for both Private and Public
4. If not there, click "Allow another app" and add it
```

---

## Common Error Codes Explained

| Code | Name | Meaning | Fix |
|------|------|---------|-----|
| -10005 | IPC timeout | Python can't reach MT5 | Restart MT5, check login |
| -10022 | Invalid account | Login/password wrong | Check config.py credentials |
| -10025 | Connection timeout | Network issue | Check internet, restart MT5 |
| -10026 | Connection failed | MT5 not running | Open MetaTrader5 |
| -10027 | Trade timeout | MT5 busy | Wait, try again |

---

## Full Connection Test

Create a file `test_connection.py`:

```python
import MetaTrader5 as mt5
from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, SYMBOL

print("Testing MT5 Connection...")
print(f"  Login: {MT5_LOGIN}")
print(f"  Server: {MT5_SERVER}")
print(f"  Symbol: {SYMBOL}")
print()

# Try to initialize
if mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
    print("✓ Connected to MT5!")
    
    # Get account info
    acct = mt5.account_info()
    print(f"✓ Account: {acct.name}")
    print(f"  Balance: {acct.balance}")
    print(f"  Equity: {acct.equity}")
    
    # Check symbol
    sym = mt5.symbol_info(SYMBOL)
    if sym:
        print(f"✓ Symbol {SYMBOL} found")
        print(f"  Bid: {sym.bid}")
        print(f"  Ask: {sym.ask}")
    else:
        print(f"✗ Symbol {SYMBOL} NOT found on this broker")
        print("  Available symbols in Market Watch:")
        # List first few symbols
        mt5.market_watch_add(SYMBOL)  # Try to add it
    
    mt5.shutdown()
    print("\n✅ ALL TESTS PASSED!")
else:
    print("✗ Failed to connect")
    print(f"Error: {mt5.last_error()}")
```

Run it:
```bash
python test_connection.py
```

---

## Still Not Working? Try These

### Option A: Use Paper Trading Account
Many brokers offer demo accounts. Try switching to those credentials first.

### Option B: Try a Different Symbol
If BTCUSDm doesn't exist on your broker:
```python
SYMBOL = "EURUSD"  # Try a major forex pair
```

### Option C: Check Python Version
```bash
python --version
```
Should be Python 3.8 or higher. If older, update Python.

### Option D: Reinstall MetaTrader5 Library
```bash
pip uninstall MetaTrader5
pip install MetaTrader5
```

### Option E: Restart Your Computer
Sometimes Windows networking gets stuck. A full restart often fixes IPC timeout issues.

---

## When You See "Connected"

Once you see this in your logs:
```
Connected. Spec: EURUSD  digits=5  point=0.00001
```

Then you're ready! The bot will start:
- Pulling live data
- Detecting signals
- Running all 4 threads
- Trading (or paper trading if DRY_RUN=True)

---

## Verification Checklist

Before running the bot again:

- [ ] MetaTrader5 is open and shows "Connected"
- [ ] MT5 login/password/server are correct in config.py
- [ ] Symbol (BTCUSDm or EURUSD) appears in MT5 Market Watch
- [ ] Algo trading is enabled in MT5 (Tools → Options)
- [ ] Windows firewall allows terminal64.exe
- [ ] You can see quotes and charts in MT5

Once all checked: `python main.py` will work!

---

## Still Need Help?

1. Check `order_flow_scalper.log` for detailed error messages
2. Run `test_connection.py` and share the output
3. Check MT5 window title bar for exact server name
4. Verify config.py matches your account exactly
5. Restart both MT5 and your Python terminal

Good luck!
