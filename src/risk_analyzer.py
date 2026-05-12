"""
Risk assessment module -- LoL Realtime Coach v2.1
==================================================
Official rules doc (LoL_Realtime_Coach_Official_Rules.md) sec2.3 implementation.

Formula:
    min(100.0, weighted_distance_points x advantage_factor x concentration_factor)

Factors:
    1. weighted_distance_points : per-enemy dist score * confidence weight
    2. advantage_factor         : ally_count vs enemy_count
    3. concentration_factor     : enemy spread (std-dev based)

Interface:
    result = {
        "my_position": DetBox | None,
        "ally":        [DetBox, ...],
        "enemy":       [DetBox, ...],
    }
    DetBox must have .bbox (x1,y1,x2,y2) and .top1_conf (float).
"""
from __future__ import annotations

import math
import time
from typing import Any

# -- constants (official rules sec6) -----------------------------------------

# sec6.1 distance-based
DANGER_RADIUS_HIGH = 60    # px -> +40 pts
DANGER_RADIUS_MID  = 120   # px -> +20 pts

# sec6.2 LLM call
RISK_AUTO_ALERT     = 65   # trigger LLM when risk >= this
RISK_ALERT_COOLDOWN = 10   # seconds

# sec6.3 numerical advantage factor
ADVANTAGE_LARGE_LOSS  = 1.40   # enemy > ally + 2
ADVANTAGE_MID_LOSS    = 1.30   # enemy = ally + 2
ADVANTAGE_SMALL_LOSS  = 1.15   # enemy = ally + 1
ADVANTAGE_EQUAL       = 1.00   # enemy = ally
ADVANTAGE_GAIN        = 0.85   # ally > enemy

# sec6.4 threat concentration factor
CONCENTRATION_VERY_HIGH   = 1.25   # std < 30px
CONCENTRATION_HIGH        = 1.15   # std 30-60px
CONCENTRATION_MEDIUM      = 1.00   # std 60-100px
CONCENTRATION_LOW         = 0.80   # std > 100px
CONCENTRATION_MIN_ENEMIES = 2      # <= this: skip concentration calc

# sec6.5 detection confidence weight
CONF_WEIGHT_VERY_HIGH = 1.00   # conf >= 0.90
CONF_WEIGHT_HIGH      = 0.95   # conf 0.75-0.89
CONF_WEIGHT_MEDIUM    = 0.85   # conf 0.60-0.74
CONF_WEIGHT_LOW       = 0.70   # conf < 0.60


# -- helpers ------------------------------------------------------------------

def _center(box: Any):
    x1, y1, x2, y2 = box.bbox
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def _conf_weight(conf: float) -> float:
    if conf >= 0.90:
        return CONF_WEIGHT_VERY_HIGH
    elif conf >= 0.75:
        return CONF_WEIGHT_HIGH
    elif conf >= 0.60:
        return CONF_WEIGHT_MEDIUM
    else:
        return CONF_WEIGHT_LOW


def _advantage_factor(ally_count: int, enemy_count: int) -> float:
    diff = enemy_count - ally_count
    if diff > 2:
        return ADVANTAGE_LARGE_LOSS
    elif diff == 2:
        return ADVANTAGE_MID_LOSS
    elif diff == 1:
        return ADVANTAGE_SMALL_LOSS
    elif diff == 0:
        return ADVANTAGE_EQUAL
    else:
        return ADVANTAGE_GAIN


def _concentration_factor(enemies: list) -> float:
    if len(enemies) <= CONCENTRATION_MIN_ENEMIES:
        return CONCENTRATION_MEDIUM
    positions = [_center(e) for e in enemies]
    mx = sum(p[0] for p in positions) / len(positions)
    my = sum(p[1] for p in positions) / len(positions)
    variance = sum((p[0]-mx)**2 + (p[1]-my)**2 for p in positions) / len(positions)
    std = math.sqrt(variance)
    if std < 30:
        return CONCENTRATION_VERY_HIGH
    elif std < 60:
        return CONCENTRATION_HIGH
    elif std < 100:
        return CONCENTRATION_MEDIUM
    else:
        return CONCENTRATION_LOW


def _weighted_distance_points(my_pos: Any, enemies: list) -> float:
    mx, my = _center(my_pos)
    total = 0.0
    for e in enemies:
        ex, ey = _center(e)
        dist = math.sqrt((mx - ex)**2 + (my - ey)**2)
        if dist <= DANGER_RADIUS_HIGH:
            base = 40.0
        elif dist <= DANGER_RADIUS_MID:
            base = 20.0
        else:
            base = 0.0
        conf = getattr(e, "top1_conf", 0.5)
        total += base * _conf_weight(conf)
    return total


# -- main class ---------------------------------------------------------------

class RiskAnalyzer:
    """
    Minimap detection result -> risk score 0-100.

    Risk zones (official rules sec2.2):
        0-30   : safe   (green)
        31-65  : caution (yellow)
        66-100 : danger  (red) - triggers LLM auto call
    """

    def __init__(self) -> None:
        self._last_alert_t: float = 0.0
        self.last_risk: float = 0.0

    def calculate_risk(self, result: dict) -> float:
        """
        TwoStageDetectorV2 result dict -> risk 0.0-100.0

        Args:
            result: {"my_position": DetBox|None, "ally": [...], "enemy": [...]}
        """
        enemies = result.get("enemy", [])
        allies  = result.get("ally",  [])
        my_pos  = result.get("my_position")

        if not enemies:
            self.last_risk = 0.0
            return 0.0

        if my_pos is None:
            # fallback: conservative estimate when own position unknown
            risk = min(100.0, len(enemies) * 12.0)
            self.last_risk = risk
            return risk

        # official rules sec2.3.5 final formula
        wdp  = _weighted_distance_points(my_pos, enemies)
        adv  = _advantage_factor(len(allies), len(enemies))
        conc = _concentration_factor(enemies)

        risk = min(100.0, wdp * adv * conc)
        self.last_risk = risk
        return risk

    def should_trigger_alert(self, risk: float) -> bool:
        """
        Official rules sec1.1: risk >= RISK_AUTO_ALERT AND cooldown elapsed.
        Updates internal timer when returning True.
        """
        now = time.time()
        if risk >= RISK_AUTO_ALERT and (now - self._last_alert_t) >= RISK_ALERT_COOLDOWN:
            self._last_alert_t = now
            return True
        return False

    def reset_cooldown(self) -> None:
        """Force-reset cooldown (e.g. after manual F9 request)."""
        self._last_alert_t = 0.0
