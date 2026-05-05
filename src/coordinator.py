"""
coordinator.py — 데이터 변환 허브

담당: 박창민

역할:
  YOLO 탐지 결과(좌표) + Live Client API 데이터(플레이어 상태)를
  risk_analyzer.py의 RiskAnalyzer.calculate_risk()가 요구하는
  표준 입력 형식으로 변환

데이터 흐름:
  황기수(YOLO 탐지) ──yolo_frame──┐
                                  ▼
  박창민(Live Client) ─live_status─┤
                                  ▼
                          [coordinator.py]
                                  │
                    ┌─────────────┴──────────────┐
                    ▼                            ▼
             risk_analyzer.py              debug 출력
             calculate_risk(summary)

입력 형식 상세: docs/COORDINATE_SPEC.md 참고
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List, Optional

from src.coord_parser import CoordParser, class_to_track_key, DEFAULT_MINIMAP_BBOX_1080P


# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
DEFAULT_CONFIDENCE_THRESHOLD = 0.5   # 이 값 미만의 YOLO 탐지는 무시
DEAD_ENEMY_WEIGHT_FACTOR     = 0.0   # 사망한 적 위험도 기여 비율 (0 = 완전 제외)
SUMMARY_WINDOW_SECONDS       = 5.0   # RiskAnalyzer에 전달할 시간 윈도우 크기


class Coordinator:
    """
    YOLO + Live Client 데이터를 합산하여 RiskAnalyzer 입력 생성

    사용 예시:
        coord = Coordinator(minimap_bbox=(1625, 815, 1920, 1080))

        # Live Client 업데이트 (DataCollector.on_poll 콜백에서 호출)
        coord.update_live_status(live_status)

        # YOLO 프레임 처리 (detector.py 콜백에서 호출)
        summary = coord.process_yolo_frame(yolo_frame)

        # RiskAnalyzer에 전달
        risk_score = risk_analyzer.calculate_risk(summary)
    """

    def __init__(
        self,
        minimap_bbox: tuple = DEFAULT_MINIMAP_BBOX_1080P,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        summary_window: float = SUMMARY_WINDOW_SECONDS,
    ):
        self._parser   = CoordParser(bbox=minimap_bbox)
        self._conf_thr = confidence_threshold
        self._window   = summary_window

        # Live Client에서 받은 최신 상태 (비동기 업데이트)
        self._live_status: Optional[dict] = None
        self._match_info:  Optional[dict] = None

        # 슬라이딩 윈도우 트랙 버퍼 [(timestamp, x, y), ...]
        self._track_buffer: Dict[str, List] = defaultdict(list)

    # ── Live Client 업데이트 ───────────────────

    def update_live_status(self, live_status: dict):
        """
        DataCollector.on_poll 콜백에서 호출.
        매 폴링(500ms)마다 Live Client 최신 상태를 저장.
        """
        self._live_status = live_status

    def update_match_info(self, match_info: dict):
        """
        DataCollector.on_game_start 콜백에서 호출.
        게임 시작 시 1회 저장 (팀 구성, 내 팀 정보 등).
        """
        self._match_info = match_info
        self._track_buffer.clear()

    # ── YOLO 프레임 처리 ──────────────────────

    def process_yolo_frame(self, yolo_frame: dict) -> dict:
        """
        YOLO 탐지 1프레임을 처리하여 RiskAnalyzer 입력 형식(summary)으로 변환.

        Args:
            yolo_frame: YOLO 탐지 결과 프레임
                {
                    "frame_time": float,   # time.time()
                    "game_time":  float,   # Live Client gameTime (선택)
                    "detections": [
                        {
                            "class": "red_jungle",
                            "pixel_x": 1780,   # 또는 이미 정규화된 "x"
                            "pixel_y": 950,
                            "confidence": 0.91,
                        }, ...
                    ]
                }

        Returns:
            RiskAnalyzer.calculate_risk(summary) 입력 형식:
                {
                    "frames":   int,
                    "duration": float,
                    "tracks": {
                        "enemy_champion": [[rel_time, x, y], ...],
                        "ally_champion":  [[rel_time, x, y], ...],
                        ...
                    }
                }
        """
        my_team = "ORDER"
        if self._live_status:
            my_team = self._live_status.get("my_team", "ORDER")
        elif self._match_info:
            my_team = self._match_info.get("my_team", "ORDER")

        dead_enemies = self._get_dead_enemy_names()
        frame_time = yolo_frame.get("frame_time", time.time())

        # 1. 이번 프레임 탐지를 버퍼에 추가
        parsed = self._parser.parse_detections(yolo_frame.get("detections", []))
        for det in parsed:
            conf = det.get("confidence", 1.0)
            if conf < self._conf_thr:
                continue

            x = det.get("x")
            y = det.get("y")
            if x is None or y is None:
                continue

            # 사망한 적 필터링
            champion_name = det.get("champion", "")
            if champion_name in dead_enemies:
                continue

            track_key = class_to_track_key(det.get("class", ""), my_team)
            self._track_buffer[track_key].append((frame_time, x, y))

        # 2. 오래된 데이터 정리 (슬라이딩 윈도우)
        cutoff = frame_time - self._window
        for key in list(self._track_buffer.keys()):
            self._track_buffer[key] = [
                entry for entry in self._track_buffer[key]
                if entry[0] >= cutoff
            ]

        # 3. RiskAnalyzer 입력 형식으로 변환
        return self._build_summary(frame_time)

    def _build_summary(self, current_time: float) -> dict:
        """
        트랙 버퍼 → RiskAnalyzer summary 형식 변환
        시각을 절대 time에서 '윈도우 내 상대 시각'으로 변환
        """
        if not self._track_buffer:
            return {"frames": 0, "duration": 0.0, "tracks": {}}

        # 윈도우 시작 시각
        all_times = [entry[0] for entries in self._track_buffer.values() for entry in entries]
        if not all_times:
            return {"frames": 0, "duration": 0.0, "tracks": {}}

        window_start = min(all_times)
        duration = current_time - window_start
        total_frames = sum(len(v) for v in self._track_buffer.values())

        # 상대 시각으로 변환
        tracks = {}
        for key, entries in self._track_buffer.items():
            if entries:
                tracks[key] = [
                    [entry[0] - window_start, entry[1], entry[2]]
                    for entry in entries
                ]

        return {
            "frames":   total_frames,
            "duration": round(duration, 3),
            "tracks":   tracks,
        }

    # ── Live Client 보조 정보 ─────────────────

    def _get_dead_enemy_names(self) -> set:
        """현재 사망 중인 적 챔피언 이름 집합 반환"""
        if not self._live_status:
            return set()
        return {
            e["championName"]
            for e in self._live_status.get("enemy_status", [])
            if e.get("isDead", False)
        }

    def get_live_context(self) -> dict:
        """
        LLM 코칭 호출 시 컨텍스트로 활용할 수 있는 현재 게임 상태 요약.
        황기수(LLM caller)가 사용.
        """
        if not self._live_status:
            return {}

        ls = self._live_status
        dead_enemies  = [e["championName"] for e in ls.get("enemy_status", []) if e.get("isDead")]
        alive_enemies = [e["championName"] for e in ls.get("enemy_status", []) if not e.get("isDead")]

        return {
            "game_time":     ls.get("game_time", 0),
            "my_hp_ratio":   ls.get("my_hp_ratio", 1.0),
            "my_team":       ls.get("my_team", "ORDER"),
            "dead_enemies":  dead_enemies,
            "alive_enemies": alive_enemies,
            "timestamp":     ls.get("timestamp", 0),
        }

    def reset(self):
        """게임 종료 시 상태 초기화"""
        self._live_status = None
        self._match_info  = None
        self._track_buffer.clear()


# ──────────────────────────────────────────────
# 통합 빌더 — DataCollector + Coordinator 연결
# ──────────────────────────────────────────────

def build_collector_coordinator(
    minimap_bbox: tuple = DEFAULT_MINIMAP_BBOX_1080P,
    on_summary_ready: callable = None,
):
    """
    DataCollector와 Coordinator를 연결하는 편의 함수.

    사용 예시:
        def handle_summary(summary, context):
            score = risk_analyzer.calculate_risk(summary)
            print(f"위험도: {score:.1f}")

        collector, coord = build_collector_coordinator(
            on_summary_ready=handle_summary
        )
        collector.start()
    """
    from src.data_collector import DataCollector

    coord = Coordinator(minimap_bbox=minimap_bbox)

    def on_start(match_info):
        coord.update_match_info(match_info)
        print(f"[Coordinator] 게임 시작 — 내 팀: {match_info.get('my_team', '?')}")

    def on_poll(live_status):
        coord.update_live_status(live_status)

    def on_end():
        coord.reset()
        print("[Coordinator] 게임 종료 — 상태 초기화")

    collector = DataCollector(
        on_game_start=on_start,
        on_poll=on_poll,
        on_game_end=on_end,
    )

    return collector, coord


# ──────────────────────────────────────────────
# 단독 실행 테스트
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import json

    print("=== Coordinator 변환 테스트 ===\n")

    coord = Coordinator()

    # Mock live_status (사망한 적 포함)
    mock_live = {
        "game_time":    342.5,
        "my_hp_ratio":  0.85,
        "my_team":      "ORDER",
        "enemy_status": [
            {"championName": "직스",  "isDead": True,  "respawnTimer": 12.3},
            {"championName": "뽀삐",  "isDead": False, "respawnTimer": 0.0},
            {"championName": "세라핀","isDead": False, "respawnTimer": 0.0},
        ],
        "ally_status": [],
        "timestamp": time.time(),
    }
    coord.update_live_status(mock_live)

    # Mock YOLO 프레임 (픽셀 좌표)
    mock_yolo = {
        "frame_time": time.time(),
        "game_time":  342.5,
        "detections": [
            {"class": "red_jungle",  "pixel_x": 1780, "pixel_y": 950, "confidence": 0.91},
            {"class": "red_adc",     "pixel_x": 1700, "pixel_y": 900, "confidence": 0.85},
            {"class": "blue_mid",    "pixel_x": 1770, "pixel_y": 948, "confidence": 0.78},
            {"class": "red_mid",     "pixel_x": 1800, "pixel_y": 820, "confidence": 0.30},  # conf 낮음 → 제외
        ],
    }

    summary = coord.process_yolo_frame(mock_yolo)
    print("RiskAnalyzer 입력 (summary):")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    print("\nLLM 컨텍스트:")
    print(json.dumps(coord.get_live_context(), indent=2, ensure_ascii=False))
