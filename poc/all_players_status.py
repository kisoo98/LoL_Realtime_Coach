import requests
import urllib3
import json
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://127.0.0.1:2999/liveclientdata"


def fetch_game_data() -> dict:
    resp = requests.get(f"{BASE_URL}/allgamedata", verify=False, timeout=3)
    resp.raise_for_status()
    return resp.json()


def parse_players(data: dict) -> tuple[list, list]:
    """allPlayers를 아군(ORDER) / 적군(CHAOS)으로 분리"""
    allies, enemies = [], []
    active_name = data.get("activePlayer", {}).get("summonerName", "")

    for p in data.get("allPlayers", []):
        info = {
            "name":       p.get("summonerName", "?"),
            "champion":   p.get("championName", "?"),
            "team":       p.get("team", "?"),          # ORDER / CHAOS
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


def main():
    print(f"\n[LoL 전체 플레이어 상태] {datetime.now().strftime('%H:%M:%S')}")

    try:
        data = fetch_game_data()
    except requests.exceptions.ConnectionError:
        print("\n❌ 게임에 연결할 수 없어요. LoL이 실행 중인지 확인하세요.")
        return
    except requests.exceptions.Timeout:
        print("\n❌ 응답 시간 초과. 다시 시도해 주세요.")
        return

    game_time = data.get("gameData", {}).get("gameTime", 0)
    minutes, seconds = divmod(int(game_time), 60)
    print(f"게임 시간 : {minutes:02d}:{seconds:02d}")

    allies, enemies = parse_players(data)

    print_team(allies, "🔵 아군 (ORDER)")
    print_team(enemies, "🔴 적군 (CHAOS)")

    print(f"\n{'='*56}\n")

    # 원본 JSON도 저장 (디버깅용)
    with open("game_snapshot.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("📄 전체 데이터 → game_snapshot.json 저장 완료")


if __name__ == "__main__":
    main()
