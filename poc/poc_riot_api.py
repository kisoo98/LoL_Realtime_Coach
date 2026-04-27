"""
PoC: League of Legends Live Client Data API 연동
담당: 박창민

LoL 게임 실행 중 로컬 서버(https://127.0.0.1:2999)에서
실시간 게임 데이터를 가져오는 PoC 코드입니다.

실행 방법:
    1. League of Legends 게임을 실행하고 인게임 상태로 진입
    2. python poc/poc_riot_api.py
"""

import requests
import json
import time
import urllib3

# LoL Live Client API는 자체 서명 인증서를 사용하므로 경고 비활성화
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://127.0.0.1:2999/liveclientdata"


def fetch(endpoint: str) -> dict | list | None:
    """Live Client API 엔드포인트 호출 공통 함수"""
    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, verify=False, timeout=3)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        print(f"[ERROR] 게임이 실행 중이지 않거나 API 서버에 연결할 수 없습니다.")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"[ERROR] HTTP 오류: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] 알 수 없는 오류: {e}")
        return None


def get_active_player() -> dict | None:
    """현재 플레이어(본인) 정보 조회"""
    return fetch("activeplayer")


def get_all_players() -> list | None:
    """게임 내 전체 플레이어 목록 조회"""
    return fetch("playerlist")


def get_game_stats() -> dict | None:
    """현재 게임 통계 조회 (시간, 맵 등)"""
    return fetch("gamestats")


def get_events() -> dict | None:
    """게임 이벤트 목록 조회 (킬, 용, 바론 등)"""
    return fetch("eventdata")


def get_all_data() -> dict | None:
    """전체 데이터 한 번에 조회"""
    return fetch("allgamedata")


def print_section(title: str, data) -> None:
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def run_poc():
    print("=== LoL Live Client API PoC ===")
    print("게임 데이터를 가져옵니다...\n")

    # 1. 현재 플레이어 정보
    active_player = get_active_player()
    if active_player:
        print_section("현재 플레이어 (Active Player)", active_player)
    else:
        print("[SKIP] 현재 플레이어 데이터 없음")

    # 2. 전체 플레이어 목록
    all_players = get_all_players()
    if all_players:
        print_section(f"전체 플레이어 목록 ({len(all_players)}명)", all_players)

        # 팀 구분 출력
        print("\n--- 팀 구분 ---")
        for p in all_players:
            team = p.get("team", "?")
            name = p.get("summonerName", "?")
            champion = p.get("championName", "?")
            position = p.get("position", "?")
            print(f"  [{team}] {name} - {champion} ({position})")
    else:
        print("[SKIP] 전체 플레이어 데이터 없음")

    # 3. 게임 통계
    game_stats = get_game_stats()
    if game_stats:
        print_section("게임 통계 (Game Stats)", game_stats)
    else:
        print("[SKIP] 게임 통계 데이터 없음")

    # 4. 게임 이벤트
    events = get_events()
    if events:
        event_list = events.get("Events", [])
        print_section(f"게임 이벤트 (최근 5개 / 전체 {len(event_list)}개)", event_list[-5:])
    else:
        print("[SKIP] 이벤트 데이터 없음")

    print("\n\n=== PoC 완료 ===")


def run_polling(interval_sec: float = 2.0, duration_sec: float = 30.0):
    """
    폴링 모드: 일정 주기로 게임 데이터를 반복 수집
    실제 코칭 앱에서 사용할 패턴 검증용
    """
    print(f"=== 폴링 모드 시작 (주기: {interval_sec}초, 총 {duration_sec}초) ===")
    end_time = time.time() + duration_sec
    poll_count = 0

    while time.time() < end_time:
        poll_count += 1
        data = get_all_data()
        if data is None:
            print(f"[{poll_count}] 데이터 수신 실패 — 게임이 실행 중인지 확인하세요.")
            break

        game_time = data.get("gameData", {}).get("gameTime", 0)
        players = data.get("allPlayers", [])
        events = data.get("events", {}).get("Events", [])

        print(f"[{poll_count}] 게임 시간: {game_time:.1f}초 | 플레이어: {len(players)}명 | 이벤트: {len(events)}건")
        time.sleep(interval_sec)

    print(f"=== 폴링 종료 (총 {poll_count}회 수집) ===")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--poll":
        run_polling()
    else:
        run_poc()
