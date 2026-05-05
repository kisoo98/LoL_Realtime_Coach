"""
live_data_watcher.py — LoL 게임 자동 감지 + Live Client API 데이터 수집기

실행 방법:
    python live_data_watcher.py

동작:
    1. 게임이 꺼져 있으면 → 자동 대기 (2초마다 확인)
    2. 게임이 켜지면  → 자동으로 Live Client API 폴링 시작
    3. 폴링마다       → game_data_latest.json 갱신 (최신 스냅샷)
    4. 게임이 끝나면  → game_data_YYYYMMDD_HHMMSS.json 저장 후 대기 복귀

저장 파일:
    game_data_latest.json          : 매 폴링마다 덮어쓰는 최신 스냅샷
    game_data_YYYYMMDD_HHMMSS.json : 게임 종료 시 세션 전체 기록

의존성:
    pip install requests urllib3
    pip install psutil   (선택 — 없어도 동작)
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── psutil 선택 의존성 ──────────────────────────
try:
    import psutil
    _PSUTIL_OK = True
except ImportError:
    _PSUTIL_OK = False

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
POLL_INTERVAL  = 1.0   # 게임 중 폴링 주기 (초)
WAIT_INTERVAL  = 2.0   # 게임 미실행 시 재확인 주기 (초)
API_TIMEOUT    = 2.0   # API 요청 타임아웃 (초)
BASE_URL       = "https://127.0.0.1:2999/liveclientdata"

OUTPUT_DIR     = Path(".")                          # JSON 저장 경로 (현재 폴더)
LATEST_FILE    = OUTPUT_DIR / "game_data_latest.json"

LOL_PROCESSES  = {"League of Legends.exe", "LeagueClient.exe"}


# ──────────────────────────────────────────────
# API 호출
# ──────────────────────────────────────────────

def fetch_all_data() -> dict | None:
    """Live Client API 전체 데이터 1회 호출. 실패 시 None 반환."""
    try:
        resp = requests.get(
            f"{BASE_URL}/allgamedata",
            verify=False,
            timeout=API_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


# ──────────────────────────────────────────────
# 게임 실행 감지
# ──────────────────────────────────────────────

def is_lol_running() -> bool:
    """psutil로 LoL 프로세스 확인 (없으면 API로 폴백)."""
    if _PSUTIL_OK:
        try:
            for proc in psutil.process_iter(["name"]):
                if proc.info["name"] in LOL_PROCESSES:
                    return True
            return False
        except Exception:
            pass
    # psutil 없으면 API 응답 여부로 판단
    return fetch_all_data() is not None


def is_ingame(data: dict | None) -> bool:
    """API 응답 데이터로 인게임 여부 확인."""
    if not data:
        return False
    try:
        return float(data["gameData"]["gameTime"]) > 0
    except (KeyError, TypeError, ValueError):
        return False


# ──────────────────────────────────────────────
# JSON 저장
# ──────────────────────────────────────────────

def save_latest(data: dict):
    """최신 스냅샷을 game_data_latest.json에 저장 (매 폴링마다 덮어쓰기)."""
    with open(LATEST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_session(session_log: list[dict], started_at: str):
    """
    게임 세션 전체 기록을 타임스탬프 파일에 저장.
    파일명 예시: game_data_20260427_183045.json
    """
    filename = OUTPUT_DIR / f"game_data_{started_at}.json"
    payload = {
        "session_start": started_at,
        "total_snapshots": len(session_log),
        "snapshots": session_log,
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return filename


# ──────────────────────────────────────────────
# 콘솔 출력 (간략 요약)
# ──────────────────────────────────────────────

def print_status(data: dict, poll_count: int):
    """폴링마다 핵심 정보를 한 줄로 출력."""
    game_time = data.get("gameData", {}).get("gameTime", 0)
    m, s = divmod(int(game_time), 60)

    players    = data.get("allPlayers", [])
    my_name    = data.get("activePlayer", {}).get("summonerName", "?")
    stats      = data.get("activePlayer", {}).get("championStats", {})
    max_hp     = stats.get("maxHealth", 1)
    cur_hp     = stats.get("currentHealth", max_hp)
    hp_pct     = int(cur_hp / max_hp * 100) if max_hp else 100

    dead_enemies = []
    for p in players:
        if p.get("summonerName") == my_name:
            continue
        if p.get("isDead", False):
            dead_enemies.append(p.get("championName", "?"))

    events     = data.get("events", {}).get("Events", [])
    last_event = events[-1].get("EventName", "-") if events else "-"

    print(
        f"  [{poll_count:04d}] {m:02d}:{s:02d} | "
        f"HP: {hp_pct:3d}% | "
        f"사망 적: {dead_enemies if dead_enemies else '없음':20s} | "
        f"최근 이벤트: {last_event}"
    )


# ──────────────────────────────────────────────
# 메인 루프
# ──────────────────────────────────────────────

def run():
    print("=" * 60)
    print("  LoL Live Data Watcher")
    print(f"  psutil 사용 가능: {_PSUTIL_OK}")
    print(f"  폴링 주기: {POLL_INTERVAL}초")
    print(f"  저장 경로: {OUTPUT_DIR.resolve()}")
    print("  게임이 시작되면 자동으로 수집을 시작합니다...")
    print("  종료: Ctrl+C")
    print("=" * 60)

    game_active    = False
    session_log: list[dict] = []
    session_start  = ""
    poll_count     = 0

    while True:
        # ── 게임 미실행 대기 ──────────────────
        if not game_active:
            if not is_lol_running():
                print(f"\r  대기 중... ({datetime.now().strftime('%H:%M:%S')})", end="", flush=True)
                time.sleep(WAIT_INTERVAL)
                continue

            # 프로세스는 있지만 인게임 진입 전일 수 있음 → API 확인
            data = fetch_all_data()
            if not is_ingame(data):
                print(f"\r  LoL 실행 감지, 인게임 대기 중...", end="", flush=True)
                time.sleep(WAIT_INTERVAL)
                continue

            # ── 게임 시작 ──────────────────────
            game_active   = True
            session_log   = []
            poll_count    = 0
            session_start = datetime.now().strftime("%Y%m%d_%H%M%S")

            my_name  = data.get("activePlayer", {}).get("summonerName", "?")
            my_team  = next(
                (p.get("team") for p in data.get("allPlayers", [])
                 if p.get("summonerName") == my_name),
                "?"
            )
            game_mode = data.get("gameData", {}).get("gameMode", "?")

            print(f"\n\n🟢 게임 시작 감지! [{datetime.now().strftime('%H:%M:%S')}]")
            print(f"   소환사명 : {my_name}")
            print(f"   내 팀    : {my_team}")
            print(f"   게임 모드: {game_mode}")
            print(f"   세션 ID  : {session_start}")
            print("-" * 60)

        # ── 인게임 폴링 ───────────────────────
        data = fetch_all_data()

        if not is_ingame(data):
            # ── 게임 종료 ──────────────────────
            game_active = False

            if session_log:
                saved = save_session(session_log, session_start)
                print(f"\n\n🔴 게임 종료 감지!")
                print(f"   총 수집: {len(session_log)}개 스냅샷")
                print(f"   저장됨: {saved}")
            else:
                print(f"\n\n🔴 게임 종료 (데이터 없음)")

            if LATEST_FILE.exists():
                LATEST_FILE.unlink()  # 최신 파일 정리

            print("\n대기 상태로 복귀...\n")
            print("=" * 60)
            continue

        # 데이터 수집
        poll_count += 1
        snapshot = {
            "poll_index": poll_count,
            "collected_at": datetime.now().isoformat(),
            **data,
        }
        session_log.append(snapshot)

        # 최신 스냅샷 저장
        save_latest(snapshot)

        # 콘솔 출력
        print_status(data, poll_count)

        time.sleep(POLL_INTERVAL)


# ──────────────────────────────────────────────
# 실행
# ──────────────────────────────────────────────

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n\n수집 중지 (Ctrl+C)")
