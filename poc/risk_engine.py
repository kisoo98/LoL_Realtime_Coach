"""
risk_engine.py — 위험도 산정 룰 엔진 v1

흐름:
  황기수(YOLO) → minimap_positions 딕셔너리 →  [이 파일]  → risk 결과
  한승우(UI)   ←────────────────────────────────────────────────────

미니맵 좌표 기준:
  - 1920x1080 기준 미니맵은 우측 하단 약 (1580~1920, 780~1080) 영역
  - YOLO가 챔피언 아이콘 중심점을 픽셀 좌표로 넘겨줌
  - 이 엔진은 그 좌표만 받아서 거리 계산 → 위험도 판정
"""

import math
import requests
import urllib3
from dataclasses import dataclass, field

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ──────────────────────────────────────────────
# 설정값 (나중에 컨트롤 UI 슬라이더와 연동)
# ──────────────────────────────────────────────
DANGER_RADIUS_HIGH = 60   # 픽셀 — 이 안에 적이 있으면 HIGH
DANGER_RADIUS_MID  = 120  # 픽셀 — 이 안에 적이 있으면 MID


# ──────────────────────────────────────────────
# 데이터 타입 정의 (황기수님과 인터페이스 합의용)
# ──────────────────────────────────────────────
@dataclass
class ChampionPosition:
    """YOLO가 넘겨주는 챔피언 위치 정보"""
    name: str           # 챔피언 이름 (예: "럭스")
    team: str           # "ally" 또는 "enemy"
    x: float            # 미니맵 픽셀 X 좌표
    y: float            # 미니맵 픽셀 Y 좌표
    confidence: float = 1.0  # YOLO 탐지 신뢰도 (0.0~1.0)

@dataclass
class RiskResult:
    """한승우(UI) · 황기수(LLM)에게 넘겨주는 결과"""
    score: int                        # 0~100 위험도 점수
    level: str                        # "LOW" / "MID" / "HIGH"
    text_alert: str                   # 중간 위험도용 텍스트 메시지
    nearby_enemies: list[str] = field(default_factory=list)  # 근처 적 챔피언 이름들
    reasons: list[str] = field(default_factory=list)         # LLM 프롬프트용 이유 목록


# ──────────────────────────────────────────────
# Live Client API — 내 챔피언 이름 가져오기
# ──────────────────────────────────────────────
def get_my_summoner_name() -> str:
    try:
        resp = requests.get(
            "https://127.0.0.1:2999/liveclientdata/activeplayername",
            verify=False, timeout=3
        )
        return resp.json()  # 문자열 바로 반환
    except Exception:
        return "unknown"

def get_dead_enemies(game_data: dict, my_name: str) -> list[str]:
    """Live API에서 현재 죽어있는 적 목록 추출 (보조 정보)"""
    dead = []
    for p in game_data.get("allPlayers", []):
        if p.get("summonerName") == my_name:
            continue
        # 팀 판별: activePlayer 기준 반대 팀
        is_enemy = True  # 실제로는 팀 비교 필요, 여기선 단순화
        if is_enemy and p.get("isDead", False):
            dead.append(p.get("championName", "?"))
    return dead


# ──────────────────────────────────────────────
# 핵심 로직
# ──────────────────────────────────────────────
def pixel_distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def calculate_risk(
    my_pos: ChampionPosition,
    all_positions: list[ChampionPosition],
) -> RiskResult:
    """
    Args:
        my_pos        : 나의 미니맵 좌표 (YOLO 제공)
        all_positions : 전체 탐지된 챔피언 좌표 목록 (YOLO 제공)

    Returns:
        RiskResult    : 위험도 판정 결과
    """
    score = 0
    reasons = []
    nearby_enemies = []

    enemies = [p for p in all_positions if p.team == "enemy"]

    for enemy in enemies:
        # 신뢰도 낮은 탐지는 무시 (YOLO 오탐 필터)
        if enemy.confidence < 0.5:
            continue

        dist = pixel_distance(my_pos.x, my_pos.y, enemy.x, enemy.y)

        if dist <= DANGER_RADIUS_HIGH:
            score += 40
            nearby_enemies.append(enemy.name)
            reasons.append(f"{enemy.name} 매우 근접 (거리: {dist:.0f}px)")

        elif dist <= DANGER_RADIUS_MID:
            score += 20
            nearby_enemies.append(enemy.name)
            reasons.append(f"{enemy.name} 근접 (거리: {dist:.0f}px)")

    # 점수 상한 100
    score = min(score, 100)

    # 위험도 단계 분류
    if score >= 75:
        level = "HIGH"
    elif score >= 50:
        level = "MID"
    else:
        level = "LOW"

    # 중간 위험도 텍스트 생성 (한승우 UI에 표시)
    text_alert = _generate_text(level, nearby_enemies)

    return RiskResult(
        score=score,
        level=level,
        text_alert=text_alert,
        nearby_enemies=nearby_enemies,
        reasons=reasons,
    )


def _generate_text(level: str, nearby_enemies: list[str]) -> str:
    if level == "LOW":
        return ""
    names = ", ".join(nearby_enemies) if nearby_enemies else "적군"
    if level == "MID":
        return f"⚠️ 주의! {names} 접근 중"
    if level == "HIGH":
        return f"🚨 위험! {names} 매우 근접 — 즉시 후퇴하세요"
    return ""


# ──────────────────────────────────────────────
# 테스트용 Mock 실행
# (황기수님 YOLO 모듈 완성 전까지 이걸로 개발)
# ──────────────────────────────────────────────
def mock_positions() -> tuple[ChampionPosition, list[ChampionPosition]]:
    """
    실제 미니맵 좌표 대신 가짜 좌표로 테스트.
    황기수님 YOLO 완성 후 이 함수를 YOLO 출력으로 교체하면 됨.
    """
    my_pos = ChampionPosition(name="루시안", team="ally", x=300, y=300)

    all_positions = [
        my_pos,
        ChampionPosition(name="럭스",     team="enemy", x=340, y=310, confidence=0.92),  # 가까움 → HIGH
        ChampionPosition(name="케일",     team="enemy", x=400, y=350, confidence=0.85),  # 중간 → MID
        ChampionPosition(name="에코",     team="enemy", x=600, y=600, confidence=0.90),  # 멀리 → 무시
        ChampionPosition(name="쉔",       team="ally",  x=280, y=290, confidence=0.88),  # 아군 → 무시
        ChampionPosition(name="모르가나", team="ally",  x=310, y=320, confidence=0.80),  # 아군 → 무시
    ]
    return my_pos, all_positions


if __name__ == "__main__":
    print("=== 위험도 엔진 v1 테스트 ===\n")
    print(f"HIGH 판정 반경 : {DANGER_RADIUS_HIGH}px")
    print(f"MID  판정 반경 : {DANGER_RADIUS_MID}px\n")

    my_pos, all_positions = mock_positions()

    print(f"내 위치  : ({my_pos.x}, {my_pos.y})")
    print(f"탐지된 챔피언 수 : {len(all_positions)}명\n")

    result = calculate_risk(my_pos, all_positions)

    print(f"──────────────────────────")
    print(f"위험도 점수 : {result.score} / 100")
    print(f"위험도 단계 : {result.level}")
    print(f"근처 적군   : {', '.join(result.nearby_enemies) if result.nearby_enemies else '없음'}")
    print(f"알림 메시지 : {result.text_alert if result.text_alert else '(없음)'}")
    print(f"\n[판정 근거]")
    for r in result.reasons:
        print(f"  - {r}")
    print(f"──────────────────────────")
    print(f"\n※ LLM(황기수)에게 넘길 데이터: reasons={result.reasons}")
    print(f"※ UI(한승우)에게 넘길 데이터 : level='{result.level}', text='{result.text_alert}'")
