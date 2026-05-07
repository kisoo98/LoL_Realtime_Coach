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
    """체력/골드/게임시간 기반 규칙 팁."""
    if hp_pct <= 20:
        return "🛑 체력 20% 이하! 귀환을 고려하세요."
    if gold >= 1500:
        return f"💰 {int(gold)} 골드 — 코어 아이템 구매 타이밍!"
    if gold >= 1100 and game_time < 600:
        return f"💡 {int(gold)} 골드 — 하위템 구매 후 압박하세요."
    if game_time < 100:
        return "🔍 초반 시야를 확보하세요."
    if 810 < game_time < 870:
        return "⏰ 14분 — 타워 방패 소멸 타이밍!"
    if 1170 < game_time < 1260:
        return "🟣 20분 — 바론 시야 장악 준비!"
    return "미니맵을 수시로 확인하세요."


def make_event_tip(ev: dict, my_name: str) -> str:
    """Live Client API 이벤트 객체 → 짧은 알림 문구. 매칭 안 되면 빈 문자열."""
    et     = ev.get("EventName", "")
    killer = ev.get("KillerName", "")
    victim = ev.get("VictimName", "")
    if et == "ChampionKill":
        if killer == my_name:
            return "🔥 킬! 라인 밀고 귀환 타이밍 잡으세요."
        if victim == my_name:
            return "💀 데스. 상대 스펠 브리핑하세요."
        return f"⚔️ {killer} → {victim} 처치"
    if et == "DragonKill":
        return "🐉 용 처치 — 다음 용 타이머 체크."
    if et == "TurretKilled":
        return "🏰 포탑 파괴 — 로밍 기회!"
    if et == "BaronKill":
        return "🟣 바론 처치! 라인 밀기 집중."
    if et == "FirstBlood":
        return "🩸 퍼스트 블러드 발생!"
    return ""
