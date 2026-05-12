"""
Riot Games Live Client Data API 연동 모듈
===========================================
리그 오브 레전드 게임이 진행 중일 때, 로컬에서 실행되는 Live Client Data API를 통해
현재 게임에 참여 중인 10명의 챔피언, 포지션, 게임 이벤트 등을 실시간으로 가져옵니다.

API 기본 주소: https://127.0.0.1:2999
(게임이 실행 중이어야만 접근 가능합니다)
"""

import requests
import urllib3
import time
import json

# Riot Live Client API는 자체 서명 인증서(Self-signed cert)를 사용하므로
# SSL 경고를 비활성화합니다.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://127.0.0.1:2999"


def _get(endpoint):
    """Live Client API에 GET 요청을 보내고 JSON을 반환합니다."""
    url = f"{BASE_URL}{endpoint}"
    try:
        response = requests.get(url, verify=False, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        print("[Live API] 게임이 실행 중이 아닙니다. 롤 인게임 상태에서만 사용할 수 있습니다.")
        return None
    except requests.exceptions.Timeout:
        print("[Live API] 응답 시간 초과")
        return None
    except Exception as e:
        print(f"[Live API] 요청 실패: {e}")
        return None


# ─────────────────────────────────────────────
# 1. 전체 게임 데이터 (한 번에 모든 정보)
# ─────────────────────────────────────────────
def get_all_game_data():
    """모든 게임 데이터를 한 번에 가져옵니다."""
    return _get("/liveclientdata/allgamedata")


# ─────────────────────────────────────────────
# 2. 현재 플레이어 (나 자신) 정보
# ─────────────────────────────────────────────
def get_active_player():
    """현재 내가 조종하는 챔피언의 상세 정보를 반환합니다.
    (능력치, 레벨, 골드 등)"""
    return _get("/liveclientdata/activeplayer")


# ─────────────────────────────────────────────
# 3. 10명 전체 플레이어 리스트
# ─────────────────────────────────────────────
def get_player_list():
    """게임에 참여 중인 10명 전원의 정보를 리스트로 반환합니다.
    각 플레이어에는 championName, team, position, scores 등이 포함됩니다."""
    return _get("/liveclientdata/playerlist")


# ─────────────────────────────────────────────
# 4. 게임 이벤트 (킬, 포탑 파괴, 드래곤 처치 등)
# ─────────────────────────────────────────────
def get_event_data():
    """발생한 모든 게임 이벤트 목록을 반환합니다.
    예: GameStart, ChampionKill, TurretKilled, DragonKill 등"""
    return _get("/liveclientdata/eventdata")


# ─────────────────────────────────────────────
# 5. 게임 통계 (경과 시간, 맵 정보 등)
# ─────────────────────────────────────────────
def get_game_stats():
    """현재 게임의 기본 통계(경과 시간, 맵 이름, 게임 모드)를 반환합니다."""
    return _get("/liveclientdata/gamestats")


# ─────────────────────────────────────────────
# 유틸리티: 보기 좋게 정리된 요약 출력
# ─────────────────────────────────────────────
def print_player_summary():
    """10명의 챔피언과 포지션을 팀별로 정리하여 출력합니다."""
    players = get_player_list()
    if players is None:
        return

    # 포지션 한글 매핑
    pos_kr = {
        "TOP": "탑",
        "JUNGLE": "정글",
        "MIDDLE": "미드",
        "BOTTOM": "원딜",
        "UTILITY": "서폿",
        "": "미지정"
    }

    blue_team = [p for p in players if p.get("team") == "ORDER"]
    red_team = [p for p in players if p.get("team") == "CHAOS"]

    print("\n" + "=" * 50)
    print("         🔵 블루 팀 (ORDER)")
    print("=" * 50)
    for p in blue_team:
        pos = pos_kr.get(p.get("position", ""), p.get("position", ""))
        champ = p.get("championName", "???")
        name = p.get("summonerName", "???")
        scores = p.get("scores", {})
        kills = scores.get("kills", 0)
        deaths = scores.get("deaths", 0)
        assists = scores.get("assists", 0)
        cs = scores.get("creepScore", 0)
        print(f"  [{pos:>3}] {champ:<16} | {name:<20} | KDA: {kills}/{deaths}/{assists} | CS: {cs}")

    print("\n" + "=" * 50)
    print("         🔴 레드 팀 (CHAOS)")
    print("=" * 50)
    for p in red_team:
        pos = pos_kr.get(p.get("position", ""), p.get("position", ""))
        champ = p.get("championName", "???")
        name = p.get("summonerName", "???")
        scores = p.get("scores", {})
        kills = scores.get("kills", 0)
        deaths = scores.get("deaths", 0)
        assists = scores.get("assists", 0)
        cs = scores.get("creepScore", 0)
        print(f"  [{pos:>3}] {champ:<16} | {name:<20} | KDA: {kills}/{deaths}/{assists} | CS: {cs}")

    print()


def print_event_summary():
    """게임 이벤트를 시간순으로 보기 좋게 출력합니다."""
    data = get_event_data()
    if data is None:
        return

    events = data.get("Events", [])
    if not events:
        print("\n아직 발생한 이벤트가 없습니다.")
        return

    # 이벤트 타입 한글 매핑
    event_kr = {
        "GameStart": "🎮 게임 시작",
        "MinionsSpawning": "🐛 미니언 스폰",
        "FirstBrick": "🧱 퍼스트 블러드 타워",
        "TurretKilled": "🏰 포탑 파괴",
        "InhibKilled": "💎 억제기 파괴",
        "DragonKill": "🐉 드래곤 처치",
        "HeraldKill": "👁️ 전령 처치",
        "BaronKill": "👑 바론 처치",
        "ChampionKill": "⚔️ 챔피언 처치",
        "Multikill": "🔥 멀티킬",
        "Ace": "💀 에이스",
        "FirstBlood": "🩸 퍼스트 블러드",
        "InhibRespawningSoon": "💎 억제기 곧 부활",
        "InhibRespawned": "💎 억제기 부활",
        "GameEnd": "🏆 게임 종료",
    }

    print("\n" + "=" * 60)
    print("              📋 게임 이벤트 타임라인")
    print("=" * 60)

    for evt in events:
        event_type = evt.get("EventName", "Unknown")
        event_time = evt.get("EventTime", 0)
        minutes = int(event_time) // 60
        seconds = int(event_time) % 60

        label = event_kr.get(event_type, event_type)

        # 세부 정보 추가
        detail = ""
        if event_type == "ChampionKill":
            killer = evt.get("KillerName", "?")
            victim = evt.get("VictimName", "?")
            assisters = evt.get("Assisters", [])
            assist_str = f" (어시스트: {', '.join(assisters)})" if assisters else ""
            detail = f" → {killer} 이(가) {victim} 처치{assist_str}"
        elif event_type == "TurretKilled":
            turret = evt.get("TurretKilled", "?")
            killer = evt.get("KillerName", "?")
            detail = f" → {turret} | 파괴자: {killer}"
        elif event_type == "DragonKill":
            killer = evt.get("KillerName", "?")
            dragon = evt.get("DragonType", "?")
            detail = f" → {dragon} 드래곤 | 처치자: {killer}"
        elif event_type == "BaronKill":
            killer = evt.get("KillerName", "?")
            detail = f" → 처치자: {killer}"
        elif event_type == "Multikill":
            killer = evt.get("KillerName", "?")
            kill_streak = evt.get("KillStreak", 0)
            detail = f" → {killer} ({kill_streak}연속 처치!)"

        print(f"  [{minutes:02d}:{seconds:02d}] {label}{detail}")

    print()


# ─────────────────────────────────────────────
# 메인: 직접 실행하면 현재 게임 정보를 출력
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  🎮 Riot Live Client Data API - 실시간 게임 정보 조회")
    print("=" * 60)

    # 게임 기본 정보
    stats = get_game_stats()
    if stats:
        game_time = stats.get("gameTime", 0)
        minutes = int(game_time) // 60
        seconds = int(game_time) % 60
        game_mode = stats.get("gameMode", "???")
        map_name = stats.get("mapName", "???")
        print(f"\n📍 맵: {map_name} | 모드: {game_mode} | 경과 시간: {minutes}분 {seconds}초")

    # 10명 챔피언 & 포지션 출력
    print_player_summary()

    # 게임 이벤트 타임라인 출력
    print_event_summary()

    # 내 캐릭터 정보
    me = get_active_player()
    if me:
        print("=" * 50)
        print("         🧑‍💻 내 캐릭터 정보")
        print("=" * 50)
        print(f"  소환사명: {me.get('summonerName', '???')}")
        print(f"  레벨: {me.get('level', '?')}")
        print(f"  골드: {me.get('currentGold', '?'):.0f}")
        print()
