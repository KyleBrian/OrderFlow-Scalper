"""
Signals Detector — Classify order flow signals from Strategy 1, Step 4.
Absorption, Imbalance Stacking, Delta Divergence, Iceberg Detection, 
Candle Imbalance (CRT), and ICT Order Blocks.
"""
import numpy as np
import pandas as pd
import logging
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

import config
from footprint import FootprintBar, FootprintBuilder, ImbalanceStack
from delta import DeltaEngine, Divergence
from key_levels import KeyLevels
from data_puller import DOMSnapshot
from candle_imbalance import CandleImbalanceDetector, CandleImbalance, ImbalanceDirection
from ict_order_blocks import OrderBlockDetector, OrderBlock, OrderBlockType
from ldp import LiquidityDeltaProfiler, LDPSignalType
from session_config import SessionManager
from loss_prevention import LossPreventionValidator
from trade_reasoner import TradeReasoner

log = logging.getLogger(__name__)


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
    """A detected order flow signal."""
    signal_type: SignalType
    direction: str           # 'long' or 'short'
    key_level: float         # the level this signal was detected at
    confidence: float        # 0.0 - 1.0 (higher = stronger)
    bar_time: pd.Timestamp
    details: dict = field(default_factory=dict)

    def __str__(self):
        return (
            f"[{self.signal_type.value}] {self.direction.upper()} "
            f"at {self.key_level:.2f} (conf={self.confidence:.0%}) "
            f"@ {self.bar_time}"
        )


class SignalDetector:
    """
    Runs all signal detectors and classifies the best signal.
    Maps to Strategy 1, Step 3-4 (Read Order Flow → Signal Classification).
    """

    def __init__(
        self,
        footprint_builder: FootprintBuilder,
        delta_engine: DeltaEngine,
        tick_size: float,
        account_size_usd: float = 100.0,
    ):
        self.fp_builder = footprint_builder
        self.delta_engine = delta_engine
        self.tick_size = tick_size
        self.candle_imbalance_detector = CandleImbalanceDetector(tick_size)
        self.order_block_detector = OrderBlockDetector(tick_size)
        self.ldp = LiquidityDeltaProfiler(tick_size=tick_size)
        self.loss_prevention = LossPreventionValidator(tick_size=tick_size)
        self.trade_reasoner = TradeReasoner(account_size_usd=account_size_usd)

    def scan_all(
        self,
        fp_bars: List[FootprintBar],
        key_levels: KeyLevels,
        current_price: float,
        tick_df: pd.DataFrame = None,
        dom: DOMSnapshot = None,
    ) -> List[Signal]:
        """
        Run all detectors on recent footprint bars near key levels.
        Returns all detected signals, sorted by confidence descending.
        """
        signals: List[Signal] = []
        proximity = config.PROXIMITY_TICKS * self.tick_size

        # Only analyze bars near key levels
        nearby_levels = key_levels.levels_within(current_price, proximity)
        if not nearby_levels:
            return []

        # Take the last few bars for analysis
        recent_bars = fp_bars[-5:] if len(fp_bars) > 5 else fp_bars

        for fp_bar in recent_bars:
            for level in nearby_levels:
                # ── 1. Absorption ──
                absorption = self._detect_absorption(fp_bar, level)
                if absorption:
                    signals.append(absorption)

                # ── 2. Imbalance Stacking ──
                imbalance_signals = self._detect_imbalance_stacking(fp_bar, level)
                signals.extend(imbalance_signals)

            # ── 3. Exhaustion ──
            exhaustion = self._detect_exhaustion(fp_bar, nearby_levels)
            if exhaustion:
                signals.append(exhaustion)

        # ── 4. Delta Divergence (across multiple bars) ──
        divergence_signals = self._detect_delta_divergence(nearby_levels)
        signals.extend(divergence_signals)

        # ── 5. Iceberg Detection (from tick data) ──
        if tick_df is not None:
            iceberg_signals = self._detect_iceberg(tick_df, nearby_levels)
            signals.extend(iceberg_signals)

        # ── 6. Candle Imbalance Detection (CRT sniper setups) ──
        imbalance_signals = self._detect_candle_imbalances(fp_bars, nearby_levels)
        signals.extend(imbalance_signals)

        # ── 7. ICT Order Block Detection ──
        order_block_signals = self._detect_order_blocks(fp_bars, current_price, nearby_levels)
        signals.extend(order_block_signals)

        # ── 8. LDP (Liquidity Delta Profiler) Signals ──
        from datetime import datetime
        ldp_signals = self._detect_ldp_signals(fp_bars, nearby_levels, datetime.utcnow())
        signals.extend(ldp_signals)

        # ════════════════════════════════════════════════════════════
        # SESSION-BASED CONFIDENCE BOOST (CRITICAL)
        # ════════════════════════════════════════════════════════════
        # FIRST: Check if we can trade in this session
        # If NO (Asia/Dead Zone), return empty signal list immediately
        can_trade = SessionManager.can_trade_now()
        if not can_trade:
            log.debug(f"Session blocked: {SessionManager.get_session_name()}. No signals allowed.")
            return []

        # SECOND: Apply session multiplier to all signals
        for signal in signals:
            base_conf = signal.confidence
            boosted_conf = SessionManager.apply_session_boost(base_conf)
            signal.confidence = boosted_conf
            
            if signal.confidence == 0.0:
                # HARD BLOCK - remove this signal
                signals.remove(signal)

        # THIRD: Run loss prevention validator on remaining signals
        filtered_signals = []
        for signal in signals:
            result = self.loss_prevention.validate(signal, bar_index=len(fp_bars) - 1, bars=fp_bars)
            
            if result.passed:
                # Add loss prevention details to signal
                signal.details["loss_prevention"] = result.filters_status
                filtered_signals.append(signal)
            else:
                log.debug(f"Signal blocked by loss prevention: {result.reason}")

        signals = filtered_signals

        # Sort by confidence (session-boosted)
        signals.sort(key=lambda s: s.confidence, reverse=True)
        return signals

    def classify_best_signal(
        self,
        fp_bars: List[FootprintBar],
        key_levels: KeyLevels,
        current_price: float,
        tick_df: pd.DataFrame = None,
        dom: DOMSnapshot = None,
    ) -> Optional[Signal]:
        """
        Run all detectors and return the single best signal, or None.
        This is the entry point for the scanner.
        """
        signals = self.scan_all(fp_bars, key_levels, current_price, tick_df, dom)
        if not signals:
            return None

        best = signals[0]
        log.info("Best signal: %s", best)
        return best

    # ── Absorption Detector ────────────────────────
    def _detect_absorption(self, fp_bar: FootprintBar, level: float) -> Optional[Signal]:
        result = self.fp_builder.detect_absorption(fp_bar, level)
        if result is None:
            return None

        direction = "long" if result["direction"] == "bullish" else "short"
        confidence = min(result["absorbed_vol"] / (config.ABSORPTION_VOL_MULTIPLIER * 100), 1.0)

        return Signal(
            signal_type=SignalType.ABSORPTION,
            direction=direction,
            key_level=level,
            confidence=confidence,
            bar_time=fp_bar.bar_time,
            details=result,
        )

    # ── Imbalance Stacking Detector ────────────────
    def _detect_imbalance_stacking(
        self, fp_bar: FootprintBar, level: float,
    ) -> List[Signal]:
        stacks = self.fp_builder.find_imbalance_stacks(fp_bar)
        signals = []
        for stack in stacks:
            if not stack.is_significant:
                continue

            direction = "long" if stack.direction == "bullish" else "short"
            # Confidence scales with number of consecutive imbalances
            confidence = min(stack.count / 6.0, 1.0)

            signals.append(Signal(
                signal_type=SignalType.IMBALANCE_STACK,
                direction=direction,
                key_level=level,
                confidence=confidence,
                bar_time=fp_bar.bar_time,
                details={
                    "count": stack.count,
                    "direction": stack.direction,
                    "avg_ratio": np.mean([imb.ratio for imb in stack.imbalances]),
                },
            ))
        return signals

    # ── Delta Divergence Detector ──────────────────
    def _detect_delta_divergence(self, nearby_levels: List[float]) -> List[Signal]:
        divergences = self.delta_engine.detect_divergences()
        signals = []
        for div in divergences:
            # Check if the divergence swing point is near a key level
            nearest_level = None
            min_dist = float("inf")
            for level in nearby_levels:
                dist = abs(div.price_swing2 - level)
                if dist < min_dist:
                    min_dist = dist
                    nearest_level = level

            if nearest_level is None:
                continue

            direction = "long" if div.direction == "bullish" else "short"

            signals.append(Signal(
                signal_type=SignalType.DELTA_DIVERGENCE,
                direction=direction,
                key_level=nearest_level,
                confidence=div.strength,
                bar_time=div.bar_time,
                details={
                    "price_swing1": div.price_swing1,
                    "price_swing2": div.price_swing2,
                    "delta_swing1": div.delta_swing1,
                    "delta_swing2": div.delta_swing2,
                },
            ))
        return signals

    # ── Exhaustion Detector ────────────────────────
    def _detect_exhaustion(
        self, fp_bar: FootprintBar, nearby_levels: List[float],
    ) -> Optional[Signal]:
        result = self.fp_builder.detect_exhaustion(fp_bar)
        if result is None:
            return None

        # Find nearest level
        check_price = fp_bar.bar_high if "bearish" in result["direction"] else fp_bar.bar_low
        nearest = min(nearby_levels, key=lambda lv: abs(lv - check_price), default=None)
        if nearest is None:
            return None

        direction = "short" if "bearish" in result["direction"] else "long"
        confidence = 1.0 - result["delta_ratio"]  # lower delta_ratio = stronger exhaustion

        return Signal(
            signal_type=SignalType.EXHAUSTION,
            direction=direction,
            key_level=nearest,
            confidence=confidence * 0.7,  # exhaustion alone is moderate
            bar_time=fp_bar.bar_time,
            details=result,
        )

    # ── Iceberg Detector (from raw ticks) ──────────
    def _detect_iceberg(
        self, tick_df: pd.DataFrame, nearby_levels: List[float],
    ) -> List[Signal]:
        """
        Detect iceberg orders: repeated small fills at the same price.
        Pattern: 10+ ticks at same price, consistent volume (±20%),
        total volume > 5× individual clip size.
        """
        signals = []
        if tick_df.empty:
            return signals

        # Only consider trade ticks with volume
        trades = tick_df[(tick_df["volume_real"] > 0)].copy()
        if trades.empty:
            return signals

        # Use 'last' price; fallback to mid
        price_col = "last"
        if (trades[price_col] <= 0).all():
            trades[price_col] = (trades["bid"] + trades["ask"]) / 2

        for level in nearby_levels:
            tol = config.PROXIMITY_TICKS * self.tick_size
            level_ticks = trades[abs(trades[price_col] - level) <= tol]

            if len(level_ticks) < config.ICEBERG_MIN_REPEATS:
                continue

            volumes = level_ticks["volume_real"].values
            median_vol = np.median(volumes)
            if median_vol <= 0:
                continue

            # Check consistency: most fills within ±tolerance of median
            within_tolerance = np.abs(volumes - median_vol) / median_vol < config.ICEBERG_VOL_TOLERANCE
            consistent_pct = within_tolerance.mean()

            total_vol = volumes.sum()
            ratio = total_vol / median_vol

            if consistent_pct > 0.6 and ratio > config.ICEBERG_TOTAL_VS_DISPLAY:
                # Determine direction from flags
                buy_count = level_ticks["is_buy"].sum()
                sell_count = level_ticks["is_sell"].sum()
                direction = "long" if buy_count > sell_count else "short"

                confidence = min(consistent_pct * (ratio / 10.0), 1.0)

                signals.append(Signal(
                    signal_type=SignalType.ICEBERG,
                    direction=direction,
                    key_level=level,
                    confidence=confidence,
                    bar_time=pd.Timestamp(level_ticks["datetime"].iloc[-1]),
                    details={
                        "fill_count": len(level_ticks),
                        "median_clip": median_vol,
                        "total_vol": total_vol,
                        "ratio": ratio,
                        "consistency": consistent_pct,
                    },
                ))

        return signals

    # ── Candle Imbalance Detector (CRT) ────────────
    def _detect_candle_imbalances(
        self, fp_bars: List[FootprintBar], nearby_levels: List[float],
    ) -> List[Signal]:
        """
        Detect CRT candle imbalance patterns for sniper entries.
        High probability setup: volume on one side, close on opposite side.
        """
        signals = []
        recent_bars = fp_bars[-5:] if len(fp_bars) > 5 else fp_bars

        for fp_bar in recent_bars:
            imbalance = self.candle_imbalance_detector.detect(fp_bar, fp_bars)
            if not imbalance:
                continue

            # Check if imbalance is near a key level (confluence boost)
            nearest_level = min(
                nearby_levels,
                key=lambda lv: abs(lv - imbalance.mid),
                default=imbalance.mid,
            )

            direction = "long" if imbalance.direction == ImbalanceDirection.BULLISH else "short"
            confidence = imbalance.imbalance_strength * 0.9

            signals.append(Signal(
                signal_type=SignalType.CANDLE_IMBALANCE,
                direction=direction,
                key_level=nearest_level,
                confidence=confidence,
                bar_time=fp_bar.bar_time,
                details={
                    "entry_level": imbalance.entry_level,
                    "stop_loss": imbalance.stop_loss,
                    "target_ratio": imbalance.target_ratio,
                    "volume_ratio": imbalance.volume_ratio,
                    "candle_high": imbalance.details.get("candle_high"),
                    "candle_low": imbalance.details.get("candle_low"),
                },
            ))

        return signals

    # ── ICT Order Block Detector ───────────────────
    def _detect_order_blocks(
        self, fp_bars: List[FootprintBar], current_price: float, nearby_levels: List[float],
    ) -> List[Signal]:
        """
        Detect ICT order blocks (smart money accumulation/distribution zones).
        These are the zones where institutions accumulate before breakouts.
        """
        signals = []

        # Scan for order blocks in recent history
        order_blocks = self.order_block_detector.detect_order_blocks(fp_bars, lookback=20)
        if not order_blocks:
            return signals

        # Find blocks being tested near current price
        triggered_blocks = self.order_block_detector.find_triggered_blocks(
            current_price, order_blocks, proximity_ticks=10
        )

        for ob in triggered_blocks:
            # Determine entry direction based on block type
            direction = "long" if ob.block_type == OrderBlockType.ACCUMULATION else "short"

            # Confidence scales with block strength and how fresh it is
            # Fresher blocks (fewer bars since breakout) = higher confidence
            freshness = max(0, 1.0 - (ob.breakout_bars / 50.0))
            confidence = (ob.strength * 0.8) + (freshness * 0.2)

            signals.append(Signal(
                signal_type=SignalType.ORDER_BLOCK,
                direction=direction,
                key_level=ob.mid,
                confidence=min(confidence, 1.0),
                bar_time=ob.breakout_time,
                details={
                    "block_high": ob.high,
                    "block_low": ob.low,
                    "block_type": ob.block_type.value,
                    "strength": ob.strength,
                    "formed_at": str(ob.formed_at),
                    "consolidation_bars": ob.consolidation_bars,
                    "breakout_bars": ob.breakout_bars,
                    "volume_in_block": ob.volume_in_block,
                },
            ))

        return signals

    # ── LDP (Liquidity Delta Profiler) Detector ─────
    def _detect_ldp_signals(self, fp_bars: List[FootprintBar], nearby_levels: List[float], utc_time) -> List[Signal]:
        """
        Detect institutional-grade LDP signals (ABS, EXH, DIV, REJ).
        
        These are the same zones and patterns that Lux Algo detects,
        now integrated into our signal system.
        """
        signals = []
        
        if len(fp_bars) < 5:
            return signals

        # Get all LDP signals from the profiler
        ldp_all_signals = self.ldp.get_all_signals(len(fp_bars) - 1)
        
        for zone, ldp_signal_type in ldp_all_signals:
            # Map LDP signal type to our SignalType
            signal_type_map = {
                LDPSignalType.ABSORPTION: SignalType.LDP_ABSORPTION,
                LDPSignalType.EXHAUSTION: SignalType.LDP_EXHAUSTION,
                LDPSignalType.DIVERGENCE: SignalType.LDP_DIVERGENCE,
                LDPSignalType.REJECTION: SignalType.LDP_REJECTION,
            }
            
            signal_type = signal_type_map.get(ldp_signal_type, SignalType.LDP_ABSORPTION)
            
            # Determine direction based on zone type
            # BSL (buy side) with ABS = long
            # SSL (sell side) with ABS = short
            if zone.zone_type == "bsl":
                direction = "long"
            else:  # ssl
                direction = "short"

            # Confidence based on zone health (fresher zones = higher confidence)
            base_confidence = (zone.health / 100.0) * 0.9  # Max 90%
            
            # Session multiplier already applied in scan_all, so just use base
            session_boost = SessionManager.get_confidence_multiplier(utc_time)
            final_confidence = base_confidence * session_boost

            signals.append(Signal(
                signal_type=signal_type,
                direction=direction,
                key_level=zone.mid,
                confidence=final_confidence,
                bar_time=fp_bars[-1].bar_time,
                details={
                    "zone_type": zone.zone_type,
                    "zone_high": zone.high,
                    "zone_low": zone.low,
                    "zone_health": zone.health,
                    "zone_age": len(fp_bars) - zone.left,
                    "touched_count": zone.touched_count,
                    "volume_in_zone": zone.volume_in_zone,
                    "ldp_signal_type": ldp_signal_type.value,
                    "entry_level": zone.mid + (2 * self.tick_size) if direction == "long" else zone.mid - (2 * self.tick_size),
                    "stop_loss": zone.low if direction == "long" else zone.high,
                    "target_ratio": 2.0,  # 1:2 R:R
                },
            ))

        return signals
