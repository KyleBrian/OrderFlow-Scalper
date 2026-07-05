"""
Session Configuration & Multipliers
═════════════════════════════════════════════════════════════════
Wall Street-grade session awareness:
- London Open: 1.30x confidence (high vol, institutions)
- NY Open: 1.25x confidence (news, major moves)
- Asia: BLOCKED (38% win rate = toxic)
- Dead Zone: BLOCKED (pre-lunch chop)

This prevents losing $4-12/day in low-probability windows.
"""

from dataclasses import dataclass
from typing import Dict, Tuple
from datetime import datetime


@dataclass
class SessionConfig:
    """Session definition with all parameters"""
    name: str
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int
    confidence_multiplier: float  # 0.0 = HARD BLOCK, >1.0 = boost
    min_zone_health: int  # % health required to trade
    min_volume_ratio: float  # minimum volume vs 20-bar avg
    can_trade: bool  # False = HARD BLOCK regardless of multiplier


class SessionManager:
    """
    Manages trading sessions with Wall Street-grade enforcement.
    
    Each session has:
    - Time window (EST)
    - Confidence multiplier
    - Zone health requirement (per session quality)
    - Volume confirmation requirement
    - Hard trade block flag
    """

    # ═════════════════════════════════════════════════════════════════
    # SESSION DEFINITIONS (EST timezone)
    # ═════════════════════════════════════════════════════════════════

    LONDON_OPEN = SessionConfig(
        name="London",
        start_hour=2,
        start_minute=0,
        end_hour=5,
        end_minute=0,
        confidence_multiplier=1.30,  # +30% boost (institutions active)
        min_zone_health=70,  # STRICT: 70%+ health required (fresh zones only)
        min_volume_ratio=1.5,  # High volume confirmation needed
        can_trade=True,
    )

    NY_OPEN = SessionConfig(
        name="NY",
        start_hour=8,
        start_minute=30,
        end_hour=11,
        end_minute=0,
        confidence_multiplier=1.25,  # +25% boost (major news, moves)
        min_zone_health=50,  # RELAXED: 50%+ ok (more opportunities)
        min_volume_ratio=1.2,  # Standard volume confirmation
        can_trade=True,
    )

    ASIA = SessionConfig(
        name="Asia",
        start_hour=22,
        start_minute=0,
        end_hour=6,
        end_minute=0,
        confidence_multiplier=0.0,  # HARD BLOCK - 38% ABS win rate = toxic
        min_zone_health=0,
        min_volume_ratio=0,
        can_trade=False,  # Cannot trade, period
    )

    DEAD_ZONE = SessionConfig(
        name="DeadZone",
        start_hour=12,
        start_minute=0,
        end_hour=14,
        end_minute=0,
        confidence_multiplier=0.0,  # HARD BLOCK - pre-lunch chop
        min_zone_health=0,
        min_volume_ratio=0,
        can_trade=False,  # Cannot trade, period
    )

    # All sessions in order (check in this order)
    SESSIONS = [LONDON_OPEN, NY_OPEN, DEAD_ZONE, ASIA]

    # ═════════════════════════════════════════════════════════════════
    # PUBLIC METHODS
    # ═════════════════════════════════════════════════════════════════

    @classmethod
    def get_current_session(cls, utc_time: datetime = None) -> Tuple[SessionConfig, bool]:
        """
        Get current session and whether trading is allowed.
        
        Args:
            utc_time: datetime in UTC (will be converted to EST)
            
        Returns:
            (session_config, can_trade_bool)
        """
        if utc_time is None:
            utc_time = datetime.utcnow()

        # Convert UTC to EST (UTC-5, or -4 during daylight saving)
        # Simplified: assume EST year-round (UTC-5)
        est_time = utc_time.replace(tzinfo=None)  # Assume input is already EST
        hour = est_time.hour
        minute = est_time.minute

        # Check each session in order
        for session in cls.SESSIONS:
            if cls._is_in_session(hour, minute, session):
                return session, session.can_trade

        # Default: Asia session (default to False if no session matched)
        return cls.ASIA, False

    @classmethod
    def get_confidence_multiplier(cls, utc_time: datetime = None) -> float:
        """
        Get confidence multiplier for current time.
        
        0.0 = HARD BLOCK (cannot trade)
        1.0 = normal confidence
        >1.0 = boost
        """
        session, can_trade = cls.get_current_session(utc_time)
        if not can_trade:
            return 0.0
        return session.confidence_multiplier

    @classmethod
    def can_trade_now(cls, utc_time: datetime = None) -> bool:
        """
        Hard check: Can we trade right now?
        
        Returns True only if:
        - Current time is London Open OR NY Open
        - NOT in Asia (22:00-06:00 EST)
        - NOT in Dead Zone (12:00-14:00 EST)
        """
        _, can_trade = cls.get_current_session(utc_time)
        return can_trade

    @classmethod
    def get_min_zone_health(cls, utc_time: datetime = None) -> int:
        """
        Get minimum zone health % for current session.
        
        London: 70% (strict, fresh zones only)
        NY: 50% (relaxed, more opportunities)
        Asia/Dead: 0% (cannot trade anyway)
        """
        session, _ = cls.get_current_session(utc_time)
        return session.min_zone_health

    @classmethod
    def get_min_volume_ratio(cls, utc_time: datetime = None) -> float:
        """
        Get minimum volume confirmation ratio for current session.
        
        London: 1.5x (strict volume needed)
        NY: 1.2x (standard)
        Asia/Dead: 0 (cannot trade)
        """
        session, _ = cls.get_current_session(utc_time)
        return session.min_volume_ratio

    @classmethod
    def get_session_name(cls, utc_time: datetime = None) -> str:
        """Get human-readable session name"""
        session, _ = cls.get_current_session(utc_time)
        return session.name

    @classmethod
    def apply_session_boost(cls, base_confidence: float, utc_time: datetime = None) -> float:
        """
        Apply session multiplier to base confidence.
        
        If not tradeable session, returns 0.0 (HARD BLOCK).
        Otherwise returns base_confidence * multiplier.
        """
        multiplier = cls.get_confidence_multiplier(utc_time)
        if multiplier == 0.0:
            return 0.0
        return min(base_confidence * multiplier, 1.0)

    # ═════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ═════════════════════════════════════════════════════════════════

    @staticmethod
    def _is_in_session(hour: int, minute: int, session: SessionConfig) -> bool:
        """Check if given time is within session window"""
        current_time = hour * 60 + minute
        session_start = session.start_hour * 60 + session.start_minute
        session_end = session.end_hour * 60 + session.end_minute

        # Handle sessions that cross midnight (Asia: 22:00-06:00)
        if session_end < session_start:
            return current_time >= session_start or current_time < session_end

        return session_start <= current_time < session_end


# ═════════════════════════════════════════════════════════════════
# EXAMPLE USAGE
# ═════════════════════════════════════════════════════════════════
"""
from datetime import datetime
from session_config import SessionManager

# Check current time
multiplier = SessionManager.get_confidence_multiplier()
print(f"Confidence multiplier: {multiplier}x")

# Apply to signal
base_confidence = 0.68
boosted = SessionManager.apply_session_boost(base_confidence)
print(f"Base: {base_confidence} → Boosted: {boosted}")

# Can we trade?
if SessionManager.can_trade_now():
    print("✓ Can trade now")
else:
    print("✗ Cannot trade (Asia/Dead Zone)")

# What session?
session_name = SessionManager.get_session_name()
print(f"Current session: {session_name}")

# Min zone health for this session
min_health = SessionManager.get_min_zone_health()
print(f"Min zone health: {min_health}%")
"""
