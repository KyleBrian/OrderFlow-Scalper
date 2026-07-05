"""
MT5 Connector — Connection lifecycle, symbol info, account info.
Handles initialize / login / shutdown and DOM subscription.
"""
import MetaTrader5 as mt5
import logging
from dataclasses import dataclass
from typing import Optional

import config

log = logging.getLogger(__name__)


@dataclass
class SymbolSpec:
    """Essential symbol specifications pulled once on startup."""
    name: str
    digits: int
    point: float          # minimum price change
    tick_size: float      # price step
    tick_value: float     # monetary value of 1 tick move per 1 lot
    volume_min: float     # minimum lot
    volume_max: float     # maximum lot
    volume_step: float    # lot step
    trade_contract_size: float
    spread: int


@dataclass
class AccountState:
    """Snapshot of account metrics for risk calculations."""
    balance: float
    equity: float
    margin: float
    margin_free: float
    leverage: int
    currency: str


class MT5Connector:
    """Manages the MT5 terminal connection."""

    def __init__(self):
        self._connected: bool = False
        self._dom_subscribed: bool = False
        self.symbol_spec: Optional[SymbolSpec] = None
        self.account: Optional[AccountState] = None

    @property
    def spec(self) -> Optional[SymbolSpec]:
        """Alias for symbol_spec — used by scanner/executor/main."""
        return self.symbol_spec

    # ── Connection ─────────────────────────────────
    def connect(self) -> bool:
        """Initialize MT5 terminal and log in."""
        kwargs = {"timeout": config.MT5_TIMEOUT}
        if config.MT5_PATH:
            kwargs["path"] = config.MT5_PATH
        if config.MT5_LOGIN:
            kwargs["login"] = config.MT5_LOGIN
            kwargs["password"] = config.MT5_PASSWORD
            kwargs["server"] = config.MT5_SERVER

        if not mt5.initialize(**kwargs):
            log.error("MT5 initialize failed: %s", mt5.last_error())
            return False

        # Login if credentials supplied but not passed to initialize
        if config.MT5_LOGIN and not kwargs.get("login"):
            if not mt5.login(
                config.MT5_LOGIN,
                password=config.MT5_PASSWORD,
                server=config.MT5_SERVER,
                timeout=config.MT5_TIMEOUT,
            ):
                log.error("MT5 login failed: %s", mt5.last_error())
                mt5.shutdown()
                return False

        ver = mt5.version()
        log.info("MT5 connected — build %s, %s, %s", *ver)
        self._connected = True

        # Ensure symbol is visible in MarketWatch
        if not mt5.symbol_select(config.SYMBOL, True):
            log.error("Cannot select symbol %s: %s", config.SYMBOL, mt5.last_error())
            self.disconnect()
            return False

        # Pull symbol specs & account
        self.symbol_spec = self._load_symbol_spec()
        self.account = self._load_account()
        if self.symbol_spec is None:
            self.disconnect()
            return False

        log.info(
            "Symbol: %s | tick_size=%.5f | tick_value=%.2f | spread=%d",
            self.symbol_spec.name,
            self.symbol_spec.tick_size,
            self.symbol_spec.tick_value,
            self.symbol_spec.spread,
        )
        log.info(
            "Account: balance=%.2f %s | leverage=1:%d",
            self.account.balance,
            self.account.currency,
            self.account.leverage,
        )
        return True

    def disconnect(self):
        """Release DOM subscription and shut down MT5."""
        if self._dom_subscribed:
            mt5.market_book_release(config.SYMBOL)
            self._dom_subscribed = False
            log.info("DOM subscription released for %s", config.SYMBOL)
        if self._connected:
            mt5.shutdown()
            self._connected = False
            log.info("MT5 disconnected.")

    # ── DOM Subscription ───────────────────────────
    def subscribe_dom(self) -> bool:
        """Subscribe to Level 2 / DOM data for the symbol."""
        if mt5.market_book_add(config.SYMBOL):
            self._dom_subscribed = True
            log.info("DOM subscription active for %s", config.SYMBOL)
            return True
        log.warning(
            "DOM not available for %s (broker may not provide it): %s",
            config.SYMBOL,
            mt5.last_error(),
        )
        return False

    # ── Symbol Spec ────────────────────────────────
    def _load_symbol_spec(self) -> Optional[SymbolSpec]:
        info = mt5.symbol_info(config.SYMBOL)
        if info is None:
            log.error("symbol_info(%s) returned None: %s", config.SYMBOL, mt5.last_error())
            return None

        tick_size = info.trade_tick_size if info.trade_tick_size > 0 else info.point
        return SymbolSpec(
            name=info.name,
            digits=info.digits,
            point=info.point,
            tick_size=tick_size,
            tick_value=info.trade_tick_value,
            volume_min=info.volume_min,
            volume_max=info.volume_max,
            volume_step=info.volume_step,
            trade_contract_size=info.trade_contract_size,
            spread=info.spread,
        )

    # ── Account ────────────────────────────────────
    def _load_account(self) -> Optional[AccountState]:
        acc = mt5.account_info()
        if acc is None:
            log.error("account_info() returned None: %s", mt5.last_error())
            return None
        return AccountState(
            balance=acc.balance,
            equity=acc.equity,
            margin=acc.margin,
            margin_free=acc.margin_free,
            leverage=acc.leverage,
            currency=acc.currency,
        )

    def refresh_account(self) -> Optional[AccountState]:
        """Re-pull account state (call before each position-size calc)."""
        self.account = self._load_account()
        return self.account

    def get_account_state(self) -> Optional[AccountState]:
        """Return cached account state, refreshing if needed."""
        if self.account is None:
            self.refresh_account()
        return self.account

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def has_dom(self) -> bool:
        return self._dom_subscribed
