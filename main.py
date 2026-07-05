"""
Main — Entry point for the Order Flow Scalper.
4-thread architecture:
  Thread 1: Data poller (ticks / DOM at high frequency)
  Thread 2: Analyzer / Scanner (runs Strategy 1 pipeline with ALL advanced modules)
  Thread 3: Executor / Position manager with loss prevention
  Thread 4: Performance monitor & chart generation
  
Usage:
    python main.py
    
CRITICAL: Run from the OrderFlow-Scalper directory only!
Uses ABSOLUTE imports (not -m flag) due to folder naming.
"""
import logging
import signal
import sys
import threading
import time
from datetime import datetime, timezone

# ABSOLUTE IMPORTS (required for direct execution from folder)
import config
from mt5_connector import MT5Connector
from data_puller import DataPuller
from risk_manager import RiskManager
from executor import Executor
from journal import Journal
from scanner import Scanner
from session_config import SessionManager
from loss_prevention import LossPreventionValidator
from trade_reasoner import TradeReasoner
from chart import build_strategy_chart

# ── Logging Setup ──────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("order_flow_scalper.log", mode="a"),
    ],
)
log = logging.getLogger("OFScalper")


class OrderFlowScalper:
    """Top-level controller that owns all components and threads."""

    def __init__(self):
        self._shutdown = threading.Event()

        # Core Components (initialised in start())
        self.connector: MT5Connector = None              # type: ignore
        self.puller: DataPuller = None                  # type: ignore
        self.risk: RiskManager = None                   # type: ignore
        self.executor: Executor = None                  # type: ignore
        self.journal: Journal = None                    # type: ignore
        self.scanner: Scanner = None                    # type: ignore
        
        # Advanced Risk/Analysis Components
        self.session_manager: SessionManager = None     # type: ignore
        self.loss_prevention: LossPreventionValidator = None  # type: ignore
        self.trade_reasoner: TradeReasoner = None      # type: ignore

    # ── Start ──────────────────────────────────────
    def start(self):
        log.info("=" * 80)
        log.info("ORDER FLOW SCALPER v3+  —  Advanced Strategy with Full Module Integration")
        log.info("=" * 80)
        log.info("Symbol: %s  |  DRY_RUN: %s  |  Timeframe: %s", 
                 config.SYMBOL, config.DRY_RUN, config.TIMEFRAME_PRIMARY)
        log.info("All modules loaded: Session Mgmt, Loss Prevention, Trade Reasoning, Charting")
        log.info("=" * 80)

        # 1. Connect to MT5
        self.connector = MT5Connector()
        if not self.connector.connect():
            log.critical("MT5 connection failed — aborting")
            return

        spec = self.connector.spec
        log.info("Connected. Spec: %s  digits=%d  point=%.5f  tick_value=%.2f",
                 spec.name, spec.digits, spec.point, spec.tick_value)

        # 2. Subscribe to DOM (required for tape confirmation)
        self.connector.subscribe_dom()
        log.info("DOM subscription enabled")

        # 3. Build CORE components
        self.puller = DataPuller(config.SYMBOL)
        self.risk = RiskManager()
        self.executor = Executor(spec)
        self.journal = Journal()
        log.info("Core components initialized: DataPuller, RiskManager, Executor, Journal")

        # 4. Build ADVANCED components (v3+ features)
        self.session_manager = SessionManager()
        self.loss_prevention = LossPreventionValidator(tick_size=spec.point)
        self.trade_reasoner = TradeReasoner(account_size_usd=config.INITIAL_ACCOUNT_SIZE)
        log.info("Advanced components initialized: SessionMgr, LossPrevention, TradeReasoner")

        # 5. Reset risk for today
        acct = self.connector.get_account_state()
        self.risk.reset_day(acct.balance)
        log.info("Account: balance=%.2f  equity=%.2f  leverage=%d  max_drawdown=%.2f%%",
                 acct.balance, acct.equity, acct.leverage, config.MAX_DAILY_LOSS_PERCENT)

        # 6. Build scanner (orchestrates ALL signal detection pipeline)
        self.scanner = Scanner(
            connector=self.connector,
            puller=self.puller,
            risk_mgr=self.risk,
            executor=self.executor,
            journal=self.journal,
        )
        log.info("Scanner initialized with all analysis modules")

        # 7. Inject advanced validators into scanner (links all systems)
        self.scanner.session_manager = self.session_manager
        self.scanner.loss_prevention = self.loss_prevention
        self.scanner.trade_reasoner = self.trade_reasoner
        log.info("Advanced validators injected into scanner pipeline")

        # 8. Install signal handlers (graceful shutdown)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # 9. Launch threads (4 total: Analysis, Management, Chart Gen, Monitor)
        threads = [
            threading.Thread(target=self._analysis_loop, name="Analyzer", daemon=True),
            threading.Thread(target=self._management_loop, name="Manager", daemon=True),
            threading.Thread(target=self._chart_loop, name="ChartGen", daemon=True),
            threading.Thread(target=self._monitor_loop, name="Monitor", daemon=True),
        ]
        for t in threads:
            t.start()

        log.info("All 4 threads started: Analyzer, Manager, ChartGen, Monitor")
        log.info("Press Ctrl+C to shutdown gracefully")
        log.info("=" * 80)

        # Main thread blocks until shutdown
        try:
            while not self._shutdown.is_set():
                self._shutdown.wait(timeout=1.0)
        except KeyboardInterrupt:
            pass
        finally:
            self._cleanup()

    # ── Analysis Thread ────────────────────────────
    def _analysis_loop(self):
        """
        Runs scanner.run_cycle() at ANALYSIS_INTERVAL.
        
        Pipeline:
          1. Pull fresh ticks & bars
          2. Rebuild volume profile & key levels
          3. Build footprint & delta
          4. Detect ALL signal types (7+ types)
          5. Validate with 5 confirmations + loss prevention
          6. Check session constraints & trade reasoning
          7. Execute if ALL checks pass
        """
        log.info("[Analyzer] Started - Running full Strategy 1 pipeline")
        cycle_count = 0
        while not self._shutdown.is_set():
            try:
                cycle_count += 1
                if cycle_count % 10 == 0:
                    log.info("[Analyzer] Cycle %d - Pipeline: Data→Profile→Footprint→Signals→Validation→Execution", cycle_count)
                self.scanner.run_cycle()
            except Exception as e:
                log.exception("[Analyzer] Error in cycle %d: %s", cycle_count, e)
            self._shutdown.wait(timeout=config.ANALYSIS_INTERVAL_MS / 1000.0)
        log.info("[Analyzer] Stopped after %d cycles", cycle_count)

    # ── Position Management Thread ─────────────────
    def _management_loop(self):
        """
        Checks positions at a faster interval for TP/SL/trailing.
        Integrates loss prevention and risk management.
        """
        log.info("[Manager] Started - Monitoring positions for TP/SL/trailing/loss-prevention")
        management_count = 0
        while not self._shutdown.is_set():
            try:
                management_count += 1
                if self.executor.has_open_positions():
                    tick = self.puller.get_current_tick()
                    if tick:
                        delta_reversing = False
                        for pos in self.executor.get_positions():
                            if self.scanner.delta_engine.is_delta_reversing(pos.direction):
                                delta_reversing = True
                                break
                        
                        # Manage with loss prevention checks
                        self.executor.manage_positions(tick.bid, delta_reversing)
                        
                        # Check daily loss limits
                        acct = self.connector.get_account_state()
                        can_trade, reason = self.risk.can_trade(datetime.now(timezone.utc))
                        if not can_trade and "daily loss" in reason.lower():
                            log.warning("[Manager] Daily loss limit hit: %s", reason)
                            self.executor.emergency_close_all("daily_loss_limit")
                            
                    if management_count % 20 == 0:
                        log.debug("[Manager] Positions checked %d times", management_count)
            except Exception as e:
                log.exception("[Manager] Error in management cycle %d: %s", management_count, e)
            self._shutdown.wait(timeout=config.TICK_POLL_INTERVAL_MS / 1000.0)
        log.info("[Manager] Stopped after %d management cycles", management_count)

    # ── Chart Generation Thread ────────────────────
    def _chart_loop(self):
        """
        Generates interactive HTML charts periodically.
        Shows: candlesticks, volume profile, footprint, delta, signals, key levels.
        """
        log.info("[ChartGen] Started - Generating interactive charts every %d seconds", 
                 getattr(config, 'CHART_GENERATION_INTERVAL_SECS', 300))
        chart_count = 0
        try:
            while not self._shutdown.is_set():
                try:
                    chart_count += 1
                    interval = getattr(config, 'CHART_GENERATION_INTERVAL_SECS', 300)
                    
                    log.info("[ChartGen] Generating chart #%d...", chart_count)
                    try:
                        # Call the build_strategy_chart function directly
                        build_strategy_chart(
                            bar_count=100,
                            output_html="strategy_chart.html",
                            auto_open=False  # Don't auto-open in background thread
                        )
                        log.info("[ChartGen] Chart saved to strategy_chart.html")
                    except Exception as e:
                        log.warning("[ChartGen] Chart generation failed: %s", e)
                    
                    self._shutdown.wait(timeout=interval)
                except Exception as e:
                    log.exception("[ChartGen] Error in chart cycle %d: %s", chart_count, e)
                    self._shutdown.wait(timeout=60)
        finally:
            log.info("[ChartGen] Stopped after %d chart generations", chart_count)

    # ── Performance Monitor Thread ──────────────────
    def _monitor_loop(self):
        """
        Monitors system performance, logs statistics, and reports on bot health.
        """
        log.info("[Monitor] Started - Logging performance metrics every %d seconds", 
                 getattr(config, 'MONITOR_INTERVAL_SECS', 60))
        monitor_count = 0
        try:
            while not self._shutdown.is_set():
                try:
                    monitor_count += 1
                    
                    # Log account state
                    if self.connector:
                        acct = self.connector.get_account_state()
                        log.info("[Monitor] Account: Balance=%.2f USD  Equity=%.2f USD  PnL=%.2f USD (%.1f%%)",
                                 acct.balance, acct.equity, 
                                 acct.equity - acct.balance,
                                 ((acct.equity - acct.balance) / acct.balance * 100) if acct.balance > 0 else 0)
                    
                    # Log position count
                    if self.executor:
                        pos_count = len(self.executor.get_positions()) if self.executor.has_open_positions() else 0
                        log.info("[Monitor] Open Positions: %d  |  Risk Manager: daily_pnl=%.2f%%  max_drawdown=%.2f%%",
                                 pos_count,
                                 getattr(self.risk, 'daily_pnl_percent', 0),
                                 getattr(self.risk, 'max_drawdown_percent', 0))
                    
                    # Log session info
                    if self.session_manager:
                        session = self.session_manager.get_current_session()
                        log.info("[Monitor] Current Session: %s  |  Can Trade: %s",
                                 session.name if session else "NONE",
                                 "YES" if session and session.can_trade else "NO")
                    
                    if monitor_count % 60 == 0:  # Every hour
                        log.info("[Monitor] Statistics: cycles=%d (every %.1fs), threads=4 active",
                                 monitor_count,
                                 getattr(config, 'MONITOR_INTERVAL_SECS', 60))
                    
                    self._shutdown.wait(timeout=getattr(config, 'MONITOR_INTERVAL_SECS', 60))
                except Exception as e:
                    log.exception("[Monitor] Error in monitor cycle %d: %s", monitor_count, e)
                    self._shutdown.wait(timeout=30)
        finally:
            log.info("[Monitor] Stopped after %d monitoring cycles", monitor_count)

    # ── Shutdown ───────────────────────────────────
    def _signal_handler(self, signum, frame):
        log.info("Shutdown signal received (%s)", signum)
        self._shutdown.set()

    def _cleanup(self):
        log.info("=" * 80)
        log.info("GRACEFUL SHUTDOWN INITIATED")
        log.info("=" * 80)

        # 1. Close all open positions
        if self.executor and self.executor.has_open_positions():
            log.info("Closing all open positions...")
            self.executor.emergency_close_all("shutdown")

        # 2. Print final account state
        if self.connector:
            acct = self.connector.get_account_state()
            log.info("Final Account State: Balance=%.2f USD  Equity=%.2f USD  PnL=%.2f USD",
                     acct.balance, acct.equity, acct.equity - acct.balance)

        # 3. Print session summary (trades taken, stats, etc)
        log.info("-" * 80)
        log.info("SESSION SUMMARY")
        log.info("-" * 80)
        if self.journal:
            self.journal.print_summary()

        # 4. Print risk manager final stats
        if self.risk:
            log.info("Risk Manager Final: daily_pnl=%.2f%%  max_drawdown=%.2f%%  trades=%d",
                     getattr(self.risk, 'daily_pnl_percent', 0),
                     getattr(self.risk, 'max_drawdown_percent', 0),
                     getattr(self.risk, 'trade_count', 0))

        # 5. Disconnect MT5
        if self.connector:
            log.info("Disconnecting from MT5...")
            self.connector.disconnect()

        log.info("=" * 80)
        log.info("SHUTDOWN COMPLETE - All resources released")
        log.info("=" * 80)


# ── Entry Point ────────────────────────────────────
def main():
    """
    Entry point for Order Flow Scalper v3+ with full module integration.
    
    IMPORTANT SETUP NOTES:
    =====================
    1. Install all dependencies FIRST:
       pip install MetaTrader5 pandas numpy python-dotenv
    
    2. RUN FROM PROJECT DIRECTORY ONLY:
       cd /path/to/OrderFlow-Scalper
       python main.py
    
    3. DO NOT use: python -m (folder names with spaces break module resolution)
    
    4. Check config.py BEFORE running:
       - Set DRY_RUN = True for paper trading
       - Set correct SYMBOL (e.g., "EURUSD")
       - Set correct MT5 account (login, password, server)
       - Review risk parameters (initial account size, max daily loss, etc)
    
    5. Verify MT5 is running and accepting connections
    
    WHAT GETS LOADED:
    =================
    ✓ MT5 Connection (ticks, bars, DOM, account info)
    ✓ Data Puller (high-frequency tick streaming)
    ✓ 7+ Signal Types (absorption, imbalance, delta, ICT, LDP, etc)
    ✓ Risk Manager (daily limits, position sizing, equity protection)
    ✓ Loss Prevention (7 hard blocks against toxic trades)
    ✓ Session Manager (London, NY, session-aware trading)
    ✓ Trade Reasoner (explains WHY every trade is taken)
    ✓ Chart Generator (interactive TradingView-style HTML charts)
    ✓ Journal (SQLite + CSV trade logging)
    ✓ 4 Threads: Analysis, Management, Chart Gen, Monitor
    
    RUNTIME BEHAVIOR:
    =================
    - Analysis Thread: Runs full signal detection pipeline every ~500ms
    - Management Thread: Checks positions for TP/SL/trailing every ~100ms
    - Chart Thread: Generates chart every 5 minutes
    - Monitor Thread: Logs account stats every 60 seconds
    
    EXPECTED OUTPUT:
    ================
    order_flow_scalper.log - Complete event log
    trades.csv - Trade list
    trades.db - SQLite trade journal
    chart.html - Interactive chart (opens in browser)
    
    TROUBLESHOOTING:
    ================
    If you hit errors, check:
    1. All Python files in same directory as main.py
    2. config.py settings match your MT5 account
    3. MetaTrader5 running with correct server/account
    4. No relative imports (from . import) - all absolute imports now
    5. Sufficient disk space for logs/database
    6. Windows only (MT5 API requires Windows)
    
    Questions? Check INSTALLATION_GUIDE.md in project root.
    """
    scalper = OrderFlowScalper()
    scalper.start()


if __name__ == "__main__":
    main()
