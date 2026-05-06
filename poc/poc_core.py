"""
poc_core.py — LoL 실시간 코칭 핵심 모듈 (통합본)

통합 대상:
  - all_players_status.py  → 플레이어 상태 파싱 & 출력
  - risk_engine.py         → 위험도 산정 룰 엔진
  - game_monitor.py        → 게임 감지 + 폴링 루프
  - game_watcher.py        → JSON 저장 + 세션 관리

동작:
    1. 게임 감지      → 자동 수집 시작
    2. 매 폴링마다    → game_data_latest.json 갱신 (최신 스냅샷)
    3. 게임 종료      → game_data_YYYYMMDD_HHMMSS.json 저장 (세션 전체)
    4. Ctrl+Shift+Z   → 수집 시작 / 중지 토글
    5. Ctrl+C         → 완전 종료

실행:
    python -m poc.poc_core
"""

import json
import math
import time
import threading
import requests
import urllib3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ════════════════════════════════════════════════
#  설정
# ════════════════════════════════════════════════
BASE_URL       = "https://127.0.0.1:2999/liveclientdata"
POLL_INTERVAL  = 1.0          # 폴링 주기 (초)

# 위험도 엔진 — 미니맵 픽셀 거리 기준
DANGER_RADIUS_HIGH = 60       # 이 안에 적이 있으면 HIGH
DANGER_RADIUS_MID  = 120      # 이 안에 적이 있으면 MID

# JSON 저장 경로
OUTPUT_DIR  = Path(".")
LATEST_FILE = OUTPUT_DIR / "game_data_latest.json"


# ════════════════════════════════════════════════
#  1. Live Client API 호출
# ════════════════════════════════════════════════

def fetch_game_data() -> dict | None:
    """
    게임 데이터 1회 호출.
    게임 미실행 시 None 반환 (예외 발생 안 함).
    """
    try:
        resp = requests.get(
            f"{BASE_URL}/allgamedata",
            verify=False,
            timeout=2,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def get_my_summoner_name() -> str:
    """Live Client API에서 내 소환사명 가져오기."""
    try:
        resp = requests.get(
            f"{BASE_URL}/activeplayername",
            verify=False, timeout=3,
        )
        return resp.json()  # 문자열 바로 반환
    except Exception:
        return "unknown"


# ════════════════════════════════════════════════
#  2. 플레이어 상태 파싱 & 출력  (all_players_status)
# ════════════════════════════════════════════════

def parse_players(data: dict) -> tuple[list, list]:
    """allPlayers를 아군(ORDER) / 적군(CHAOS)으로 분리."""
    allies, enemies = [], []
    active_name = data.get("activePlayer", {}).get("summonerName", "")

    for p in data.get("allPlayers", []):
        info = {
            "name":       p.get("summonerName", "?"),
            "champion":   p.get("championName", "?"),
            "team":       p.get("team", "?"),
            "position":   p.get("position", "?"),
            "level":      p.get("level", 0),
            "is_dead":    p.get("isDead", False),
            "respawn_in": p.get("respawnTimer", 0),
            "is_me":      p.get("summonerName", "") == active_name,
            "scores": {
                "kills":   p.get("scores", {}).get("kills", 0),
                "deaths":  p.get("scores", {}).get("deaths", 0),
                "assists": p.get("scores", {}).get("assists", 0),
                "cs":      p.get("scores", {}).get("creepScore", 0),
            },
            "items": [
                item.get("displayName", "?")
                for item in p.get("items", [])
            ],
        }
        if p.get("team") == "ORDER":
            allies.append(info)
        else:
            enemies.append(info)

    return allies, enemies


def status_icon(player: dict) -> str:
    if player["is_dead"]:
        return f"💀 (부활 {player['respawn_in']:.0f}초)"
    return "✅ 생존"


def print_team(players: list, label: str):
    print(f"\n{'='*56}")
    print(f"  {label}")
    print(f"{'='*56}")

    for p in players:
        me_tag = " ◀ 나" if p["is_me"] else ""
        kda = f"{p['scores']['kills']}/{p['scores']['deaths']}/{p['scores']['assists']}"
        items_str = ", ".join(p["items"]) if p["items"] else "없음"

        print(f"\n  {'★ ' if p['is_me'] else '  '}{p['champion']} ({p['name']}){me_tag}")
        print(f"     상태    : {status_icon(p)}")
        print(f"     레벨    : Lv.{p['level']}")
        print(f"     KDA     : {kda}  |  CS: {p['scores']['cs']}")
        print(f"     포지션  : {p['position']}")
        print(f"     아이템  : {items_str}")


def print_all_players(data: dict):
    """전체 플레이어 상태를 콘솔에 출력."""
    game_time = data.get("gameData", {}).get("gameTime", 0)
    minutes, seconds = divmod(int(game_time), 60)

    print(f"\n[LoL 전체 플레이어 상태] {datetime.now().strftime('%H:%M:%S')}")
    print(f"게임 시간 : {minutes:02d}:{seconds:02d}")

    allies, enemies = parse_players(data)
    print_team(allies, "🔵 아군 (ORDER)")
    print_team(enemies, "🔴 적군 (CHAOS)")
    print(f"\n{'='*56}\n")


# ════════════════════════════════════════════════
#  3. 위험도 산정 룰 엔진  (risk_engine)
# ════════════════════════════════════════════════

@dataclass
class ChampionPosition:
    """YOLO가 넘겨주는 챔피언 위치 정보."""
    name: str
    team: str           # "ally" 또는 "enemy"
    x: float            # 미니맵 픽셀 X 좌표
    y: float            # 미니맵 픽셀 Y 좌표
    confidence: float = 1.0


@dataclass
class RiskResult:
    """UI · LLM에게 넘겨주는 위험도 판정 결과."""
    score: int                        # 0~100
    level: str                        # "LOW" / "MID" / "HIGH"
    text_alert: str
    nearby_enemies: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def get_dead_enemies(game_data: dict, my_name: str) -> list[str]:
    """Live API에서 현재 죽어있는 적 목록 추출 (보조 정보)."""
    dead = []
    for p in game_data.get("allPlayers", []):
        if p.get("summonerName") == my_name:
            continue
        is_enemy = True  # 실제로는 팀 비교 필요, 여기선 단순화
        if is_enemy and p.get("isDead", False):
            dead.append(p.get("championName", "?"))
    return dead


def pixel_distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def calculate_risk(
    my_pos: ChampionPosition,
    all_positions: list[ChampionPosition],
) -> RiskResult:
    """
    미니맵 좌표 기반 위험도 계산.

    Args:
        my_pos        : 나의 미니맵 좌표 (YOLO 제공)
        all_positions : 전체 탐지된 챔피언 좌표 목록 (YOLO 제공)
    """
    score = 0
    reasons = []
    nearby_enemies = []

    enemies = [p for p in all_positions if p.team == "enemy"]

    for enemy in enemies:
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

    score = min(score, 100)

    if score >= 75:
        level = "HIGH"
    elif score >= 50:
        level = "MID"
    else:
        level = "LOW"

    text_alert = _generate_risk_text(level, nearby_enemies)

    return RiskResult(
        score=score,
        level=level,
        text_alert=text_alert,
        nearby_enemies=nearby_enemies,
        reasons=reasons,
    )


def _generate_risk_text(level: str, nearby_enemies: list[str]) -> str:
    if level == "LOW":
        return ""
    names = ", ".join(nearby_enemies) if nearby_enemies else "적군"
    if level == "MID":
        return f"⚠️ 주의! {names} 접근 중"
    if level == "HIGH":
        return f"🚨 위험! {names} 매우 근접 — 즉시 후퇴하세요"
    return ""


def mock_positions() -> tuple[ChampionPosition, list[ChampionPosition]]:
    """YOLO 완성 전 테스트용 가짜 좌표."""
    my_pos = ChampionPosition(name="루시안", team="ally", x=300, y=300)
    all_positions = [
        my_pos,
        ChampionPosition(name="럭스",     team="enemy", x=340, y=310, confidence=0.92),
        ChampionPosition(name="케일",     team="enemy", x=400, y=350, confidence=0.85),
        ChampionPosition(name="에코",     team="enemy", x=600, y=600, confidence=0.90),
        ChampionPosition(name="쉔",       team="ally",  x=280, y=290, confidence=0.88),
        ChampionPosition(name="모르가나", team="ally",  x=310, y=320, confidence=0.80),
    ]
    return my_pos, all_positions


# ════════════════════════════════════════════════
#  4. 게임 감지 + 폴링 루프  (game_monitor)
# ════════════════════════════════════════════════

def is_game_running(data: dict) -> bool:
    """API 응답이 있고 gameTime > 0 이면 게임 진행 중."""
    try:
        return data["gameData"]["gameTime"] > 0
    except Exception:
        return False


def extract_match_info(data: dict) -> dict:
    """게임 시작 시 1회만 추출하는 매치 정보."""
    players = data.get("allPlayers", [])
    my_name = data.get("activePlayer", {}).get("summonerName", "")

    my_team = next(
        (p.get("team", "ORDER") for p in players if p.get("summonerName") == my_name),
        "ORDER",
    )

    allies, enemies = [], []
    for p in players:
        info = {
            "championName": p.get("championName", ""),
            "summonerName": p.get("summonerName", ""),
            "team":         p.get("team", ""),
            "position":     p.get("position", ""),
        }
        if p.get("team") == my_team:
            allies.append(info)
        else:
            enemies.append(info)

    return {
        "my_name":    my_name,
        "my_team":    my_team,
        "allies":     allies,
        "enemies":    enemies,
        "game_mode":  data.get("gameData", {}).get("gameMode", ""),
        "started_at": datetime.now().strftime("%H:%M:%S"),
    }


def extract_live_status(data: dict) -> dict:
    """매 폴링마다 추출하는 실시간 상태 → 위험도 엔진에 전달."""
    players   = data.get("allPlayers", [])
    my_name   = data.get("activePlayer", {}).get("summonerName", "")
    game_time = data.get("gameData", {}).get("gameTime", 0)

    stats = data.get("activePlayer", {}).get("championStats", {})
    hp_ratio = 1.0
    if stats.get("maxHealth", 0) > 0:
        hp_ratio = stats["currentHealth"] / stats["maxHealth"]

    my_team = next(
        (p.get("team", "ORDER") for p in players if p.get("summonerName") == my_name),
        "ORDER",
    )

    enemy_status = []
    for p in players:
        if p.get("team") == my_team:
            continue
        enemy_status.append({
            "championName": p.get("championName", ""),
            "isDead":       p.get("isDead", False),
            "respawnTimer": p.get("respawnTimer", 0),
        })

    return {
        "game_time":    game_time,
        "my_hp_ratio":  round(hp_ratio, 2),
        "enemy_status": enemy_status,
    }


# ── 기본 콜백 ──

def default_on_game_start(match_info: dict):
    print(f"\n🟢 게임 시작 감지! [{match_info['started_at']}]")
    print(f"   내 소환사명 : {match_info['my_name']}")
    print(f"   게임 모드   : {match_info['game_mode']}")
    print(f"   아군 챔피언 : {[p['championName'] for p in match_info['allies']]}")
    print(f"   적군 챔피언 : {[p['championName'] for p in match_info['enemies']]}")


def default_on_poll(live_status: dict, raw_data: dict | None = None):
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
    print("\n🔴 게임 종료 감지 — 루프 중지\n")


# ── 메인 폴링 루프 ──

def run(
    on_game_start=default_on_game_start,
    on_poll=default_on_poll,
    on_game_end=default_on_game_end,
    poll_interval: float = POLL_INTERVAL,
    stop_event: threading.Event | None = None,
):
    """
    게임 감지 → 폴링 → 종료 감지 루프.

    Args:
        on_game_start : 게임 시작 감지 시 1회 호출
        on_poll       : 매 폴링마다 호출
        on_game_end   : 게임 종료 감지 시 1회 호출
        poll_interval : 폴링 주기 (초)
        stop_event    : threading.Event — set() 호출 시 루프 종료
    """
    print("=" * 48)
    print("  LoL 게임 모니터 시작")
    print("  게임이 실행되면 자동으로 감지합니다...")
    print("=" * 48)

    game_active     = False
    match_info_sent = False

    while not (stop_event and stop_event.is_set()):
        data = fetch_game_data()

        if data and is_game_running(data):
            if not game_active:
                game_active     = True
                match_info_sent = False

            if not match_info_sent:
                match_info = extract_match_info(data)
                on_game_start(match_info)
                match_info_sent = True

            live_status = extract_live_status(data)
            on_poll(live_status, data)

        else:
            if game_active:
                game_active     = False
                match_info_sent = False
                on_game_end()

        if stop_event is not None:
            stop_event.wait(timeout=poll_interval)
        else:
            time.sleep(poll_interval)

    print("\n모니터 종료 (stop_event 감지)")


# ════════════════════════════════════════════════
#  5. JSON 저장 + 세션 관리  (game_watcher)
# ════════════════════════════════════════════════

def save_latest(snapshot: dict):
    """최신 스냅샷을 game_data_latest.json에 저장 (매 폴링마다 덮어쓰기)."""
    with open(LATEST_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def save_session(session_log: list, started_at: str) -> Path:
    """게임 세션 전체 기록을 타임스탬프 파일에 저장."""
    filename = OUTPUT_DIR / f"game_data_{started_at}.json"
    payload = {
        "session_start":   started_at,
        "total_snapshots": len(session_log),
        "snapshots":       session_log,
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return filename


def build_callbacks():
    """
    run()에 넘길 콜백 3개를 반환.
    토글로 재시작할 때마다 새로 호출해서 세션 상태를 초기화.
    """
    session_log:  list = []
    session_start: str = ""
    poll_count         = [0]

    def on_game_start(match_info: dict):
        nonlocal session_log, session_start
        session_log   = []
        session_start = datetime.now().strftime("%Y%m%d_%H%M%S")
        poll_count[0] = 0

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
            **(raw_data if raw_data is not None else live_status),
        }
        session_log.append(snapshot)
        save_latest(snapshot)

        m, s = divmod(int(live_status["game_time"]), 60)
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
            LATEST_FILE.unlink()

        print("\n대기 중...\n" + "=" * 60)

    return on_game_start, on_poll, on_game_end


# ════════════════════════════════════════════════
#  직접 실행 시 — Game Watcher 모드
# ════════════════════════════════════════════════

if __name__ == "__main__":
    import keyboard

    TOGGLE_HOTKEY = "ctrl+shift+z"

    _stop_event: threading.Event | None = None
    _thread:     threading.Thread | None = None
    _active = False

    def toggle_monitor():
        global _stop_event, _thread, _active

        if _active:
            _stop_event.set()
            _active = False
            print(f"\n[{TOGGLE_HOTKEY.upper()}] 수집 중지 — 다시 누르면 재시작")
        else:
            on_start, on_poll, on_end = build_callbacks()
            _stop_event = threading.Event()
            _thread = threading.Thread(
                target=run,
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
    print("  LoL Game Watcher (통합 모듈)")
    print(f"  [{TOGGLE_HOTKEY.upper()}] : 수집 시작 / 중지 토글")
    print(f"  Ctrl+C              : 완전 종료")
    print(f"  저장 경로           : {OUTPUT_DIR.resolve()}")
    print("=" * 60)

    toggle_monitor()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        if _stop_event:
            _stop_event.set()
        print("\n완전 종료")
    finally:
        keyboard.remove_hotkey(TOGGLE_HOTKEY)
