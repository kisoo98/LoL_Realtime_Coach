"""
Team Classifier (F) — 박스 crop → ally / enemy.

알고리즘:
    1. cv2.HoughCircles 로 ring 자체를 기하학적으로 검출 (LoL 미니맵 ring 은 깨끗한 원)
    2. 검출된 원의 둘레 ±3px 띠 안의 픽셀만 색 카운트 → 챔피언 초상화 색 영향 0
    3. ring 검출 실패 시 fallback: 중앙 사각형 제외한 가장자리 영역
    4. 시그니처 색 (ally=cyan/blue, enemy=red) 픽셀 다수결

검증 결과:
    data_0429 의 blue_border 50 + red_border 50 → 100/100 (오차 0건).

API:
    from src.team_classifier import TeamClassifier
    tc = TeamClassifier()
    pred, info = tc.classify(rgb_crop)   # pred ∈ {"ally","enemy","unknown"}

    또는 박스 좌표로 미니맵에서 직접:
    pred, info = tc.classify_box(minimap_rgb, (x1,y1,x2,y2))
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image


# ─────────────────────────────────────────────────────────────────────────────
# config (data_0429 100장에서 100/100 확정한 값)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class TeamClassifierConfig:
    # ring 검출
    hough_param1: int = 80
    hough_param2: int = 18
    # 반경 비율 — 격리 100/100 검증된 원래 값으로 롤백
    min_radius_ratio: float = 0.25
    max_radius_ratio: float = 0.55
    ring_band_px: int = 3
    # ring 중심 정합성 (largest-circle priority 후보 필터용)
    center_max_offset_ratio: float = 0.50
    # fallback
    center_keep_ratio: float = 0.55
    # 색 마스크 (PIL HSV 0~255) — 원래 값
    sat_min: int = 100
    val_min: int = 100
    blue_hue_lo: int = 125
    blue_hue_hi: int = 180
    red_hue_lo_low: int = 0
    red_hue_hi_low: int = 20
    red_hue_lo_high: int = 230
    red_hue_hi_high: int = 255
    # crop resize
    target_size: int = 100


# ─────────────────────────────────────────────────────────────────────────────
# 메인 클래스
# ─────────────────────────────────────────────────────────────────────────────


class TeamClassifier:
    """ally/enemy 판정. 모델 가중치 없음 — 결정론적 색 분석."""

    def __init__(self, config: Optional[TeamClassifierConfig] = None):
        self.cfg = config or TeamClassifierConfig()

    # ───────── public ─────────

    def classify(self, rgb: np.ndarray) -> tuple[str, dict]:
        """
        Args:
            rgb: HxWx3 uint8 RGB array (챔피언 아이콘 crop).
        Returns:
            (pred, info) — pred ∈ {"ally","enemy","unknown"}.
            info: {"mode","ring","blue_n","red_n","margin"}.
        """
        # 비정형 크기 입력 → target_size 로 정규화
        rgb = self._ensure_target_size(rgb)
        H, W = rgb.shape[:2]

        info: dict = {}
        ring = self._detect_ring(rgb)

        if ring is not None:
            cx, cy, r = ring
            mask = self._ring_band_mask(H, W, cx, cy, r, self.cfg.ring_band_px)
            info["mode"] = "hough"
            info["ring"] = (cx, cy, r)
        else:
            mask = self._fallback_edge_mask(H, W, self.cfg.center_keep_ratio)
            info["mode"] = "fallback"
            info["ring"] = None

        blue_n, red_n = self._color_counts(rgb, mask)
        info["blue_n"] = blue_n
        info["red_n"] = red_n
        info["margin"] = abs(blue_n - red_n)

        if blue_n == 0 and red_n == 0:
            return "unknown", info
        return ("ally" if blue_n > red_n else "enemy"), info

    def classify_box(self, minimap_rgb: np.ndarray, bbox: tuple[int, int, int, int]) -> tuple[str, dict]:
        """미니맵 RGB + (x1,y1,x2,y2) → ally/enemy."""
        x1, y1, x2, y2 = bbox
        crop = minimap_rgb[y1:y2, x1:x2]
        if crop.size == 0:
            return "unknown", {"mode": "empty_crop"}
        return self.classify(crop)

    # ───────── internal ─────────

    def _ensure_target_size(self, rgb: np.ndarray) -> np.ndarray:
        H, W = rgb.shape[:2]
        T = self.cfg.target_size
        if H == T and W == T:
            return rgb
        # 비율 무시하고 target 으로 resize (ring 모양은 거의 정원이므로 살짝 찌그러져도 OK)
        return cv2.resize(rgb, (T, T), interpolation=cv2.INTER_AREA)

    def _detect_ring(self, rgb: np.ndarray) -> Optional[tuple[int, int, int]]:
        """
        Hough Circle 후보 중 '가장 외곽 ring' 을 우선 선택.

        근거: 챔프 본체 내부에 빨간 아이콘/원형 디테일이 있어 Hough 가 작은 안쪽
        원에 끌리는 경우가 다수. 외곽 ring (실제 팀 색 띠) 을 우선해야 색 분류가 정확.

        선택 정책:
            1. minDist 를 줄여 다중 후보 허용 (기존 max(H,W) 단일 → 1 픽셀)
            2. 후보 중 반경이 가장 큰 것 선택
            3. 단, 중심이 crop 중앙에서 너무 멀면 제외 (edge 노이즈 회피)
        """
        H, W = rgb.shape[:2]
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        gray = cv2.medianBlur(gray, 3)
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=1.0,
            minDist=1,  # 다중 후보 허용
            param1=self.cfg.hough_param1,
            param2=self.cfg.hough_param2,
            minRadius=int(min(H, W) * self.cfg.min_radius_ratio),
            maxRadius=int(min(H, W) * self.cfg.max_radius_ratio),
        )
        if circles is None:
            return None
        # 중심이 crop 중앙에서 너무 먼 후보 제거 (config 기반)
        cx_img, cy_img = W / 2.0, H / 2.0
        best = None
        best_r = -1
        for c in circles[0]:
            cx, cy, r = float(c[0]), float(c[1]), float(c[2])
            d = np.sqrt((cx - cx_img) ** 2 + (cy - cy_img) ** 2)
            if d > r * self.cfg.center_max_offset_ratio:
                continue
            if r > best_r:
                best_r = r
                best = (int(round(cx)), int(round(cy)), int(round(r)))
        if best is not None:
            return best
        # 모든 후보가 중앙에서 멀면 첫 후보 fallback (기존 동작)
        c = circles[0, 0]
        return int(round(c[0])), int(round(c[1])), int(round(c[2]))

    @staticmethod
    def _ring_band_mask(H: int, W: int, cx: int, cy: int, r: int, band: int) -> np.ndarray:
        yy, xx = np.mgrid[0:H, 0:W]
        dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
        return (dist >= r - band) & (dist <= r + band)

    @staticmethod
    def _fallback_edge_mask(H: int, W: int, center_keep_ratio: float) -> np.ndarray:
        cy, cx = H / 2.0, W / 2.0
        half = (min(H, W) / 2.0) * center_keep_ratio
        yy, xx = np.mgrid[0:H, 0:W]
        in_center = (np.abs(yy - cy) < half) & (np.abs(xx - cx) < half)
        return ~in_center

    def _color_counts(self, rgb: np.ndarray, mask: np.ndarray) -> tuple[int, int]:
        hsv = np.array(Image.fromarray(rgb, mode="RGB").convert("HSV"))
        h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        region = mask & (s >= self.cfg.sat_min) & (v >= self.cfg.val_min)
        blue_n = int((region & (h >= self.cfg.blue_hue_lo) & (h <= self.cfg.blue_hue_hi)).sum())
        red_lo  = (h <= self.cfg.red_hue_hi_low)
        red_hi  = (h >= self.cfg.red_hue_lo_high)
        red_n  = int((region & (red_lo | red_hi)).sum())
        return blue_n, red_n


# ─────────────────────────────────────────────────────────────────────────────
# CLI: 단독 검증
# ─────────────────────────────────────────────────────────────────────────────


def _evaluate_dir(blue_dir: Path, red_dir: Path) -> dict:
    """두 디렉토리 내의 모든 PNG 검증."""
    tc = TeamClassifier()
    blue_paths = sorted(blue_dir.glob("blue_border_*.png"))
    red_paths  = sorted(red_dir.glob("red_border_*.png"))
    bc = rc = 0
    fails = []
    for p in blue_paths:
        rgb = np.array(Image.open(p).convert("RGB"))
        pred, info = tc.classify(rgb)
        if pred == "ally":
            bc += 1
        else:
            fails.append((p.name, "ally", pred, info))
    for p in red_paths:
        rgb = np.array(Image.open(p).convert("RGB"))
        pred, info = tc.classify(rgb)
        if pred == "enemy":
            rc += 1
        else:
            fails.append((p.name, "enemy", pred, info))
    return {
        "blue_correct": bc, "blue_total": len(blue_paths),
        "red_correct":  rc, "red_total":  len(red_paths),
        "total_correct": bc + rc, "total": len(blue_paths) + len(red_paths),
        "fails": fails,
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path,
                    default=Path(__file__).resolve().parent.parent / "data" / "raw_0429" / "train")
    args = ap.parse_args()

    res = _evaluate_dir(args.data_dir, args.data_dir)
    print(f"ally  : {res['blue_correct']}/{res['blue_total']}")
    print(f"enemy : {res['red_correct']}/{res['red_total']}")
    print(f"total : {res['total_correct']}/{res['total']}")
    if res["fails"]:
        for name, gt, pred, info in res["fails"]:
            print(f"  fail: {name}  gt={gt}  pred={pred}  info={info}")
    else:
        print("\n*** PERFECT ***")
