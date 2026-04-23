"""YOLO minimap detector wrapper."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

try:
    from ultralytics import YOLO  # type: ignore
except Exception:
    YOLO = None  # allow import without ultralytics for unit tests


@dataclass
class Detection:
    cls_name: str
    conf: float
    # Normalized minimap coordinates [0..1]
    x: float
    y: float

    def to_dict(self) -> dict:
        return {
            "class": self.cls_name,
            "conf": round(self.conf, 3),
            "x": round(self.x, 3),
            "y": round(self.y, 3),
        }


class MinimapDetector:
    def __init__(
        self,
        model_path: str,
        classes: List[str],
        conf: float = 0.35,
        iou: float = 0.5,
        device: str = "cuda:0",
    ) -> None:
        if YOLO is None:
            raise RuntimeError("ultralytics is not installed.")
        self.model = YOLO(model_path)
        self.classes = classes
        self.conf = conf
        self.iou = iou
        self.device = device

    def predict(self, frame_bgr: np.ndarray) -> List[Detection]:
        if frame_bgr is None or frame_bgr.size == 0:
            return []
        h, w = frame_bgr.shape[:2]
        results = self.model.predict(
            frame_bgr,
            conf=self.conf,
            iou=self.iou,
            device=self.device,
            verbose=False,
        )
        out: List[Detection] = []
        for r in results:
            boxes = r.boxes
            if boxes is None:
                continue
            for b in boxes:
                cls_id = int(b.cls.item())
                cls_name = (
                    self.classes[cls_id]
                    if cls_id < len(self.classes)
                    else str(cls_id)
                )
                xyxy = b.xyxy[0].tolist()
                cx = (xyxy[0] + xyxy[2]) / 2.0 / w
                cy = (xyxy[1] + xyxy[3]) / 2.0 / h
                out.append(
                    Detection(
                        cls_name=cls_name,
                        conf=float(b.conf.item()),
                        x=float(cx),
                        y=float(cy),
                    )
                )
        return out
