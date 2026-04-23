"""Test script for RiskAnalyzer."""
from src.risk_analyzer import RiskAnalyzer


def test_no_threat():
    """Test: No enemies detected."""
    analyzer = RiskAnalyzer()
    summary = {
        "frames": 100,
        "duration": 34.5,
        "tracks": {
            "ally_champion": [[0.0, 0.5, 0.5]],
        }
    }
    risk = analyzer.calculate_risk(summary)
    print(f"✅ No threat: risk = {risk:.1f}% (expect ~0%)")
    assert risk < 30, "No threat should have low risk"


def test_enemy_nearby():
    """Test: Enemy champion nearby."""
    analyzer = RiskAnalyzer()
    summary = {
        "frames": 100,
        "duration": 34.5,
        "tracks": {
            "enemy_champion": [[i*0.1, 0.45+i*0.01, 0.45+i*0.01] for i in range(20)],
            "ally_champion": [[0.0, 0.5, 0.5]],
        }
    }
    risk = analyzer.calculate_risk(summary)
    print(f"✅ Enemy nearby: risk = {risk:.1f}% (expect ~40-60%)")
    assert risk > 40, "Enemy nearby should increase risk"


def test_enemy_tower_danger():
    """Test: Enemy tower in red zone + multiple enemies."""
    analyzer = RiskAnalyzer()
    summary = {
        "frames": 100,
        "duration": 34.5,
        "tracks": {
            "tower": [[i*0.1, 0.8, 0.2] for i in range(20)],  # Red zone
            "enemy_champion": [[i*0.1, 0.75, 0.25] for i in range(40)],  # Multiple enemies
        }
    }
    risk = analyzer.calculate_risk(summary)
    print(f"✅ Enemy tower danger: risk = {risk:.1f}% (expect ~60-80%)")
    assert risk > 50, "Enemy tower + champions should increase risk"


def test_high_activity():
    """Test: High recent activity."""
    analyzer = RiskAnalyzer()
    # Many detections in last 5 seconds
    summary = {
        "frames": 300,
        "duration": 60.0,
        "tracks": {
            "enemy_champion": [[30.0+i*0.1, 0.5, 0.5] for i in range(100)],  # Last 30s
        }
    }
    risk = analyzer.calculate_risk(summary)
    print(f"✅ High activity: risk = {risk:.1f}% (expect ~50-80%)")
    assert risk > 30, "High activity should increase risk"


def test_alert_threshold():
    """Test: Alert trigger logic."""
    analyzer = RiskAnalyzer()

    # Low risk - no alert
    should_alert = analyzer.should_trigger_alert(50.0)
    print(f"✅ Risk 50%: should_alert = {should_alert} (expect False)")
    assert not should_alert

    # High risk - alert triggered
    should_alert = analyzer.should_trigger_alert(75.0)
    print(f"✅ Risk 75%: should_alert = {should_alert} (expect True)")
    assert should_alert

    # High risk but too soon - no alert
    should_alert = analyzer.should_trigger_alert(80.0)
    print(f"✅ Risk 80% (within 5s): should_alert = {should_alert} (expect False)")
    assert not should_alert


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Testing RiskAnalyzer")
    print("="*60 + "\n")

    try:
        test_no_threat()
        test_enemy_nearby()
        test_enemy_tower_danger()
        test_high_activity()
        test_alert_threshold()

        print("\n" + "="*60)
        print("✅ All tests passed!")
        print("="*60 + "\n")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}\n")
        raise
