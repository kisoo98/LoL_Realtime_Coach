"""
LoL Realtime Coach — 통합 PoC 상수 정의
==========================================
위험도 산정 임계값과 알림 쿨타임 등 전역 상수.
"""
from __future__ import annotations

# ── 위험도 v2.1 (멀티팩터: 거리 + 우위 + 집중도 + 신뢰도) ────────────────────────
# 1️⃣ 거리 기반 포인트
DANGER_RADIUS_HIGH = 60   # 이 안에 적이 있으면 +40점
DANGER_RADIUS_MID  = 120  # 이 안에 적이 있으면 +20점

# 2️⃣ 신뢰도 가중치 (top1_conf 기반)
CONF_WEIGHT_VERY_HIGH = 1.00  # conf >= 0.90
CONF_WEIGHT_HIGH      = 0.95  # conf 0.75~0.89
CONF_WEIGHT_MEDIUM    = 0.85  # conf 0.60~0.74
CONF_WEIGHT_LOW       = 0.70  # conf < 0.60

# 3️⃣ 수치적 우위/열위 팩터 (ally_count vs enemy_count)
ADVANTAGE_LARGE_LOSS  = 1.40  # enemy > ally + 2
ADVANTAGE_MID_LOSS    = 1.30  # enemy = ally + 2
ADVANTAGE_SMALL_LOSS  = 1.15  # enemy = ally + 1
ADVANTAGE_EQUAL       = 1.00  # enemy = ally
ADVANTAGE_GAIN        = 0.85  # ally > enemy

# 4️⃣ 위협 집중도 팩터 (적 위치 표준편차 기반)
CONCENTRATION_VERY_HIGH = 1.25  # std < 30px (밀집)
CONCENTRATION_HIGH      = 1.15  # std 30~60px
CONCENTRATION_MEDIUM    = 1.00  # std 60~100px
CONCENTRATION_LOW       = 0.80  # std > 100px
CONCENTRATION_MIN_ENEMIES = 2   # 이 이하면 집중도 = 1.00 (계산 불가)

# ── Gemini 자동 호출 임계 / 쿨타임 ──────────────────────────────────────────
RISK_AUTO_ALERT     = 65  # 위험도 ≥ 이 값이면 LLM 자동 호출
RISK_ALERT_COOLDOWN = 10  # 같은 위험도 알림 사이 최소 간격 (초)

# ── 오버레이 표시 시간 (초) ─────────────────────────────────────────────────
LLM_DISPLAY_SEC   = 20  # Gemini 피드백 표시 시간
LIVE_DISPLAY_SEC  = 10  # Live API 코칭 팁 표시 시간
EVENT_DISPLAY_SEC = 10  # 이벤트 알림 표시 시간
