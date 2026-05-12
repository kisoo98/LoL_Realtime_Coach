"""
Live Client API 폴링 스레드.

Riot Live Client API(localhost:2999) 에서 1초 단위로 게임 상태를 가져와
 - 내 챔피언 영문명 → champ_signal로 발사 (YOLO 스레드에 전달)
 - 코칭 팁 / 이벤트 팁 → update_signal에 dict로 발사
"""
from __future__ import annotations

import time

from PyQt6.QtCore import QThread, pyqtSignal
from loguru import logger

from poc.integrated_helpers import parse_raw_champ_name
from poc.integrated_tips import make_coaching_tip, make_event_tip, strip_emoji

# ── Live Client API 모듈 (poc/live_game.py) ─────────────────────────────────
try:
    import poc.live_game as live_game
    LIVE_API_AVAILABLE = True
except Exception:
    try:
        import live_game  # poc/ 안에서 직접 실행할 때 fallback
        LIVE_API_AVAILABLE = True
    except Exception as _err:  # pragma: no cover
        print(f"[경고] live_game 로드 실패: {_err}")
        LIVE_API_AVAILABLE = False


class LiveClientThread(QThread):
    """Live Client API 폴링 + 코칭/이벤트 팁 발사 스레드."""

    update_signal = pyqtSignal(dict)
    # 챔피언 영문명을 YoloCoachThread에 넘기기 위한 시그널
    champ_signal  = pyqtSignal(str)
    # 게임의 10명 챔피언 리스트를 YoloCoachThread에 넘기기 위한 시그널 (필터링용)
    champ_list_signal = pyqtSignal(set)  # {"Aatrox", "Ahri", ...}

    def __init__(self):
        super().__init__()
        self.running = True
        self.last_event_count = 0
        self._last_coaching_tip = ""
        self._last_event_tip    = ""

    def run(self) -> None:
        if not LIVE_API_AVAILABLE:
            self.update_signal.emit({
                "status": "waiting",
                "msg": "Live Client API 모듈 없음 (게임 외부)",
            })
            return

        last_champ_emitted = ""

        while self.running:
            try:
                data = live_game.get_all_game_data()
                if not data:
                    self.update_signal.emit({
                        "status": "waiting",
                        "msg": "롤 게임 진입 대기 중...",
                    })
                    time.sleep(2)
                    continue

                active_player = data.get("activePlayer", {})
                all_players   = data.get("allPlayers", [])
                events        = data.get("events", {}).get("Events", [])
                stats         = data.get("gameData", {})

                # 내 챔피언 영문명 + 10명 챔피언 리스트 → YOLO 스레드로 ──────
                my_name = active_player.get("summonerName", "")
                my_champ_en = ""
                all_champs = set()  # 게임의 10명 챔피언 리스트

                for p in all_players:
                    # 챔피언명 추출 (rawChampionName 우선, 없으면 championName)
                    raw = p.get("rawChampionName", "")
                    champ_name = (
                        parse_raw_champ_name(raw) if raw
                        else p.get("championName", "")
                    )

                    if champ_name:
                        all_champs.add(champ_name)

                    # 내 챔피언 찾기
                    if p.get("summonerName") == my_name:
                        my_champ_en = champ_name

                # 내 챔피언 변경 감지 → 시그널 전송
                if my_champ_en and my_champ_en != last_champ_emitted:
                    last_champ_emitted = my_champ_en
                    self.champ_signal.emit(my_champ_en)
                    logger.info(f"내 챔피언: {my_champ_en}")

                # 10명 챔피언 리스트 → 필터링용 시그널 전송
                if all_champs:
                    self.champ_list_signal.emit(all_champs)
                    logger.debug(f"게임 챔피언: {sorted(all_champs)}")

                # 스탯 ────────────────────────────────────────────────────
                champ_stats = active_player.get("championStats", {})
                max_hp   = champ_stats.get("maxHealth", 1)
                curr_hp  = champ_stats.get("currentHealth", 1)
                hp_pct   = (curr_hp / max_hp) * 100 if max_hp > 0 else 100
                gold      = active_player.get("currentGold", 0)
                game_time = stats.get("gameTime", 0)

                # 규칙 기반 코칭 팁 ─────────────────────────────────────────
                tip = make_coaching_tip(hp_pct, gold, game_time)

                # 이벤트 알림 ──────────────────────────────────────────────
                event_tip = ""
                if len(events) > self.last_event_count:
                    ev = events[-1]
                    event_tip = make_event_tip(ev, my_name)
                    self.last_event_count = len(events)

                # 중복 제거 ────────────────────────────────────────────────
                new_tip = tip if tip != self._last_coaching_tip else None
                new_ev  = event_tip if event_tip and event_tip != self._last_event_tip else None
                if new_tip:
                    self._last_coaching_tip = tip
                if new_ev:
                    self._last_event_tip = event_tip

                speeches = []
                if new_tip:
                    speeches.append(strip_emoji(new_tip))
                if new_ev:
                    speeches.append(strip_emoji(new_ev))

                self.update_signal.emit({
                    "status":           "ingame",
                    "new_coaching_tip": new_tip,
                    "event_tip":        new_ev,
                    "speeches":         speeches,
                })

            except Exception as e:
                logger.debug(f"Live API 오류: {e}")

            time.sleep(1)

    def stop(self) -> None:
        self.running = False
        self.wait()
