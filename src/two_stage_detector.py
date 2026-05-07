"""
Two-Stage Detector v2 — β 구조 (1-class detect + 결정론적 팀 분류 + 챔피언 분류).

블록 매핑 (역할 명세):
    [모델 1] 내 캐릭터 위치만 파악
        = ally 박스들 중 Live API 의 my_champ 점수가 가장 높은 박스 (Model B 활용)
    [모델 2] 적/아군 구분 + 좌표
        = (A') 1-class champion detector  +  (F) team_classifier (HSV ring 결정론적)
    [파이프라인] 둘을 묶음
        = 본 파일 TwoStageDetectorV2

흐름:
    1. 미니맵 RGB → A' 검출 → 박스 N개 (팀 정보 없음)
    2. 각 박스 crop → F → ally/enemy
    3. 각 박스 crop → B → 챔피언 분류 + my_champ 점수
    4. ally 박스들 중 my_champ 점수 최대 박스 = 내 위치

레거시 호환:
    - A' 가 아직 학습 안 끝났을 때: model_a_path 에 기존 2-class 가중치도 OK
      (검출만 사용하고 팀 라벨은 F 가 덮어씀 — F 가 더 정확하므로)
    - manual_boxes 인자: A' 미존재 시 GT 박스 주입해서 end-to-end 평가 가능

사용 예:
    from src.two_stage_detector import TwoStageDetectorV2

    det = TwoStageDetectorV2(
        model_a_path="models/lol_minimap_1class_l.pt",   # A' 학습 완료 후
        model_b_path="models/champion_classifier.pt",
    )
    result = det.predict(minimap_image, my_champion_name="Aatrox")

    print(result["my_position"])
    # MyPosition(bbox=(x1,y1,x2,y2), score_for_my_champ=0.92, ...)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
from PIL import Image

from src.team_classifier import TeamClassifier


# ─────────────────────────────────────────────────────────────────────────────
# 데이터 구조
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Box:
    bbox: tuple              # (x1, y1, x2, y2) 미니맵 픽셀 좌표
    team: str                # 'ally' | 'enemy' (F 가 결정)
    top1: str                # B 의 top-1 챔피언명
    top1_conf: float
    score_for_my_champ: float = 0.0


@dataclass
class MyPosition:
    bbox: tuple
    score_for_my_champ: float
    rank: int
    top1: str
    top1_conf: float


# ─────────────────────────────────────────────────────────────────────────────
# 메인 클래스
# ─────────────────────────────────────────────────────────────────────────────


class TwoStageDetectorV2:
    """
    β 구조 파이프라인.

    구성 요소:
        - detector: A' 또는 (legacy) A. ultralytics YOLO weights.
        - team_classifier: F. 결정론적 HSV ring 분류.
        - classifier: B. 172-class champion classifier (yolo cls).
    """

    def __init__(
        self,
        model_a_path: Optional[Path],
        model_b_path: Path,
        device: str = "0",
        det_conf: float = 0.30,
        det_iou: float = 0.45,
        cls_imgsz: int = 96,
        team_classifier: Optional[TeamClassifier] = None,
    ):
        from ultralytics import YOLO

        self.cls_imgsz = cls_imgsz
        self.device = device
        self.det_conf = det_conf
        self.det_iou = det_iou

        if model_a_path is not None and Path(model_a_path).exists():
            self.detector = YOLO(str(model_a_path))
            self.has_detector = True
        else:
            self.detector = None
            self.has_detector = False

        self.classifier = YOLO(str(model_b_path))
        self._name_to_idx = {v: k for k, v in self.classifier.names.items()}
        self.team_classifier = team_classifier or TeamClassifier()

    # ───────── public ─────────

    def predict(
        self,
        image,
        my_champion_name: Optional[str] = None,
        manual_boxes: Optional[Sequence[tuple]] = None,
        valid_champs: Optional[set] = None,
    ) -> dict:
        """
        Args:
            image: PIL.Image | np.ndarray | path. 미니맵 RGB.
            my_champion_name: Live API my_champ. None 이면 my_position 미반환.
            manual_boxes: [(x1,y1,x2,y2), ...] 또는 [(team_str, x1,y1,x2,y2), ...].
                          tuple 길이로 자동 판단. 후자의 경우 team_str 은 무시됨 (F 가 덮어씀).
            valid_champs: 게임에 참여 중인 10명 챔피언 set. None 이면 필터링 안 함.
                         예: {"Aatrox", "Ahri", "Akali", ...}

        Returns:
            {
                'ally':  [Box, ...],
                'enemy': [Box, ...],
                'my_position': MyPosition or None,
            }
        """
        img = _to_pil(image)
        img_np = np.array(img)  # F 에 RGB ndarray 전달

        # 1) 박스 좌표 확보 (팀 정보는 무시 — F 가 결정)
        if manual_boxes is not None:
            boxes_xyxy = [_strip_team(b) for b in manual_boxes]
        else:
            if not self.has_detector:
                raise RuntimeError(
                    "detector 가 없습니다. model_a_path 를 지정하거나 manual_boxes 를 넘기세요."
                )
            boxes_xyxy = self._run_detector(img)

        if not boxes_xyxy:
            return {"ally": [], "enemy": [], "my_position": None}

        # 2) 각 박스 crop
        crops = [_crop_and_resize(img, bb, self.cls_imgsz) for bb in boxes_xyxy]
        # F 용 crop (resize 안 한 원본 픽셀 — ring 색 손상 방지)
        crops_for_f = [img_np[y1:y2, x1:x2] for (x1, y1, x2, y2) in boxes_xyxy]

        # 3) F: 팀 분류 (결정론적, 거의 100%)
        teams = []
        for crop_f in crops_for_f:
            if crop_f.size == 0:
                teams.append("enemy")  # 안전 fallback
            else:
                pred, _info = self.team_classifier.classify(crop_f)
                teams.append(pred if pred in ("ally", "enemy") else "enemy")

        # 4) B: 챔피언 분류 (배치)
        cls_results = self.classifier.predict(
            crops, verbose=False, device=self.device,
        )

        # 5) Box 조립 + 필터링
        my_idx = self._name_to_idx.get(my_champion_name) if my_champion_name else None
        ally, enemy = [], []
        ally_box_objs = []
        ally_probs = []

        names = self.classifier.names

        for bbox, team, res in zip(boxes_xyxy, teams, cls_results):
            probs = res.probs
            top1_idx = int(probs.top1)
            top1_conf = float(probs.top1conf)
            top1_name = names.get(top1_idx, str(top1_idx))

            # 🔥 필터링: valid_champs 에 포함되지 않은 챔피언은 스킵
            if valid_champs and top1_name not in valid_champs:
                continue

            score = 0.0
            probs_np = None
            if my_idx is not None:
                probs_np = _tensor_to_numpy(probs.data)
                score = float(probs_np[my_idx])

            box = Box(
                bbox=bbox, team=team, top1=top1_name,
                top1_conf=top1_conf, score_for_my_champ=score,
            )
            if team == "ally":
                ally.append(box)
                ally_box_objs.append(box)
                if my_idx is not None:
                    if probs_np is None:
                        probs_np = _tensor_to_numpy(probs.data)
                    ally_probs.append(probs_np.astype(np.float32))
            else:
                enemy.append(box)

        # 6) [모델 1] my_position: ally 박스 중 my_champ 점수 최대
        my_position = None
        if my_idx is not None and ally_box_objs:
            best_i = int(np.argmax([p[my_idx] for p in ally_probs]))
            best_box = ally_box_objs[best_i]
            best_probs = ally_probs[best_i]
            rank = int(np.sum(best_probs > best_probs[my_idx])) + 1
            my_position = MyPosition(
                bbox=best_box.bbox,
                score_for_my_champ=float(best_probs[my_idx]),
                rank=rank,
                top1=best_box.top1,
                top1_conf=best_box.top1_conf,
            )

        return {"ally": ally, "enemy": enemy, "my_position": my_position}

    # ───────── internal ─────────

    def _run_detector(self, img):
        """A' (1-class) 또는 legacy A (2-class) 실행. 팀 라벨 무시 — F 가 덮어쓸 것."""
        result = self.detector.predict(
            img, verbose=False, device=self.device,
            conf=self.det_conf, iou=self.det_iou,
        )[0]
        boxes_xyxy = []
        if result.boxes is None:
            return boxes_xyxy
        xyxy = result.boxes.xyxy.cpu().numpy()
        for (x1, y1, x2, y2) in xyxy:
            boxes_xyxy.append((int(x1), int(y1), int(x2), int(y2)))
        return boxes_xyxy


# ─────────────────────────────────────────────────────────────────────────────
# 레거시 별칭 (기존 import 호환)
# ─────────────────────────────────────────────────────────────────────────────


# 기존 코드에서 `from src.two_stage_detector import TwoStageDetector` 로 import 했을 수 있어 alias.
TwoStageDetector = TwoStageDetectorV2


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────


def _to_pil(image):
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    if isinstance(image, (str, Path)):
        return Image.open(str(image)).convert("RGB")
    if isinstance(image, np.ndarray):
        return Image.fromarray(image).convert("RGB")
    raise TypeError("image must be PIL.Image, ndarray, or path")


def _tensor_to_numpy(t):
    if isinstance(t, np.ndarray):
        return t
    try:
        return t.detach().cpu().numpy()
    except AttributeError:
        return np.asarray(t)


def _crop_and_resize(img, bbox, size):
    x1, y1, x2, y2 = bbox
    if x2 <= x1 + 2 or y2 <= y1 + 2:
        return Image.new("RGB", (size, size), (0, 0, 0))
    return img.crop((x1, y1, x2, y2)).resize((size, size), Image.LANCZOS)


def _strip_team(box):
    """manual_boxes 가 (team, x1,y1,x2,y2) 5-tuple 또는 (x1,y1,x2,y2) 4-tuple 모두 수용."""
    if len(box) == 5:
        return tuple(box[1:])
    if len(box) == 4:
        return tuple(box)
    raise ValueError(f"box 형식 이상: {box}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI: 단독 실행
# ─────────────────────────────────────────────────────────────────────────────


def _load_yolo_labels(label_path, img_w, img_h, class_filter=(0, 1, 2)):
    """YOLO TXT → [(x1,y1,x2,y2), ...]. team 정보는 무시 (F 가 다시 결정)."""
    out = []
    with open(label_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) != 5:
                continue
            cls = int(parts[0])
            if cls not in class_filter:
                continue
            # class 0 (미니맵 영역) 은 너무 큼 → 제외
            if cls == 0:
                continue
            cx, cy, w, h = map(float, parts[1:])
            x1 = max(0, int((cx - w / 2) * img_w))
            y1 = max(0, int((cy - h / 2) * img_h))
            x2 = min(img_w, int((cx + w / 2) * img_w))
            y2 = min(img_h, int((cy + h / 2) * img_h))
            out.append((x1, y1, x2, y2))
    return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="2-stage detector v2 (β 구조) 단독 테스트")
    ap.add_argument("--image", type=Path, required=True, help="minimap PNG")
    ap.add_argument("--label", type=Path, default=None,
                    help="YOLO label TXT. 주면 manual_boxes 모드 (A' 미사용)")
    ap.add_argument("--my-champ", type=str, required=True, help="내 챔피언 이름 (예: Aatrox)")
    ap.add_argument("--model-a", type=Path,
                    default=Path(__file__).resolve().parent.parent / "models" / "lol_minimap_1class_l.pt",
                    help="A' weights (없으면 None 으로 manual_boxes 모드)")
    ap.add_argument("--model-b", type=Path,
                    default=Path(__file__).resolve().parent.parent / "models" / "champion_classifier.pt")
    ap.add_argument("--device", default="0")
    args = ap.parse_args()

    model_a = args.model_a if args.model_a.exists() else None
    if model_a is None:
        print(f"[!] {args.model_a} 없음 — manual_boxes 모드로 진행")

    det = TwoStageDetectorV2(model_a, args.model_b, device=args.device)

    img = Image.open(args.image).convert("RGB")
    manual = None
    if args.label and args.label.exists():
        manual = _load_yolo_labels(args.label, img.size[0], img.size[1])

    result = det.predict(img, my_champion_name=args.my_champ, manual_boxes=manual)

    print(f"image     : {args.image}")
    print(f"my champ  : {args.my_champ}")
    print(f"ally  ({len(result['ally'])}):")
    for b in result["ally"]:
        print(f"  {b.bbox}  top1={b.top1} ({b.top1_conf:.2f})  my_score={b.score_for_my_champ:.3f}")
    print(f"enemy ({len(result['enemy'])}):")
    for b in result["enemy"]:
        print(f"  {b.bbox}  top1={b.top1} ({b.top1_conf:.2f})")
    if result["my_position"]:
        mp = result["my_position"]
        print(f"\nmy_position:")
        print(f"  bbox            : {mp.bbox}")
        print(f"  score_for_my    : {mp.score_for_my_champ:.3f}")
        print(f"  rank in box     : {mp.rank}  (1 = top-1)")
        print(f"  top1 of box     : {mp.top1} ({mp.top1_conf:.3f})")
    else:
        print("\nmy_position: None (no ally boxes or my_champ unknown)")
