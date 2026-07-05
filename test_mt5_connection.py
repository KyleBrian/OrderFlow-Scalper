#!/usr/bin/env python3
"""
Test MT5 Connection - Diagnoses connection issues

Usage:
    python test_mt5_connection.py
"""

import sys

print("=" * 80)
print("MT5 CONNECTION DIAGNOSTIC TEST")
print("=" * 80)
print()

# Step 1: Check if MetaTrader5 is installed
print("Step 1: Checking if MetaTrader5 library is installed...")
try:
    import MetaTrader5 as mt5
    print("  ✓ MetaTrader5 library found")
except ImportError:
    print("  ✗ MetaTrader5 library NOT installed")
    print("  Fix: pip install MetaTrader5")
    sys.exit(1)

# Step 2: Load config
print("\nStep 2: Loading configuration...")
try:
    import config
    print(f"  ✓ Config loaded")
    print(f"    Login: {config.MT5_LOGIN}")
    print(f"    Server: {config.MT5_SERVER}")
    print(f"    Symbol: {config.SYMBOL}")
except Exception as e:
    print(f"  ✗ Config error: {e}")
    sys.exit(1)

# Step 3: Check if MetaTrader5 is running
print("\nStep 2: Checking if MetaTrader5 is running...")
try:
    # Try to initialize - this will work only if MT5 is open
    if mt5.initialize(login=config.MT5_LOGIN, password=config.MT5_PASSWORD, server=config.MT5_SERVER):
        print("  ✓ MetaTrader5 is running and accessible!")
        
        # Step 4: Get account info
        print("\nStep 4: Retrieving account information...")
        acct = mt5.account_info()
        if acct:
            print(f"  ✓ Account found")
            print(f"    Name: {acct.name}")
            print(f"    Balance: {acct.balance} USD")
            print(f"    Equity: {acct.equity} USD")
            print(f"    Leverage: {acct.leverage}x")
        else:
            print(f"  ✗ Could not retrieve account info")
        
        # Step 5: Check symbol
        print(f"\nStep 5: Checking symbol '{config.SYMBOL}'...")
        sym = mt5.symbol_info(config.SYMBOL)
        if sym:
            print(f"  ✓ Symbol found on broker")
            print(f"    Bid: {sym.bid}")
            print(f"    Ask: {sym.ask}")
            print(f"    Spread: {sym.ask - sym.bid}")
            print(f"    Point: {sym.point}")
            print(f"    Digits: {sym.digits}")
        else:
            print(f"  ✗ Symbol '{config.SYMBOL}' NOT found on this broker")
            print(f"  ⚠ This might be the issue!")
            print(f"  Fix:")
            print(f"    1. Open MetaTrader5")
            print(f"    2. Go to View → Market Watch")
            print(f"    3. Right-click and 'Add' the symbol")
            print(f"    OR")
            print(f"    Change SYMBOL in config.py to a symbol that exists")
        
        # Step 6: Try to get bars
        print(f"\nStep 6: Attempting to retrieve recent bars...")
        bars = mt5.copy_rates_from_pos(config.SYMBOL, config.TIMEFRAME_PRIMARY, 0, 10)
        if bars is not None and len(bars) > 0:
            print(f"  ✓ Retrieved {len(bars)} bars")
            print(f"    Most recent close: {bars[-1][4]}")
        else:
            print(f"  ⚠ Could not retrieve bars (might be normal if symbol hasn't traded)")
        
        mt5.shutdown()
        
        print("\n" + "=" * 80)
        print("✅ CONNECTION TEST PASSED - Bot should work!")
        print("=" * 80)
        print("\nRun: python main.py")
        
    else:
        # MT5 not running or connection failed
        error = mt5.last_error()
        print(f"  ✗ Failed to connect to MetaTrader5")
        print(f"    Error Code: {error[0]}")
        print(f"    Error Message: {error[1]}")
        print()
        
        # Provide diagnosis based on error code
        if error[0] == -10005:
            print("  ⚠ Error -10005: IPC Timeout")
            print("    Cause: MetaTrader5 is not running or not responding")
            print("    Fix:")
            print("      1. Make sure MetaTrader5 is OPEN on your screen")
            print("      2. Wait for MT5 to fully load (watch for 'Connected' message)")
            print("      3. Go to View → Market Watch to see available symbols")
            print("      4. Try again: python test_mt5_connection.py")
        elif error[0] == -10022:
            print("  ⚠ Error -10022: Invalid Account")
            print("    Cause: Login, password, or server is wrong")
            print("    Fix:")
            print("      1. Check config.py - verify these values match exactly:")
            print(f"         MT5_LOGIN = {config.MT5_LOGIN}")
            print(f"         MT5_PASSWORD = {config.MT5_PASSWORD}")
            print(f"         MT5_SERVER = {config.MT5_SERVER}")
            print("      2. Look at MT5 window title bar for correct server name")
            print("      3. Check your login credentials are correct")
            print("      4. Try again: python test_mt5_connection.py")
        else:
            print(f"  ⚠ Error {error[0]}: {error[1]}")
            print("    Fix:")
            print("      1. Restart MetaTrader5")
            print("      2. Check your internet connection")
            print("      3. Verify login credentials in config.py")
            print("      4. Try again: python test_mt5_connection.py")
        
        print("\n" + "=" * 80)
        print("❌ CONNECTION TEST FAILED")
        print("=" * 80)
        sys.exit(1)

except Exception as e:
    print(f"  ✗ Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
