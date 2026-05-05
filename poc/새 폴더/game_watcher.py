"""
game_watcher.py — 게임 감지 + 실시간 데이터 수집 + JSON 저장 통합본

game_monitor.py (폴링 엔진) + live_data_watcher.py (JSON 저장) 를 하나로 묶은 파일.
원본 파일은 그대로 유지됨.

동작:
    1. 게임 감지      → 자동 수집 시작
    2. 매 폴링마다    → game_data_latest.json 갱신 (최신 스냅샷)
    3. 게임 종료      → game_data_YYYYMMDD_HHMMSS.json 저장 (세션 전체)
    4. Ctrl+Shift+Z   → 수집 시작 / 중지 토글 (게임 풀스크린 중에도 동작)
    5. Ctrl+C         → 완전 종료

실행:
    python game_watcher.py

저장 파일:
    game_data_latest.json          : 매 폴링마다 덮어쓰는 최신 스냅샷
    game_data_YYYYMMDD_HHMMSS.json : 게임 종료 시 세션 전체 기록
"""

import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# 어디서 실행하든 프로젝트 루트를 sys.path에 추가
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from poc.game_monitor import run as monitor_run

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
OUTPUT_DIR  = Path(".")
LATEST_FILE = OUTPUT_DIR / "game_data_latest.json"


# ──────────────────────────────────────────────
# JSON 저장
# ──────────────────────────────────────────────

def save_latest(snapshot: dict):
    """최신 스냅샷을 game_data_latest.json에 저장 (매 폴링마다 덮어쓰기)."""
    with open(LATEST_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def save_session(session_log: list, started_at: str) -> Path:
    """게임 세션 전체 기록을 타임스탬프 파일에 저장."""
    filename = OUTPUT_DIR / f"game_data_{started_at}.json"
    payload = {
        "session_start":    started_at,
        "total_snapshots":  len(session_log),
        "snapshots":        session_log,
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return filename


# ──────────────────────────────────────────────
# 콜백 세트 — 게임 세션 상태를 클로저로 관리
# ──────────────────────────────────────────────

def build_callbacks():
    """
    game_monitor.run()에 넘길 콜백 3개를 반환.
    토글로 재시작할 때마다 새로 호출해서 세션 상태를 초기화.
    """
    session_log:   list = []
    session_start: str  = ""
    poll_count         = [0]   # 클로저에서 수정 가능한 컨테이너

    def on_game_start(match_info: dict):
        nonlocal session_log, session_start
        session_log    = []
        session_start  = datetime.now().strftime("%Y%m%d_%H%M%S")
        poll_count[0]  = 0

        print(f"\n🟢 게임 시작! [{match_info['started_at']}]")
        print(f"   소환사명 : {match_info['my_name']}")
        print(f"   내 팀    : {match_info.get('my_team', '?')}")
        print(f"   아군     : {[p['championName'] for p in match_info['allies']]}")
        print(f"   적군     : {[p['championName'] for p in match_info['enemies']]}")
        print(f"   게임모드 : {match_info['game_mode']}")
        print("-" * 60)

    def on_poll(live_status: dict, raw_data: dict | None = None):
        poll_count[0] += 1
        snapshot = {
            "poll_index":   poll_count[0],
            "collected_at": datetime.now().isoformat(),
            # raw_data 우선 저장 (전체 API 응답), 없으면 live_status만 저장
            **(raw_data if raw_data is not None else live_status),
        }
        session_log.append(snapshot)
        save_latest(snapshot)

        # 콘솔 요약 출력 (live_status 기준)
        m, s  = divmod(int(live_status["game_time"]), 60)
        dead  = [e["championName"] for e in live_status["enemy_status"] if e["isDead"]]
        print(
            f"  [{poll_count[0]:04d}] {m:02d}:{s:02d} | "
            f"HP: {live_status['my_hp_ratio'] * 100:.0f}% | "
            f"사망한 적: {dead if dead else '없음'}"
        )

    def on_game_end():
        if session_log:
            saved = save_session(session_log, session_start)
            print(f"\n🔴 게임 종료! 총 {len(session_log)}개 스냅샷 저장 → {saved}")
        else:
            print("\n🔴 게임 종료 (데이터 없음)")

        if LATEST_FILE.exists():
            LATEST_FILE.unlink()   # 임시 파일 정리

        print("\n대기 중...\n" + "=" * 60)

    return on_game_start, on_poll, on_game_end


# ──────────────────────────────────────────────
# 실행
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import keyboard

    TOGGLE_HOTKEY = "ctrl+shift+z"

    _stop_event: threading.Event | None  = None
    _thread:     threading.Thread | None = None
    _active = False

    def toggle_monitor():
        global _stop_event, _thread, _active

        if _active:
            # 실행 중 → 중지
            _stop_event.set()
            _active = False
            print(f"\n[{TOGGLE_HOTKEY.upper()}] 수집 중지 — 다시 누르면 재시작")
        else:
            # 중지 중 → 시작 (콜백 새로 생성해서 세션 상태 초기화)
            on_start, on_poll, on_end = build_callbacks()
            _stop_event = threading.Event()
            _thread = threading.Thread(
                target=monitor_run,
                kwargs={
                    "on_game_start": on_start,
                    "on_poll":       on_poll,
                    "on_game_end":   on_end,
                    "stop_event":    _stop_event,
                },
                daemon=True,
            )
            _thread.start()
            _active = True
            print(f"\n[{TOGGLE_HOTKEY.upper()}] 수집 시작 — 다시 누르면 중지")

    keyboard.add_hotkey(TOGGLE_HOTKEY, toggle_monitor)

    print("=" * 60)
    print("  LoL Game Watcher")
    print(f"  [{TOGGLE_HOTKEY.upper()}] : 수집 시작 / 중지 토글")
    print(f"  Ctrl+C              : 완전 종료")
    print(f"  저장 경로           : {OUTPUT_DIR.resolve()}")
    print("=" * 60)

    toggle_monitor()   # 자동 시작

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        if _stop_event:
            _stop_event.set()
        print("\n완전 종료")
    finally:
        keyboard.remove_hotkey(TOGGLE_HOTKEY)
