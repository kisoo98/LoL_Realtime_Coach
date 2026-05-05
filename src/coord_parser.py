"""
coord_parser.py — 미니맵 픽셀 좌표 ↔ 정규화 좌표 변환 유틸

담당: 박창민

역할:
  - YOLO가 출력하는 절대 픽셀 좌표를 0.0~1.0 정규화 비율로 변환
  - 해상도/설정이 바뀌어도 minimap_bbox 값만 바꾸면 동작
  - 좌표 스펙 상세: docs/COORDINATE_SPEC.md 참고

좌표 기준:
  (0.0, 0.0) = 미니맵 좌상단 (블루팀 기지 방향)
  (1.0, 1.0) = 미니맵 우하단 (레드팀 기지 방향)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


# ──────────────────────────────────────────────
# 기본 미니맵 bbox (config.yaml 기준)
# 실제 사용 시 settings.py에서 읽어서 CoordParser에 주입
# ──────────────────────────────────────────────
DEFAULT_MINIMAP_BBOX_1080P = (1625, 815, 1920, 1080)  # left, top, right, bottom


@dataclass
class NormalizedCoord:
    """0.0~1.0 정규화 미니맵 좌표"""
    x: float  # 가로 비율 (0=좌, 1=우)
    y: float  # 세로 비율 (0=위, 1=아래)

    def __post_init__(self):
        self.x = float(max(0.0, min(1.0, self.x)))
        self.y = float(max(0.0, min(1.0, self.y)))

    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)

    def __repr__(self) -> str:
        return f"NormalizedCoord(x={self.x:.3f}, y={self.y:.3f})"


class CoordParser:
    """
    픽셀 좌표 ↔ 정규화 좌표 변환기

    사용 예시:
        parser = CoordParser(bbox=(1625, 815, 1920, 1080))
        norm = parser.pixel_to_norm(pixel_x=1780, pixel_y=950)
        # → NormalizedCoord(x=0.528, y=0.511)
    """

    def __init__(self, bbox: Tuple[int, int, int, int] = DEFAULT_MINIMAP_BBOX_1080P):
        """
        Args:
            bbox: 미니맵 영역 (left, top, right, bottom) — 픽셀 절대 좌표
                  config.yaml의 capture.resolutions.*.minimap_bbox 값과 동일
        """
        left, top, right, bottom = bbox
        self._left   = left
        self._top    = top
        self._width  = right - left
        self._height = bottom - top

        if self._width <= 0 or self._height <= 0:
            raise ValueError(f"유효하지 않은 bbox: {bbox}")

    # ── 픽셀 → 정규화 ──────────────────────────

    def pixel_to_norm(self, pixel_x: float, pixel_y: float) -> NormalizedCoord:
        """
        절대 픽셀 좌표 → 미니맵 내 정규화 좌표 (0~1)

        Args:
            pixel_x: 화면 절대 X 픽셀
            pixel_y: 화면 절대 Y 픽셀

        Returns:
            NormalizedCoord (자동으로 0~1 클램핑)
        """
        norm_x = (pixel_x - self._left) / self._width
        norm_y = (pixel_y - self._top)  / self._height
        return NormalizedCoord(x=norm_x, y=norm_y)

    def pixel_to_norm_tuple(self, pixel_x: float, pixel_y: float) -> Tuple[float, float]:
        """픽셀 → (norm_x, norm_y) 튜플 반환 (편의 메서드)"""
        coord = self.pixel_to_norm(pixel_x, pixel_y)
        return coord.to_tuple()

    # ── 정규화 → 픽셀 ──────────────────────────

    def norm_to_pixel(self, norm_x: float, norm_y: float) -> Tuple[int, int]:
        """
        정규화 좌표 → 절대 픽셀 좌표 (디버그/시각화용)

        Args:
            norm_x, norm_y: 0.0~1.0 정규화 좌표

        Returns:
            (pixel_x, pixel_y) 절대 좌표
        """
        px = int(self._left + norm_x * self._width)
        py = int(self._top  + norm_y * self._height)
        return (px, py)

    # ── YOLO 검출 결과 일괄 변환 ───────────────

    def parse_detections(self, raw_detections: list[dict]) -> list[dict]:
        """
        YOLO 검출 결과 리스트에서 픽셀 좌표를 정규화 좌표로 일괄 변환

        Args:
            raw_detections: YOLO 원본 출력 리스트
                [
                  {
                    "class": "red_jungle",
                    "pixel_x": 1780,
                    "pixel_y": 950,
                    "confidence": 0.91,
                    ...
                  }, ...
                ]

        Returns:
            정규화 좌표 포함된 검출 결과 리스트
                [
                  {
                    "class": "red_jungle",
                    "x": 0.528,
                    "y": 0.511,
                    "confidence": 0.91,
                    ...
                  }, ...
                ]
        """
        result = []
        for det in raw_detections:
            px = det.get("pixel_x") or det.get("x_pixel")
            py = det.get("pixel_y") or det.get("y_pixel")

            if px is None or py is None:
                # 이미 정규화 좌표인 경우 그대로 사용
                result.append(det)
                continue

            norm = self.pixel_to_norm(px, py)
            parsed = {**det, "x": norm.x, "y": norm.y}
            result.append(parsed)

        return result

    def __repr__(self) -> str:
        return (
            f"CoordParser(bbox=({self._left}, {self._top}, "
            f"{self._left + self._width}, {self._top + self._height}))"
        )


# ──────────────────────────────────────────────
# YOLO 클래스명 → 팀 매핑 유틸
# docs/COORDINATE_SPEC.md 섹션 5 참고
# ──────────────────────────────────────────────

BLUE_CLASSES = {"blue_top", "blue_jungle", "blue_mid", "blue_adc", "blue_support"}
RED_CLASSES  = {"red_top",  "red_jungle",  "red_mid",  "red_adc",  "red_support"}


def class_to_team(yolo_class: str, my_team: str = "ORDER") -> str:
    """
    YOLO 클래스명과 내 팀 정보로 실제 팀(ally/enemy) 결정

    Args:
        yolo_class: YOLO 클래스명 (예: "red_jungle", "blue_mid")
        my_team:    내 팀 — Live Client API 기준 "ORDER"(블루) / "CHAOS"(레드)

    Returns:
        "ally" | "enemy" | "neutral"
    """
    if yolo_class in BLUE_CLASSES:
        return "ally" if my_team == "ORDER" else "enemy"
    elif yolo_class in RED_CLASSES:
        return "enemy" if my_team == "ORDER" else "ally"
    else:
        return "neutral"  # ward, objective 등


def class_to_track_key(yolo_class: str, my_team: str = "ORDER") -> str:
    """
    YOLO 클래스 → RiskAnalyzer.calculate_risk() tracks 딕셔너리 키로 변환

    RiskAnalyzer는 "enemy_champion" / "ally_champion" 키를 사용
    """
    team = class_to_team(yolo_class, my_team)
    if team == "ally":
        return "ally_champion"
    elif team == "enemy":
        return "enemy_champion"
    elif yolo_class == "ward":
        return "ward"
    elif yolo_class == "objective":
        return "objective"
    return "unknown"


# ──────────────────────────────────────────────
# 단독 실행 테스트
# ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=== CoordParser 테스트 (1920x1080 기준) ===\n")

    parser = CoordParser(bbox=DEFAULT_MINIMAP_BBOX_1080P)
    print(parser)

    test_cases = [
        (1625, 815,  "미니맵 좌상단 → (0.0, 0.0)"),
        (1920, 1080, "미니맵 우하단 → (1.0, 1.0)"),
        (1772, 947,  "미니맵 중앙   → (~0.5, ~0.5)"),
        (1780, 950,  "임의 좌표"),
    ]

    for px, py, label in test_cases:
        norm = parser.pixel_to_norm(px, py)
        back = parser.norm_to_pixel(norm.x, norm.y)
        print(f"  {label}")
        print(f"    픽셀  : ({px}, {py})")
        print(f"    정규화: {norm}")
        print(f"    역변환: {back}\n")

    print("=== class_to_team 테스트 ===")
    for cls in ["blue_jungle", "red_adc", "ward", "objective"]:
        team   = class_to_team(cls, my_team="ORDER")
        key    = class_to_track_key(cls, my_team="ORDER")
        print(f"  {cls:15s} → team={team:7s}  track_key={key}")
