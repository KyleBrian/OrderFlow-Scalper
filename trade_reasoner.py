"""
Trade Reasoner - Explains WHY Every Trade Is Taken
═════════════════════════════════════════════════════════════════════════════

This is what separates pros from retail.

Retail traders: "I took a trade"
Pro traders: "I took this trade at this level with this R:R because these 5 factors aligned, and I logged it for analysis"

Your bot MUST explain itself. Every trade. No exceptions.

This module logs:
1. What signal triggered the trade
2. Why each filter passed (or failed)
3. Confidence breakdown
4. Session context
5. Risk/reward calculation
6. Expected outcome

This is your audit trail. This is how you improve.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class TradeDecision:
    """Complete record of WHY a trade was taken"""
    
    # Trade basics
    symbol: str
    direction: str  # "long" or "short"
    entry: float
    stop_loss: float
    target: float
    
    # Context
    bar_time: str
    bar_index: int
    signal_type: str
    
    # Confidence
    base_confidence: float  # Before session boost (0.0-1.0)
    session_name: str
    session_multiplier: float
    final_confidence: float  # After session boost (0.0-1.0)
    
    # Filter results
    filters: Dict[str, bool] = field(default_factory=dict)  # filter_name -> passed?
    filter_details: Dict[str, str] = field(default_factory=dict)  # filter_name -> reason
    
    # Risk/reward
    risk_pips: float = 0.0
    reward_pips: float = 0.0
    ratio: float = field(init=False)  # reward / risk
    risk_amount: float = 0.0  # In USD
    reward_amount: float = 0.0  # In USD
    
    # Additional context
    zone_health: Optional[int] = None  # % (if LDP zone)
    zone_age: Optional[int] = None  # bars
    volume_ratio: Optional[float] = None  # vs 20-bar avg
    spread: float = 0.8
    atr: Optional[float] = None
    
    def __post_init__(self):
        if self.risk_pips > 0:
            self.ratio = self.reward_pips / self.risk_pips
        else:
            self.ratio = 0.0

    def to_dict(self) -> dict:
        """Convert to dict for JSON logging"""
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "target": self.target,
            "bar_time": self.bar_time,
            "bar_index": self.bar_index,
            "signal_type": self.signal_type,
            "base_confidence": round(self.base_confidence, 2),
            "session": self.session_name,
            "session_multiplier": round(self.session_multiplier, 2),
            "final_confidence": round(self.final_confidence, 2),
            "risk_pips": round(self.risk_pips, 1),
            "reward_pips": round(self.reward_pips, 1),
            "ratio": round(self.ratio, 2),
            "risk_usd": round(self.risk_amount, 2),
            "reward_usd": round(self.reward_amount, 2),
            "zone_health": self.zone_health,
            "zone_age": self.zone_age,
            "volume_ratio": round(self.volume_ratio, 2) if self.volume_ratio else None,
            "spread": self.spread,
            "filters": self.filters,
        }


class TradeReasoner:
    """
    Logs complete reasoning for every trade decision.
    
    This is your trading journal on steroids. Every filter. Every reason.
    """

    def __init__(self, account_size_usd: float = 100.0):
        self.account_size = account_size_usd
        self.decisions: List[TradeDecision] = []

    def build_decision(
        self,
        symbol: str,
        direction: str,
        entry: float,
        stop_loss: float,
        target: float,
        signal_type: str,
        bar_time: str,
        bar_index: int,
        base_confidence: float,
        session_name: str,
        session_multiplier: float,
        final_confidence: float,
        filters: Dict[str, bool],
        filter_details: Dict[str, str],
        tick_size: float = 0.0001,
        zone_health: Optional[int] = None,
        zone_age: Optional[int] = None,
        volume_ratio: Optional[float] = None,
        spread: float = 0.8,
        atr: Optional[float] = None,
    ) -> TradeDecision:
        """
        Build a complete trade decision record.
        
        Args:
            All the context about why this trade is being taken
            
        Returns:
            TradeDecision object (can be logged, audited, analyzed)
        """
        # Calculate risk/reward
        risk_pips = abs(entry - stop_loss) / tick_size
        reward_pips = abs(target - entry) / tick_size
        
        # USD amounts (1% risk = account_size * 0.01)
        risk_amount = self.account_size * 0.01  # Standard 1% risk rule
        
        # Account for spread
        actual_risk_pips = risk_pips + (spread / 2.0)  # Account for spread impact
        
        decision = TradeDecision(
            symbol=symbol,
            direction=direction,
            entry=entry,
            stop_loss=stop_loss,
            target=target,
            bar_time=bar_time,
            bar_index=bar_index,
            signal_type=signal_type,
            base_confidence=base_confidence,
            session_name=session_name,
            session_multiplier=session_multiplier,
            final_confidence=final_confidence,
            filters=filters,
            filter_details=filter_details,
            risk_pips=risk_pips,
            reward_pips=reward_pips,
            risk_amount=risk_amount,
            reward_amount=risk_amount * reward_pips / actual_risk_pips,
            zone_health=zone_health,
            zone_age=zone_age,
            volume_ratio=volume_ratio,
            spread=spread,
            atr=atr,
        )
        
        self.decisions.append(decision)
        return decision

    def format_reasoning(self, decision: TradeDecision) -> str:
        """
        Format a trade decision as human-readable reasoning.
        
        This is what gets printed/logged when a trade is taken.
        """
        lines = []
        lines.append("═" * 80)
        lines.append(f"[TRADE APPROVED] {decision.symbol} {decision.direction.upper()} @ {decision.entry:.5f}")
        lines.append("═" * 80)
        lines.append("")
        
        # Signal type
        lines.append(f"📊 SIGNAL TYPE: {decision.signal_type}")
        lines.append(f"   Bar: {decision.bar_time} (#{decision.bar_index})")
        lines.append("")
        
        # Confidence breakdown
        lines.append(f"🎯 CONFIDENCE")
        lines.append(f"   Base:         {decision.base_confidence*100:.0f}%")
        lines.append(f"   Session:      {decision.session_name} × {decision.session_multiplier}x")
        lines.append(f"   Final:        {decision.final_confidence*100:.0f}% ✓")
        lines.append("")
        
        # Filter results (show which filters passed)
        lines.append(f"✅ FILTERS PASSED ({sum(decision.filters.values())}/{len(decision.filters)})")
        for filter_name, passed in decision.filters.items():
            status = "✓" if passed else "✗"
            reason = decision.filter_details.get(filter_name, "")
            lines.append(f"   {status} {filter_name}: {reason}")
        lines.append("")
        
        # Risk/Reward
        lines.append(f"💰 RISK/REWARD")
        lines.append(f"   Entry:        {decision.entry:.5f}")
        lines.append(f"   Stop Loss:    {decision.stop_loss:.5f} ({decision.risk_pips:.1f} pips)")
        lines.append(f"   Target:       {decision.target:.5f} ({decision.reward_pips:.1f} pips)")
        lines.append(f"   Ratio:        1:{decision.ratio:.2f} ✓")
        lines.append(f"   Risk USD:     ${decision.risk_amount:.2f}")
        lines.append(f"   Reward USD:   ${decision.reward_amount:.2f}")
        lines.append("")
        
        # Zone details (if applicable)
        if decision.zone_health is not None:
            lines.append(f"📍 ZONE DETAILS")
            lines.append(f"   Health:       {decision.zone_health}%")
            lines.append(f"   Age:          {decision.zone_age} bars")
            if decision.volume_ratio:
                lines.append(f"   Volume:       {decision.volume_ratio:.2f}x avg")
            lines.append("")
        
        # Volatility context
        if decision.atr:
            lines.append(f"📈 VOLATILITY")
            lines.append(f"   ATR(20):      {decision.atr:.1f} pips")
            lines.append("")
        
        lines.append("═" * 80)
        
        return "\n".join(lines)

    def format_concise(self, decision: TradeDecision) -> str:
        """
        Concise one-line summary for logs.
        
        [LONG] EURUSD @ 1.0853 (conf 78%) | 1:2.0 R:R | LDP_ABS + London boost
        """
        filter_summary = ",".join(k for k, v in decision.filters.items() if v)
        
        return (
            f"[{decision.direction.upper()}] {decision.symbol} @ {decision.entry:.5f} "
            f"(conf {decision.final_confidence*100:.0f}%) | "
            f"1:{decision.ratio:.1f} R:R | "
            f"{decision.signal_type} + {decision.session_name} ({decision.session_multiplier}x)"
        )

    def log_to_csv(self, filepath: str) -> None:
        """
        Log all decisions to CSV for analysis.
        
        Useful for backtesting, finding patterns in win/loss trades.
        """
        import csv
        
        if not self.decisions:
            return
        
        with open(filepath, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.decisions[0].to_dict().keys())
            
            # Write header if file is empty
            f.seek(0, 2)  # Go to end
            if f.tell() == 0:
                writer.writeheader()
            
            for decision in self.decisions[-1:]:  # Log last decision
                writer.writerow(decision.to_dict())

    def log_to_json(self, filepath: str) -> None:
        """
        Log all decisions to JSON for detailed analysis.
        """
        decisions_data = [d.to_dict() for d in self.decisions]
        
        with open(filepath, 'a') as f:
            for decision_data in decisions_data[-1:]:  # Log last decision
                json.dump(decision_data, f)
                f.write("\n")

    def print_reasoning(self, decision: TradeDecision, verbose: bool = True) -> None:
        """
        Print reasoning to console + logs.
        
        Args:
            decision: TradeDecision to print
            verbose: If True, full format. If False, concise format.
        """
        if verbose:
            text = self.format_reasoning(decision)
        else:
            text = self.format_concise(decision)
        
        print(text)
        logger.info(text)

    def get_statistics(self) -> dict:
        """
        Get trading statistics from all decisions.
        
        Useful for performance analysis.
        """
        if not self.decisions:
            return {}
        
        total_trades = len(self.decisions)
        long_trades = len([d for d in self.decisions if d.direction == "long"])
        short_trades = total_trades - long_trades
        
        avg_confidence = sum(d.final_confidence for d in self.decisions) / total_trades
        avg_ratio = sum(d.ratio for d in self.decisions) / total_trades
        
        total_risk = sum(d.risk_amount for d in self.decisions)
        total_potential_reward = sum(d.reward_amount for d in self.decisions)
        
        # Session breakdown
        sessions = {}
        for d in self.decisions:
            sessions[d.session_name] = sessions.get(d.session_name, 0) + 1
        
        return {
            "total_trades": total_trades,
            "long_trades": long_trades,
            "short_trades": short_trades,
            "avg_confidence": round(avg_confidence, 2),
            "avg_ratio": round(avg_ratio, 2),
            "total_risk_usd": round(total_risk, 2),
            "total_potential_reward_usd": round(total_potential_reward, 2),
            "session_breakdown": sessions,
        }


# ═════════════════════════════════════════════════════════════════
# EXAMPLE USAGE
# ═════════════════════════════════════════════════════════════════
"""
from trade_reasoner import TradeReasoner

reasoner = TradeReasoner(account_size_usd=100.0)

# Build a trade decision
decision = reasoner.build_decision(
    symbol="EURUSD",
    direction="long",
    entry=1.0853,
    stop_loss=1.0840,
    target=1.0885,
    signal_type="ldp_absorption",
    bar_time="2024-01-15 02:30:00",
    bar_index=150,
    base_confidence=0.72,
    session_name="London",
    session_multiplier=1.30,
    final_confidence=0.94,
    filters={
        "session": True,
        "zone_fresh": True,
        "real_absorption": True,
        "vwap_reclaim": True,
        "htf_conflict": False,
        "news_time": True,
        "spread": True,
    },
    filter_details={
        "session": "London Open +30% boost",
        "zone_fresh": "Health 85% > 70% threshold",
        "real_absorption": "Vol 1.8x, delta +85",
        "vwap_reclaim": "Entry 1.0853 > VWAP 1.0840",
        "htf_conflict": "Zone 30 pips from daily VWAP (ok)",
        "news_time": "Safe from events",
        "spread": "0.8 pips < 2.0 limit",
    },
    zone_health=85,
    zone_age=8,
    volume_ratio=1.8,
)

# Print verbose reasoning
reasoner.print_reasoning(decision, verbose=True)

# Or concise
print(reasoner.format_concise(decision))

# Log to CSV
reasoner.log_to_csv("trades.csv")

# Get statistics
stats = reasoner.get_statistics()
print(stats)
"""
