#!/usr/bin/env python3
"""
Verification Script - Check that all 25+ modules are integrated and working
Run this BEFORE starting the bot to ensure everything is set up correctly
"""

import os
import sys

def check_files_exist():
    """Verify all required Python files exist"""
    required_files = [
        # Core
        'main.py', 'config.py', '__init__.py', '__main__.py',
        # Data & Connection
        'mt5_connector.py', 'data_puller.py', 'journal.py',
        # Analysis (7 modules)
        'volume_profile.py', 'key_levels.py', 'footprint.py', 'delta.py',
        'candle_imbalance.py', 'ict_order_blocks.py', 'ldp.py',
        # Signal Detection
        'signals.py',
        # Orchestration
        'scanner.py',
        # Risk & Execution
        'risk_manager.py', 'executor.py', 'session_config.py',
        # Validation
        'loss_prevention.py', 'trade_reasoner.py', 'chart.py'
    ]
    
    print("=" * 80)
    print("STEP 1: Checking required files exist...")
    print("=" * 80)
    
    missing = []
    for fname in required_files:
        if os.path.exists(fname):
            print(f"✅ {fname}")
        else:
            print(f"❌ {fname} - MISSING!")
            missing.append(fname)
    
    if missing:
        print(f"\n❌ Missing {len(missing)} files: {missing}")
        return False
    
    print(f"\n✅ All {len(required_files)} required files found!")
    return True

def check_imports():
    """Verify all modules can be imported"""
    print("\n" + "=" * 80)
    print("STEP 2: Checking all modules import correctly...")
    print("=" * 80)
    
    modules_to_import = [
        'config',
        'mt5_connector', 'data_puller', 'journal',
        'volume_profile', 'key_levels', 'footprint', 'delta',
        'candle_imbalance', 'ict_order_blocks', 'ldp',
        'signals', 'scanner',
        'risk_manager', 'executor', 'session_config',
        'loss_prevention', 'trade_reasoner', 'chart'
    ]
    
    failed = []
    for module_name in modules_to_import:
        try:
            __import__(module_name)
            print(f"✅ import {module_name}")
        except Exception as e:
            print(f"❌ import {module_name} - ERROR: {e}")
            failed.append((module_name, str(e)))
    
    if failed:
        print(f"\n❌ Failed to import {len(failed)} modules:")
        for mod, err in failed:
            print(f"  • {mod}: {err}")
        return False
    
    print(f"\n✅ All {len(modules_to_import)} modules import successfully!")
    return True

def check_relative_imports():
    """Check that no relative imports exist (all should be absolute)"""
    print("\n" + "=" * 80)
    print("STEP 3: Checking for relative imports (should be 0)...")
    print("=" * 80)
    
    py_files = [f for f in os.listdir('.') if f.endswith('.py') and f not in ['verify_bot.py']]
    
    relative_import_files = []
    for fname in py_files:
        with open(fname, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'from . import' in content or 'from ..' in content or content.count('\nfrom .') > 0:
                relative_import_files.append(fname)
    
    if relative_import_files:
        print(f"❌ Found relative imports in {len(relative_import_files)} files:")
        for fname in relative_import_files:
            print(f"  • {fname}")
        return False
    
    print("✅ No relative imports found (all using absolute imports)")
    return True

def check_main_py():
    """Verify main.py imports all critical modules"""
    print("\n" + "=" * 80)
    print("STEP 4: Checking main.py imports all modules...")
    print("=" * 80)
    
    critical_imports = [
        'config',
        'MT5Connector',
        'DataPuller',
        'RiskManager',
        'Executor',
        'Journal',
        'Scanner',
        'SessionManager',
        'LossPreventionValidator',
        'TradeReasoner',
        'ChartGenerator'
    ]
    
    with open('main.py', 'r') as f:
        main_content = f.read()
    
    missing_imports = []
    for imp in critical_imports:
        if imp not in main_content:
            missing_imports.append(imp)
            print(f"❌ {imp} not imported in main.py")
        else:
            print(f"✅ {imp} imported in main.py")
    
    if missing_imports:
        print(f"\n❌ Missing {len(missing_imports)} imports in main.py: {missing_imports}")
        return False
    
    print(f"\n✅ main.py imports all {len(critical_imports)} critical components!")
    return True

def check_threads():
    """Verify main.py creates 4 threads"""
    print("\n" + "=" * 80)
    print("STEP 5: Checking 4 threads are created...")
    print("=" * 80)
    
    threads_expected = [
        '_analysis_loop',
        '_management_loop',
        '_chart_loop',
        '_monitor_loop'
    ]
    
    with open('main.py', 'r') as f:
        main_content = f.read()
    
    missing_threads = []
    for thread in threads_expected:
        if f'target=self.{thread}' in main_content:
            print(f"✅ {thread} thread defined")
        else:
            print(f"❌ {thread} thread NOT found")
            missing_threads.append(thread)
    
    if missing_threads:
        print(f"\n❌ Missing {len(missing_threads)} threads: {missing_threads}")
        return False
    
    print(f"\n✅ All {len(threads_expected)} threads defined!")
    return True

def check_config():
    """Verify config.py has critical settings"""
    print("\n" + "=" * 80)
    print("STEP 6: Checking config.py has critical settings...")
    print("=" * 80)
    
    critical_configs = [
        'MT5_LOGIN',
        'MT5_PASSWORD',
        'MT5_SERVER',
        'SYMBOL',
        'DRY_RUN',
        'INITIAL_ACCOUNT_SIZE',
        'RISK_PER_TRADE',
        'MAX_DAILY_LOSS_PERCENT'
    ]
    
    with open('config.py', 'r') as f:
        config_content = f.read()
    
    missing_configs = []
    for cfg in critical_configs:
        if cfg in config_content:
            print(f"✅ {cfg} defined")
        else:
            print(f"❌ {cfg} NOT defined")
            missing_configs.append(cfg)
    
    if missing_configs:
        print(f"\n⚠️  Missing {len(missing_configs)} configs (may use defaults): {missing_configs}")
        return True  # Not critical
    
    print(f"\n✅ All {len(critical_configs)} critical settings found!")
    return True

def main():
    """Run all verifications"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  ORDER FLOW SCALPER v3+ - VERIFICATION SCRIPT".center(78) + "║")
    print("║" + "  Checking all 25+ modules are integrated correctly".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝")
    print()
    
    checks = [
        ("Files exist", check_files_exist),
        ("Imports work", check_imports),
        ("No relative imports", check_relative_imports),
        ("main.py has all imports", check_main_py),
        ("4 threads defined", check_threads),
        ("Config has settings", check_config),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ Error in {name}: {e}")
            results.append((name, False))
    
    # Print summary
    print("\n" + "=" * 80)
    print("FINAL VERIFICATION SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print("=" * 80)
    
    if passed == total:
        print(f"\n✅ ✅ ✅  ALL CHECKS PASSED ({passed}/{total})  ✅ ✅ ✅")
        print("\nYour bot is ready to run!")
        print("Next steps:")
        print("  1. Edit config.py with your MT5 account details")
        print("  2. Run: python main.py")
        print("  3. Monitor: tail -f order_flow_scalper.log")
        return 0
    else:
        print(f"\n❌ Some checks failed ({passed}/{total} passed)")
        print("\nPlease fix the issues above before running the bot")
        return 1

if __name__ == "__main__":
    sys.exit(main())
