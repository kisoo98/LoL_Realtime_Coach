"""Risk assessment module for minimap data."""
from __future__ import annotations

import time
from typing import Dict, List


class RiskAnalyzer:
    """
    Analyzes minimap detections and calculates risk score.

    Risk Score (0-100):
        0-30:   Safe (Green) - No threat detected
        31-65:  Caution (Yellow) - Moderate threat, be aware
        66-100: Danger (Red) - High threat, immediate attention needed

    Risk Calculation Factors:
        1. Enemy Champions (30%):
           - More champions nearby = higher risk
        2. Threat Proximity (40%):
           - Tower/Dragon/Baron proximity = higher risk
        3. Activity Level (30%):
           - Recent movement intensity in last 5s = urgency
    """

    # Risk thresholds
    THRESHOLD_AUTO_ALERT = 65  # Auto-alert when risk > this
    MIN_ALERT_INTERVAL = 5  # Minimum seconds between alerts

    # Class importance weights (for threat assessment)
    CLASS_WEIGHTS = {
        "enemy_champion": 0.8,
        "ally_champion": 0.0,  # Friendly, no threat
        "tower": 0.6,
        "dragon": 0.7,
        "baron": 0.8,
        "inhibitor": 0.5,
        "turret": 0.6,  # Alias for tower
    }

    # Position zones on minimap
    # [left, top, right, bottom] as fractions [0..1]
    ZONES = {
        "blue_base": [0.0, 0.65, 0.35, 1.0],     # Bottom-left
        "blue_jungle": [0.0, 0.3, 0.5, 0.8],      # Left side
        "neutral": [0.3, 0.3, 0.7, 0.7],          # Center
        "red_jungle": [0.5, 0.2, 1.0, 0.5],       # Right side
        "red_base": [0.65, 0.0, 1.0, 0.35],       # Top-right
    }

    def __init__(self):
        self.last_alert_time = 0.0
        self.last_risk_score = 0.0

    def calculate_risk(self, summary: Dict) -> float:
        """
        Calculate risk score from buffer summary.

        Args:
            summary: Output from RollingBuffer.summarize()
                {
                    "frames": int,
                    "duration": float,
                    "tracks": {
                        "class_name": [[time, x, y], ...],
                        ...
                    }
                }

        Returns:
            Risk score (0.0-100.0)
        """
        if not summary or not summary.get("tracks"):
            return 0.0

        tracks = summary["tracks"]

        # Factor 1: Enemy Champion Count (30%)
        champion_risk = self._assess_champion_risk(tracks)

        # Factor 2: Threat Proximity (40%)
        proximity_risk = self._assess_proximity_risk(tracks)

        # Factor 3: Activity Level (30%)
        activity_risk = self._assess_activity_risk(tracks, summary.get("duration", 0))

        # Weighted combination
        total_risk = (
            champion_risk * 0.30 +
            proximity_risk * 0.40 +
            activity_risk * 0.30
        )

        # Clamp to [0, 100]
        total_risk = max(0.0, min(100.0, total_risk))
        self.last_risk_score = total_risk

        return total_risk

    def _assess_champion_risk(self, tracks: Dict[str, List]) -> float:
        """
        Assess risk based on enemy champion count.
        More enemy champions = higher risk.
        """
        enemy_count = len(tracks.get("enemy_champion", []))
        ally_count = len(tracks.get("ally_champion", []))

        # Rough enemy count estimates (based on detection frequency)
        # 10+ detections ≈ 1 champion
        estimated_enemies = max(1, enemy_count // 10 + 1)
        estimated_allies = max(1, ally_count // 10 + 1)

        # Numerical disadvantage amplifies risk
        if estimated_enemies > estimated_allies:
            # 3v2 = 1.5x risk, 4v1 = 4x risk
            number_disadvantage = estimated_enemies / max(1, estimated_allies)
            return min(100.0, number_disadvantage * 50.0)

        return 0.0

    def _assess_proximity_risk(self, tracks: Dict[str, List]) -> float:
        """
        Assess risk based on threats near player.
        Enemy towers/objectives nearby = higher risk.
        """
        risk_scores = []

        # Check last position of each threat type
        for class_name, positions in tracks.items():
            weight = self.CLASS_WEIGHTS.get(class_name, 0.0)
            if weight <= 0.0:
                continue

            if not positions:
                continue

            # Get latest position (last detection)
            latest_pos = positions[-1]  # [time, x, y]
            x, y = latest_pos[1], latest_pos[2]

            # Check if in dangerous zone
            if self._is_in_red_zone(x, y):
                # Enemy territory = very dangerous
                risk_scores.append(weight * 100.0)
            elif self._is_in_neutral_zone(x, y):
                # Neutral zone = moderate danger
                risk_scores.append(weight * 60.0)
            elif self._is_nearby(x, y, radius=0.3):
                # Close to player = dangerous
                risk_scores.append(weight * 80.0)

        if not risk_scores:
            return 0.0

        # Return max risk (worst threat)
        return min(100.0, max(risk_scores))

    def _assess_activity_risk(self, tracks: Dict[str, List], duration: float) -> float:
        """
        Assess urgency based on recent activity.
        High activity = urgent situation = higher risk.
        """
        if duration < 1.0:
            return 0.0

        # Count detections in last 5 seconds
        last_5s_count = 0
        cutoff_time = duration - 5.0

        for positions in tracks.values():
            for time_rel, _, _ in positions:
                if time_rel >= cutoff_time:
                    last_5s_count += 1

        # More detections = more activity = more urgent
        # 0 detections = 0%, 50+ detections = 100%
        activity_level = min(100.0, (last_5s_count / 50.0) * 100.0)
        return activity_level

    def should_trigger_alert(self, risk_score: float) -> bool:
        """
        Check if alert should be triggered.
        Conditions:
        - Risk score > THRESHOLD
        - Minimum interval since last alert
        """
        now = time.time()
        time_since_last = now - self.last_alert_time

        should_alert = (
            risk_score > self.THRESHOLD_AUTO_ALERT
            and time_since_last >= self.MIN_ALERT_INTERVAL
        )

        if should_alert:
            self.last_alert_time = now

        return should_alert

    @staticmethod
    def _is_in_red_zone(x: float, y: float) -> bool:
        """Check if position is in red team zone (enemy territory)."""
        return x > 0.65 and y < 0.35

    @staticmethod
    def _is_in_blue_zone(x: float, y: float) -> bool:
        """Check if position is in blue team zone (safe territory)."""
        return x < 0.35 and y > 0.65

    @staticmethod
    def _is_in_neutral_zone(x: float, y: float) -> bool:
        """Check if position is in neutral zone (risky)."""
        return 0.3 < x < 0.7 and 0.3 < y < 0.7

    @staticmethod
    def _is_nearby(x: float, y: float, radius: float = 0.3) -> bool:
        """
        Check if position is near player (assumed center).
        Player is assumed at minimap center (0.5, 0.5).
        """
        player_x, player_y = 0.5, 0.5
        distance = ((x - player_x) ** 2 + (y - player_y) ** 2) ** 0.5
        return distance < radius
