"""
Main — Entry point for the Order Flow Scalper.
3-thread architecture:
  Thread 1: Data poller (ticks / DOM at high frequency)
  Thread 2: Analyzer / Scanner (runs Strategy 1 pipeline)
  Thread 3: Executor / Position manager
  
Usage:
    python -m order_flow_scalper.main
"""
import logging
import signal
import sys
import threading
import time
from datetime import datetime, timezone

from . import config
from .mt5_connector import MT5Connector
from .data_puller import DataPuller
from .risk_manager import RiskManager
from .executor import Executor
from .journal import Journal
from .scanner import Scanner

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

        # Components (initialised in start())
        self.connector: MT5Connector = None       # type: ignore
        self.puller: DataPuller = None             # type: ignore
        self.risk: RiskManager = None              # type: ignore
        self.executor: Executor = None             # type: ignore
        self.journal: Journal = None               # type: ignore
        self.scanner: Scanner = None               # type: ignore

    # ── Start ──────────────────────────────────────
    def start(self):
        log.info("=" * 60)
        log.info("ORDER FLOW SCALPER  —  Strategy 1")
        log.info("Symbol: %s  |  DRY_RUN: %s", config.SYMBOL, config.DRY_RUN)
        log.info("=" * 60)

        # 1. Connect to MT5
        self.connector = MT5Connector()
        if not self.connector.connect():
            log.critical("MT5 connection failed — aborting")
            return

        spec = self.connector.spec
        log.info("Connected. Spec: %s  digits=%d  point=%.5f  tick_value=%.2f",
                 spec.name, spec.digits, spec.point, spec.tick_value)

        # 2. Subscribe to DOM
        self.connector.subscribe_dom()

        # 3. Build components
        self.puller = DataPuller(config.SYMBOL)
        self.risk = RiskManager()
        self.executor = Executor(spec)
        self.journal = Journal()

        # Reset risk for today
        acct = self.connector.get_account_state()
        self.risk.reset_day(acct.balance)
        log.info("Account: balance=%.2f  equity=%.2f  leverage=%d",
                 acct.balance, acct.equity, acct.leverage)

        # 4. Build scanner
        self.scanner = Scanner(
            connector=self.connector,
            puller=self.puller,
            risk_mgr=self.risk,
            executor=self.executor,
            journal=self.journal,
        )

        # 5. Install signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # 6. Launch threads
        threads = [
            threading.Thread(target=self._analysis_loop, name="Analyzer", daemon=True),
            threading.Thread(target=self._management_loop, name="Manager", daemon=True),
        ]
        for t in threads:
            t.start()

        log.info("Threads started. Press Ctrl+C to stop.")

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
        """Runs scanner.run_cycle() at ANALYSIS_INTERVAL."""
        log.info("[Analyzer] Started")
        while not self._shutdown.is_set():
            try:
                self.scanner.run_cycle()
            except Exception as e:
                log.exception("[Analyzer] Error: %s", e)
            self._shutdown.wait(timeout=config.ANALYSIS_INTERVAL_MS / 1000.0)
        log.info("[Analyzer] Stopped")

    # ── Position Management Thread ─────────────────
    def _management_loop(self):
        """Checks positions at a faster interval for TP/trailing."""
        log.info("[Manager] Started")
        while not self._shutdown.is_set():
            try:
                if self.executor.has_open_positions():
                    tick = self.puller.get_current_tick()
                    if tick:
                        from .delta import DeltaEngine
                        delta_reversing = False
                        for pos in self.executor.get_positions():
                            if self.scanner.delta_engine.is_delta_reversing(pos.direction):
                                delta_reversing = True
                                break
                        self.executor.manage_positions(tick.bid, delta_reversing)
            except Exception as e:
                log.exception("[Manager] Error: %s", e)
            self._shutdown.wait(timeout=config.TICK_POLL_INTERVAL_MS / 1000.0)
        log.info("[Manager] Stopped")

    # ── Shutdown ───────────────────────────────────
    def _signal_handler(self, signum, frame):
        log.info("Shutdown signal received (%s)", signum)
        self._shutdown.set()

    def _cleanup(self):
        log.info("Shutting down...")

        # Close all positions
        if self.executor and self.executor.has_open_positions():
            self.executor.emergency_close_all("shutdown")

        # Print session summary
        if self.journal:
            self.journal.print_summary()

        # Disconnect MT5
        if self.connector:
            self.connector.disconnect()

        log.info("Shutdown complete.")


# ── Entry Point ────────────────────────────────────
def main():
    scalper = OrderFlowScalper()
    scalper.start()


if __name__ == "__main__":
    main()
