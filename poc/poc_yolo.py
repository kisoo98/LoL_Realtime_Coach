"""poc_yolo.py — YOLO26 미니맵 탐지 PoC (Phase 0, 황기수)

목적
----
- `models/lol_minimap_yolo26n.pt` (YOLO26, 169 챔피언 클래스, mAP50 93.3%)
  으로 미니맵 이미지 1장에서 챔피언 아이콘을 탐지하고 결과를 시각화한다.
- Phase 1 `detector.py` 통합 전에 모델/환경/추론 파이프라인이 정상
  동작하는지 확인하기 위한 standalone 스크립트.

사용 예
-------
    # 기본 샘플 이미지로 실행
    python poc/poc_yolo.py

    # 특정 이미지 지정
    python poc/poc_yolo.py --image data/huggingface/test/images/0.png

    # 임계값/디바이스 조정
    python poc/poc_yolo.py --conf 0.25 --device cuda:0

출력
----
- 콘솔: 탐지된 객체 리스트 (class, conf, normalized x/y)
- 파일: poc/out/<이미지명>_pred.jpg (바운딩박스 + 라벨 그려진 이미지)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

# 무거운 의존성(ultralytics)은 실제 추론 시점에만 임포트한다.
# 그래야 `python poc_yolo.py --help` 가 환경 미설치 상태에서도 동작한다.


# ---------- 경로 기본값 ----------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = PROJECT_ROOT / "models" / "lol_minimap_yolo26n.pt"
DEFAULT_IMAGE = PROJECT_ROOT / "data" / "huggingface" / "test" / "images" / "0.png"
DEFAULT_OUTDIR = PROJECT_ROOT / "poc" / "out"


# ---------- 박스 색상 ----------
def _color_for_class(cls_id: int) -> Tuple[int, int, int]:
    """클래스 id로부터 결정적 BGR 색상 생성 (시각화용)."""
    rng = np.random.default_rng(cls_id * 9973 + 17)
    return tuple(int(c) for c in rng.integers(60, 230, size=3))


# ---------- 시각화 ----------
def draw_detections(
    image: np.ndarray,
    boxes_xyxy: np.ndarray,
    classes: np.ndarray,
    confs: np.ndarray,
    names: dict,
) -> np.ndarray:
    """탐지 결과를 이미지에 그려 반환."""
    out = image.copy()
    for (x1, y1, x2, y2), cls_id, conf in zip(boxes_xyxy, classes, confs):
        x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
        color = _color_for_class(int(cls_id))
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

        label = f"{names.get(int(cls_id), str(int(cls_id)))} {conf:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(out, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(
            out,
            label,
            (x1 + 2, y1 - 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
    return out


# ---------- 메인 추론 ----------
def run_inference(
    model_path: Path,
    image_path: Path,
    conf: float,
    iou: float,
    device: str,
    outdir: Path,
) -> List[dict]:
    if not model_path.exists():
        print(f"[ERROR] 모델 파일이 없습니다: {model_path}")
        sys.exit(1)
    if not image_path.exists():
        print(f"[ERROR] 입력 이미지가 없습니다: {image_path}")
        sys.exit(1)

    try:
        from ultralytics import YOLO  # type: ignore
    except ImportError:
        print("[ERROR] ultralytics 패키지가 필요합니다. `pip install ultralytics`")
        sys.exit(1)

    print(f"[INFO] 모델 로딩: {model_path.name}")
    t0 = time.perf_counter()
    model = YOLO(str(model_path))
    print(f"[INFO] 모델 로딩 완료 ({time.perf_counter() - t0:.2f}s)")

    image = cv2.imread(str(image_path))
    if image is None:
        print(f"[ERROR] 이미지 로딩 실패: {image_path}")
        sys.exit(1)
    h, w = image.shape[:2]
    print(f"[INFO] 이미지: {image_path.name} ({w}x{h})")

    print(f"[INFO] 추론 시작 (conf={conf}, iou={iou}, device={device})")
    t1 = time.perf_counter()
    results = model.predict(
        image,
        conf=conf,
        iou=iou,
        device=device,
        verbose=False,
    )
    infer_ms = (time.perf_counter() - t1) * 1000
    print(f"[INFO] 추론 완료 ({infer_ms:.1f} ms)")

    detections: List[dict] = []
    boxes_xyxy_list: List[np.ndarray] = []
    classes_list: List[np.ndarray] = []
    confs_list: List[np.ndarray] = []
    names: dict = {}

    for r in results:
        names = r.names if hasattr(r, "names") else {}
        if r.boxes is None or len(r.boxes) == 0:
            continue
        xyxy = r.boxes.xyxy.cpu().numpy()
        cls = r.boxes.cls.cpu().numpy().astype(int)
        cf = r.boxes.conf.cpu().numpy()

        boxes_xyxy_list.append(xyxy)
        classes_list.append(cls)
        confs_list.append(cf)

        for box, c_id, c_conf in zip(xyxy, cls, cf):
            cx = (box[0] + box[2]) / 2.0 / w
            cy = (box[1] + box[3]) / 2.0 / h
            detections.append(
                {
                    "class": names.get(int(c_id), str(int(c_id))),
                    "conf": round(float(c_conf), 3),
                    "x_norm": round(float(cx), 3),
                    "y_norm": round(float(cy), 3),
                    "bbox_xyxy": [int(v) for v in box],
                }
            )

    # 콘솔 출력
    print(f"\n[RESULT] 탐지 객체 {len(detections)}개")
    print(json.dumps(detections, indent=2, ensure_ascii=False))

    # 시각화 저장
    outdir.mkdir(parents=True, exist_ok=True)
    if boxes_xyxy_list:
        annotated = draw_detections(
            image,
            np.concatenate(boxes_xyxy_list, axis=0),
            np.concatenate(classes_list, axis=0),
            np.concatenate(confs_list, axis=0),
            names,
        )
    else:
        annotated = image

    out_path = outdir / f"{image_path.stem}_pred.jpg"
    cv2.imwrite(str(out_path), annotated)
    print(f"\n[INFO] 시각화 결과 저장: {out_path}")

    return detections


# ---------- CLI ----------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="YOLO26 미니맵 탐지 PoC")
    p.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL,
        help=f"YOLO 모델 경로 (default: {DEFAULT_MODEL.name})",
    )
    p.add_argument(
        "--image",
        type=Path,
        default=DEFAULT_IMAGE,
        help=f"입력 이미지 경로 (default: {DEFAULT_IMAGE.name})",
    )
    p.add_argument("--conf", type=float, default=0.35, help="confidence threshold")
    p.add_argument("--iou", type=float, default=0.5, help="IoU NMS threshold")
    p.add_argument(
        "--device",
        type=str,
        default="cpu",
        help="추론 디바이스 ('cpu' 또는 'cuda:0')",
    )
    p.add_argument(
        "--outdir",
        type=Path,
        default=DEFAULT_OUTDIR,
        help=f"결과 저장 폴더 (default: {DEFAULT_OUTDIR})",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    run_inference(
        model_path=args.model,
        image_path=args.image,
        conf=args.conf,
        iou=args.iou,
        device=args.device,
        outdir=args.outdir,
    )


if __name__ == "__main__":
    main()
main() -> None:
    args = parse_args()
    run_inference(
        model_path=args.model,
        image_path=args.image,
        conf=args.conf,
        iou=args.iou,
        device=args.device,
        outdir=args.outdir,
    )


if __name__ == "__main__":
    main()
