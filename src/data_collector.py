"""
data_collector.py — Live Client API 폴링 루프 + 게임 자동 감지

담당: 박창민

역할:
  1. LoL 게임 자동 감지 (프로세스 감지 + API 응답 이중 확인)
  2. 게임 실행 전부터 대기 → 게임 시작 시 자동으로 수집 시작
  3. 500ms 주기로 Live Client API 폴링
  4. 수집 데이터를 coordinator.py에 전달 가능한 형식으로 출력

연결 구조:
  [이 파일] ──live_status──▶ coordinator.py ──▶ risk_analyzer.py
  [이 파일] ──match_info──▶ 한승우(오버레이 초기화) · 김대원(승률 그래프)

게임 감지 방식:
  1차: psutil 프로세스 감지 ("League of Legends.exe") — 빠르지만 옵션
  2차: Live Client API 응답 기반 감지 — 항상 동작 (psutil 없어도 됨)
"""

from __future__ import annotations

import time
import threading
from datetime import datetime
from typing import Callable, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# psutil은 선택 의존성 — 없어도 API 기반 감지로 동작
try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

# ──────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────
BASE_URL          = "https://127.0.0.1:2999/liveclientdata"
LOL_PROCESS_NAMES = {"League of Legends.exe", "LeagueClient.exe", "LeagueClientUx.exe"}

DEFAULT_POLL_INTERVAL   = 0.5   # 초 (500ms)
DEFAULT_WAIT_INTERVAL   = 2.0   # 게임 미실행 시 재확인 주기
REQUEST_TIMEOUT         = 2.0   # API 요청 타임아웃


# ──────────────────────────────────────────────
# 게임 감지 유틸
# ──────────────────────────────────────────────

def is_lol_process_running() -> bool:
    """
    psutil로 LoL 프로세스 실행 여부 확인 (1차 감지).
    psutil 미설치 시 항상 False 반환 → API 기반 감지로 폴백.
    """
    if not _PSUTIL_AVAILABLE:
        return False
    try:
        for proc in psutil.process_iter(["name"]):
            if proc.info["name"] in LOL_PROCESS_NAMES:
                return True
    except Exception:
        pass
    return False


def fetch_live_data() -> Optional[dict]:
    """
    Live Client API 단일 호출.
    게임 미실행 또는 오류 시 None 반환.
    """
    try:
        resp = requests.get(
            f"{BASE_URL}/allgamedata",
            verify=False,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def is_game_active(data: Optional[dict]) -> bool:
    """API 응답 데이터로 게임 진행 중 여부 확인"""
    if not data:
        return False
    try:
        return float(data["gameData"]["gameTime"]) > 0
    except (KeyError, TypeError, ValueError):
        return False


# ──────────────────────────────────────────────
# 데이터 추출 함수
# ──────────────────────────────────────────────

def extract_match_info(data: dict) -> dict:
    """
    게임 시작 시 1회 추출하는 매치 정보.
    → 한승우(오버레이 초기화) · 김대원(승률 그래프 생성) 전달용
    """
    my_name = data.get("activePlayer", {}).get("summonerName", "")
    players = data.get("allPlayers", [])

    allies, enemies = [], []
    my_team = "ORDER"

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
        "my_name":    my_name,
        "my_team":    my_team,        # "ORDER" | "CHAOS" — 좌표 팀 판별에 필요
        "allies":     allies,
        "enemies":    enemies,
        "game_mode":  data.get("gameData", {}).get("gameMode", ""),
        "started_at": datetime.now().strftime("%H:%M:%S"),
    }


def extract_live_status(data: dict) -> dict:
    """
    매 폴링마다 추출하는 실시간 상태.
    → coordinator.py를 통해 risk_analyzer.py로 전달

    Returns:
        {
            "game_time":    float,   # 게임 경과 시간(초)
            "my_hp_ratio":  float,   # 내 체력 비율 0.0~1.0
            "my_team":      str,     # "ORDER" | "CHAOS"
            "enemy_status": [        # 적군 생사 정보
                {
                    "championName": str,
                    "isDead":       bool,
                    "respawnTimer": float,
                    "team":         str,
                }
            ],
            "ally_status":  [...],   # 아군 생사 정보 (동일 구조)
            "timestamp":    float,   # 수집 시각 (time.time())
        }
    """
    players    = data.get("allPlayers", [])
    my_name    = data.get("activePlayer", {}).get("summonerName", "")
    game_time  = data.get("gameData", {}).get("gameTime", 0.0)

    # 내 팀 파악
    my_team = "ORDER"
    for p in players:
        if p.get("summonerName") == my_name:
            my_team = p.get("team", "ORDER")
            break

    enemy_team_name = "CHAOS" if my_team == "ORDER" else "ORDER"

    # 내 체력 비율
    stats    = data.get("activePlayer", {}).get("championStats", {})
    max_hp   = stats.get("maxHealth", 1.0)
    cur_hp   = stats.get("currentHealth", max_hp)
    hp_ratio = round(cur_hp / max_hp, 3) if max_hp > 0 else 1.0

    # 플레이어 상태 분리
    enemy_status, ally_status = [], []
    for p in players:
        if p.get("summonerName") == my_name:
            continue
        entry = {
            "championName": p.get("championName", ""),
            "summonerName": p.get("summonerName", ""),
            "isDead":       p.get("isDead", False),
            "respawnTimer": p.get("respawnTimer", 0.0),
            "team":         p.get("team", ""),
            "level":        p.get("level", 1),
        }
        if p.get("team") == enemy_team_name:
            enemy_status.append(entry)
        else:
            ally_status.append(entry)

    return {
        "game_time":    float(game_time),
        "my_hp_ratio":  hp_ratio,
        "my_name":      my_name,
        "my_team":      my_team,
        "enemy_status": enemy_status,
        "ally_status":  ally_status,
        "timestamp":    time.time(),
    }


# ──────────────────────────────────────────────
# DataCollector 클래스
# ──────────────────────────────────────────────

class DataCollector:
    """
    Live Client API 폴링 + 게임 자동 감지 메인 클래스

    사용 예시:
        def on_start(match_info):
            print("게임 시작!", match_info["my_name"])

        def on_poll(live_status):
            coordinator.process(live_status)

        collector = DataCollector(on_game_start=on_start, on_poll=on_poll)
        collector.start()
        # ... (메인 루프)
        collector.stop()
    """

    def __init__(
        self,
        on_game_start: Callable[[dict], None] = None,
        on_poll:       Callable[[dict], None] = None,
        on_game_end:   Callable[[], None]     = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        wait_interval: float = DEFAULT_WAIT_INTERVAL,
    ):
        """
        Args:
            on_game_start : 게임 시작 감지 시 1회 호출 → match_info 전달
            on_poll       : 매 폴링마다 호출 → live_status 전달
            on_game_end   : 게임 종료 감지 시 1회 호출
            poll_interval : 게임 중 폴링 주기 (기본 0.5초)
            wait_interval : 게임 미실행 시 재확인 주기 (기본 2.0초)
        """
        self._on_game_start = on_game_start or self._default_on_start
        self._on_poll       = on_poll       or self._default_on_poll
        self._on_game_end   = on_game_end   or self._default_on_end

        self._poll_interval = poll_interval
        self._wait_interval = wait_interval

        self._running        = False
        self._thread: Optional[threading.Thread] = None
        self._game_active    = False
        self._match_notified = False

    # ── 공개 API ───────────────────────────────

    def start(self, blocking: bool = False):
        """
        수집 시작.
        blocking=True면 현재 스레드에서 루프 실행 (Ctrl+C로 중지).
        blocking=False면 백그라운드 스레드로 실행.
        """
        self._running = True
        if blocking:
            self._run_loop()
        else:
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self):
        """수집 중지"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    @property
    def is_game_active(self) -> bool:
        return self._game_active

    # ── 내부 루프 ──────────────────────────────

    def _run_loop(self):
        print("=" * 50)
        print("  LoL 게임 모니터 대기 중...")
        print("  게임 시작 시 자동으로 수집을 시작합니다.")
        print("=" * 50)

        while self._running:
            # 1차: 프로세스 감지 (빠름, psutil 필요)
            process_detected = is_lol_process_running()

            # 2차: API 응답 감지 (항상 동작)
            data = fetch_live_data() if (process_detected or not _PSUTIL_AVAILABLE) else None
            if data is None and process_detected:
                # 프로세스는 있지만 게임 아직 로딩 중
                time.sleep(self._wait_interval)
                continue

            game_running = is_game_active(data)

            if game_running:
                self._game_active = True

                # 게임 시작 트리거 (최초 1회)
                if not self._match_notified:
                    match_info = extract_match_info(data)
                    try:
                        self._on_game_start(match_info)
                    except Exception as e:
                        print(f"[DataCollector] on_game_start 오류: {e}")
                    self._match_notified = True

                # 매 폴링: 실시간 상태 추출
                live_status = extract_live_status(data)
                try:
                    self._on_poll(live_status)
                except Exception as e:
                    print(f"[DataCollector] on_poll 오류: {e}")

                time.sleep(self._poll_interval)

            else:
                # 게임 종료 또는 미실행
                if self._game_active:
                    self._game_active    = False
                    self._match_notified = False
                    try:
                        self._on_game_end()
                    except Exception as e:
                        print(f"[DataCollector] on_game_end 오류: {e}")

                time.sleep(self._wait_interval)

    # ── 기본 콜백 ──────────────────────────────

    @staticmethod
    def _default_on_start(match_info: dict):
        print(f"\n🟢 게임 시작 감지! [{match_info.get('started_at', '')}]")
        print(f"   소환사명 : {match_info.get('my_name', '?')}")
        print(f"   내 팀    : {match_info.get('my_team', '?')}")
        print(f"   게임 모드: {match_info.get('game_mode', '?')}")
        allies  = [p["championName"] for p in match_info.get("allies", [])]
        enemies = [p["championName"] for p in match_info.get("enemies", [])]
        print(f"   아군     : {allies}")
        print(f"   적군     : {enemies}\n")

    @staticmethod
    def _default_on_poll(live_status: dict):
        gt = live_status.get("game_time", 0)
        m, s = divmod(int(gt), 60)
        hp   = live_status.get("my_hp_ratio", 1.0) * 100
        dead = [e["championName"] for e in live_status.get("enemy_status", []) if e.get("isDead")]
        print(f"[{m:02d}:{s:02d}] HP: {hp:.0f}%  |  사망 적: {dead or '없음'}")

    @staticmethod
    def _default_on_end():
        print("\n🔴 게임 종료 감지 — 수집 중지\n")


# ──────────────────────────────────────────────
# 단독 실행 테스트
# ──────────────────────────────────────────────
if __name__ == "__main__":
    print(f"psutil 사용 가능: {_PSUTIL_AVAILABLE}")
    print(f"기본 폴링 주기: {DEFAULT_POLL_INTERVAL}초\n")

    collector = DataCollector()
    try:
        collector.start(blocking=True)
    except KeyboardInterrupt:
        collector.stop()
        print("\n수집 중지 (Ctrl+C)")
