"""RiskAnalyzer v2.1 unit tests."""
from __future__ import annotations
import time
from src.risk_analyzer import RISK_AUTO_ALERT, RiskAnalyzer


class _Box:
    def __init__(self, cx, cy, conf=0.92, size=10.0):
        h = size / 2
        self.bbox = (cx - h, cy - h, cx + h, cy + h)
        self.top1_conf = conf
        self.top1 = "Unknown"

    @classmethod
    def at(cls, cx, cy, conf=0.92):
        return cls(cx, cy, conf)


def R(my_cx=100, my_cy=100, eps=None, aps=None, ec=0.92):
    mp = _Box.at(my_cx, my_cy, 1.0)
    en = [_Box.at(x, y, ec) for x, y in (eps or [])]
    al = [_Box.at(x, y) for x, y in (aps or [])]
    return {"my_position": mp, "enemy": en, "ally": al}


def test_no_enemies():
    a = RiskAnalyzer()
    r = a.calculate_risk(R(eps=[]))
    assert r == 0.0, r
    print("PASS no_enemies:", r)


def test_high_danger_zone():
    # dist=50 <= 60 -> +40, conf=0.92 -> x1.00, adv=1.00, conc=1.00 -> 40.0
    a = RiskAnalyzer()
    r = a.calculate_risk(R(100, 100, [(100, 150)], [(200, 200)]))
    assert abs(r - 40.0) < 1.0, r
    print("PASS high_danger:", round(r, 1))


def test_mid_danger_zone():
    # dist=100 -> +20, conf=0.92 -> x1.00 -> 20.0
    a = RiskAnalyzer()
    r = a.calculate_risk(R(100, 100, [(100, 200)], [(200, 200)]))
    assert abs(r - 20.0) < 1.0, r
    print("PASS mid_danger:", round(r, 1))


def test_outside_range():
    a = RiskAnalyzer()
    r = a.calculate_risk(R(100, 100, [(100, 400)]))
    assert r == 0.0, r
    print("PASS outside_range:", r)


def test_disadvantage_amplifies():
    r_base = RiskAnalyzer().calculate_risk(
        R(100, 100, [(100, 150)], [(200, 200)]))
    r_dis = RiskAnalyzer().calculate_risk(
        R(100, 100, [(100, 150), (110, 155), (90, 148)], [(200, 200), (210, 210)]))
    assert r_dis > r_base, (r_base, r_dis)
    print("PASS disadvantage:", round(r_base, 1), "->", round(r_dis, 1))


def test_advantage_reduces():
    r_eq = RiskAnalyzer().calculate_risk(
        R(100, 100, [(100, 150)], [(200, 200)]))
    r_adv = RiskAnalyzer().calculate_risk(
        R(100, 100, [(100, 150)], [(200, 200), (210, 210)]))
    assert r_adv < r_eq, (r_eq, r_adv)
    print("PASS advantage:", round(r_eq, 1), "->", round(r_adv, 1))


def test_concentration():
    # clustered (std < 30): x1.25  vs  spread (std varies)
    r_c = RiskAnalyzer().calculate_risk(
        R(100, 100, [(100, 150), (110, 145), (90, 148)],
                    [(200, 200), (210, 210), (220, 220)]))
    r_s = RiskAnalyzer().calculate_risk(
        R(100, 100, [(100, 140), (100, 210), (100, 215)],
                    [(200, 200), (210, 210), (220, 220)]))
    assert r_c >= r_s, (r_c, r_s)
    print("PASS concentration: clustered", round(r_c, 1), "spread", round(r_s, 1))


def test_confidence_weight():
    r_h = RiskAnalyzer().calculate_risk(R(100, 100, [(100, 150)], ec=0.95))
    r_l = RiskAnalyzer().calculate_risk(R(100, 100, [(100, 150)], ec=0.55))
    assert r_h > r_l, (r_h, r_l)
    print("PASS conf_weight: high", round(r_h, 1), "low", round(r_l, 1))


def test_spec_example_1():
    """spec sec2.3.5 ex1: enemy2, ally5, spread -> 59.0"""
    a = RiskAnalyzer()
    result = {
        "my_position": _Box.at(200, 200, 1.0),
        "enemy": [_Box.at(200, 250, 0.92), _Box.at(200, 280, 0.85)],
        "ally": [_Box.at(400, 400), _Box.at(410, 410)],
    }
    r = a.calculate_risk(result)
    assert abs(r - 59.0) < 2.0, "spec_ex1 failed: " + str(r)
    print("PASS spec_ex1:", round(r, 1), "(expect 59.0)")


def test_no_my_position():
    a = RiskAnalyzer()
    result = {
        "my_position": None,
        "enemy": [_Box.at(100, 100), _Box.at(200, 200), _Box.at(300, 300)],
        "ally": [],
    }
    r = a.calculate_risk(result)
    assert abs(r - 36.0) < 1.0, r
    print("PASS no_my_pos:", round(r, 1), "(expect 36.0)")


def test_alert_cooldown():
    a = RiskAnalyzer()
    assert not a.should_trigger_alert(50.0)
    assert a.should_trigger_alert(70.0)
    assert not a.should_trigger_alert(70.0)
    print("PASS alert_cooldown: OK")


def test_max_clamp():
    a = RiskAnalyzer()
    result = {
        "my_position": _Box.at(100, 100, 1.0),
        "enemy": [_Box.at(100+dx, 100+dy, 0.95)
                  for dx, dy in [(0,20),(5,22),(-5,18),(3,21),(-3,19)]],
        "ally": [],
    }
    r = a.calculate_risk(result)
    assert r <= 100.0, r
    print("PASS max_clamp:", round(r, 1))


if __name__ == "__main__":
    TESTS = [
        test_no_enemies, test_high_danger_zone, test_mid_danger_zone,
        test_outside_range, test_disadvantage_amplifies, test_advantage_reduces,
        test_concentration, test_confidence_weight, test_spec_example_1,
        test_no_my_position, test_alert_cooldown, test_max_clamp,
    ]
    print("=" * 50)
    print("  RiskAnalyzer v2.1 tests")
    print("=" * 50)
    failed = 0
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print("FAIL", t.__name__, ":", e)
            failed += 1
    print("=" * 50)
    if failed == 0:
        print("ALL", len(TESTS), "tests PASSED!")
    else:
        print("FAILED", failed, "/", len(TESTS))
    print("=" * 50)
    if failed:
        raise SystemExit(1)
