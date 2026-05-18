"""
규칙 기반 코칭 팁 / 이벤트 팁 생성.

Live Client API의 게임 데이터(체력, 골드, 게임 시간, 이벤트)를 받아
사람이 읽기 좋은 짧은 한글 팁 문자열을 만든다. TTS 전달 시에는
이모지를 strip_emoji() 로 제거해서 보낸다.
"""
from __future__ import annotations

# 화면에는 표시하되 TTS에는 빼고 싶은 이모지 모음
_EMOJI = "🛑💰💡⏰🐉🪱👁🟣🔍⚔️🛡🔥💀🏰🤝🩸"


def strip_emoji(text: str) -> str:
    """TTS 입력용 — 시각용 이모지를 제거."""
    for ch in _EMOJI:
        text = text.replace(ch, "")
    return text.strip()


def make_coaching_tip(hp_pct: float, gold: float, game_time: float) -> str:
    """체력/게임시간 기반 규칙 팁.

    [정책] 골드 보유량 기반 팁은 화면/TTS 모두 출력하지 않는다 — 사용자가
    이미 인게임 HUD로 확인 가능한 정보이므로 알림 가치가 낮음.
    조건에 해당 없으면 빈 문자열 반환 (TTS 잡음 방지).
    """
    if hp_pct <= 20:
        return "🛑 체력 20% 이하! 귀환을 고려하세요."
    # 골드 팁(💰/💡)은 의도적으로 제외 — 사용자 요구사항.
    if game_time < 100:
        return "🔍 초반 시야를 확보하세요."
    # NOTE: "14분 포탑방패 소멸" 팁 제거 (2026-05-17).
    # 해당 메커니즘은 패치로 사라진 구식 룰 — 포탑 방패는 영구 소멸하지 않는다.
    if 1170 < game_time < 1260:
        return "🟣 20분 — 바론 시야 장악 준비!"
    return ""  # 기본 팁 제거 — 의미 없는 반복 TTS 방지


def make_event_tip(ev: dict, my_name: str) -> str:
    """Live Client API 이벤트 객체 → 짧은 알림 문구. 매칭 안 되면 빈 문자열.

    [정책] 챔피언 킬/데스/퍼스트블러드는 화면/TTS 모두 출력하지 않는다.
    이는 사용자가 인게임 알림으로 이미 확인 가능한 정보이므로 알림 가치가 낮음.
    오브젝트(용/포탑/바론) 처치는 전략 판단에 유용해 유지.
    """
    et = ev.get("EventName", "")
    # 챔피언 킬/데스/퍼스트블러드는 의도적으로 제외 — 사용자 요구사항.
    if et == "DragonKill":
        return "🐉 용 처치 — 다음 용 타이머 체크."
    if et == "TurretKilled":
        return "🏰 포탑 파괴 — 로밍 기회!"
    if et == "BaronKill":
        return "🟣 바론 처치! 라인 밀기 집중."
    return ""
