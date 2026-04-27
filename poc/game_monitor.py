"""
game_monitor.py — 게임 감지 + 폴링 루프

역할:
  1. LoL 게임 시작 감지 → 김대원/한승우에게 트리거 신호 전송
  2. 1초마다 Live Client API 폴링 → 위험도 엔진에 데이터 전달
  3. 게임 종료 감지 → 루프 중지

연결 구조:
  [이 파일] ──게임시작 트리거──▶ 김대원(승률 그래프 생성) + 한승우(오버레이 시작)
  [이 파일] ──플레이어 데이터──▶ risk_engine.py (황기수 YOLO 결과와 합산)
  [이 파일] ──게임종료 신호──▶ 한승우(오버레이 종료)
"""

import time
import requests
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL    = "https://127.0.0.1:2999/liveclientdata"
POLL_INTERVAL = 1.0   # 초 — 너무 빠르면 CPU 부담, 너무 느리면 반응 지연


# ──────────────────────────────────────────────
# Live Client API 호출
# ──────────────────────────────────────────────
def fetch_game_data() -> dict | None:
    """
    게임 데이터 1회 호출.
    게임 미실행 시 None 반환 (예외 발생 안 함).
    """
    try:
        resp = requests.get(
            f"{BASE_URL}/allgamedata",
            verify=False,
            timeout=2
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


# ──────────────────────────────────────────────
# 게임 상태 판단
# ──────────────────────────────────────────────
def is_game_running(data: dict) -> bool:
    """API 응답이 있고 gameTime > 0 이면 게임 진행 중"""
    try:
        return data["gameData"]["gameTime"] > 0
    except Exception:
        return False


def extract_match_info(data: dict) -> dict:
    """
    게임 시작 시 1회만 추출하는 매치 정보.
    → 김대원(승률 그래프) + 한승우(오버레이 초기화)에게 전달
    """
    players = data.get("allPlayers", [])
    my_name = data.get("activePlayer", {}).get("summonerName", "")

    allies  = []
    enemies = []

    for p in players:
        info = {
            "championName": p.get("championName", ""),
            "summonerName": p.get("summonerName", ""),
            "team":         p.get("team", ""),
            "position":     p.get("position", ""),
        }
        if p.get("summonerName") == my_name:
            my_team = p.get("team", "ORDER")

        if p.get("team") == "ORDER":
            allies.append(info)
        else:
            enemies.append(info)

    return {
        "my_name":   my_name,
        "allies":    allies,   # 아군 5명 챔피언 정보
        "enemies":   enemies,  # 적군 5명 챔피언 정보
        "game_mode": data.get("gameData", {}).get("gameMode", ""),
        "started_at": datetime.now().strftime("%H:%M:%S"),
    }


def extract_live_status(data: dict) -> dict:
    """
    매 폴링마다 추출하는 실시간 상태.
    → risk_engine.py 위험도 엔진에 전달 (YOLO 좌표와 합산)
    """
    players  = data.get("allPlayers", [])
    my_name  = data.get("activePlayer", {}).get("summonerName", "")
    game_time = data.get("gameData", {}).get("gameTime", 0)

    # 내 체력 비율
    stats = data.get("activePlayer", {}).get("championStats", {})
    hp_ratio = 1.0
    if stats.get("maxHealth", 0) > 0:
        hp_ratio = stats["currentHealth"] / stats["maxHealth"]

    # 적군 생사 상태 (미싱 보조 판단용)
    enemy_status = []
    for p in players:
        if p.get("summonerName") == my_name:
            continue
        # 내 팀과 다른 팀 = 적군
        enemy_status.append({
            "championName": p.get("championName", ""),
            "isDead":       p.get("isDead", False),
            "respawnTimer": p.get("respawnTimer", 0),
        })

    return {
        "game_time":    game_time,
        "my_hp_ratio":  round(hp_ratio, 2),   # 0.0~1.0
        "enemy_status": enemy_status,          # 적군 생사 정보
    }


# ──────────────────────────────────────────────
# 콜백 함수 (한승우/황기수/김대원가 구현해서 넘겨줌)
# ──────────────────────────────────────────────
def default_on_game_start(match_info: dict):
    """게임 시작 시 호출 — 한승우·김대원이 실제 함수로 교체"""
    print(f"\n🟢 게임 시작 감지! [{match_info['started_at']}]")
    print(f"   내 소환사명 : {match_info['my_name']}")
    print(f"   게임 모드   : {match_info['game_mode']}")
    print(f"   아군 챔피언 : {[p['championName'] for p in match_info['allies']]}")
    print(f"   적군 챔피언 : {[p['championName'] for p in match_info['enemies']]}")
    print(f"   → 김대원: 승률 그래프 생성 트리거 ✅")
    print(f"   → 한승우: 오버레이 시작 트리거 ✅\n")


def default_on_poll(live_status: dict):
    """매 폴링마다 호출 — risk_engine과 연결되는 자리"""
    m, s = divmod(int(live_status["game_time"]), 60)
    dead_enemies = [
        e["championName"] for e in live_status["enemy_status"] if e["isDead"]
    ]
    print(
        f"[{m:02d}:{s:02d}] "
        f"내 체력: {live_status['my_hp_ratio']*100:.0f}%  |  "
        f"사망한 적: {dead_enemies if dead_enemies else '없음'}"
    )


def default_on_game_end():
    """게임 종료 시 호출 — 한승우가 오버레이 종료에 연결"""
    print("\n🔴 게임 종료 감지 — 루프 중지\n")


# ──────────────────────────────────────────────
# 메인 폴링 루프
# ──────────────────────────────────────────────
def run(
    on_game_start = default_on_game_start,
    on_poll       = default_on_poll,
    on_game_end   = default_on_game_end,
    poll_interval: float = POLL_INTERVAL,
):
    """
    Args:
        on_game_start : 게임 시작 감지 시 1회 호출  → 김대원·한승우 연결
        on_poll       : 매 폴링마다 호출             → risk_engine 연결
        on_game_end   : 게임 종료 감지 시 1회 호출  → 한승우 연결
        poll_interval : 폴링 주기 (초)
    """
    print("=" * 48)
    print("  LoL 게임 모니터 시작")
    print("  게임이 실행되면 자동으로 감지합니다...")
    print("=" * 48)

    game_active    = False   # 현재 게임 진행 중 여부
    match_info_sent = False  # 게임 시작 트리거를 이미 보냈는지

    while True:
        data = fetch_game_data()

        if data and is_game_running(data):
            # ── 게임 시작 감지 (최초 1회)
            if not game_active:
                game_active     = True
                match_info_sent = False

            if not match_info_sent:
                match_info = extract_match_info(data)
                on_game_start(match_info)
                match_info_sent = True

            # ── 매 폴링: 실시간 상태 추출 → risk_engine 전달
            live_status = extract_live_status(data)
            on_poll(live_status)

        else:
            # ── 게임 종료 감지
            if game_active:
                game_active     = False
                match_info_sent = False
                on_game_end()

        time.sleep(poll_interval)


# ──────────────────────────────────────────────
# 직접 실행 시 테스트
# ──────────────────────────────────────────────
if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n모니터 종료 (Ctrl+C)")
