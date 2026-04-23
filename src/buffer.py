"""Time-windowed buffer for the last N seconds of detections."""
from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Deque, Dict, List

from .detector import Detection


class FrameRecord(dict):
    """A single timestamped frame record."""


class RollingBuffer:
    def __init__(self, window_seconds: int = 60) -> None:
        self.window = window_seconds
        self._dq: Deque[FrameRecord] = deque()
        self._lock = Lock()

    def push(self, detections: List[Detection]) -> None:
        now = time.time()
        rec = FrameRecord(
            t=now,
            detections=[d.to_dict() for d in detections],
        )
        with self._lock:
            self._dq.append(rec)
            cutoff = now - self.window
            while self._dq and self._dq[0]["t"] < cutoff:
                self._dq.popleft()

    def snapshot(self) -> List[FrameRecord]:
        with self._lock:
            return list(self._dq)

    def summarize(self) -> Dict:
        """Build a compact summary suitable for LLM input."""
        snap = self.snapshot()
        if not snap:
            return {"frames": 0, "duration": 0, "tracks": {}}

        first_t = snap[0]["t"]
        last_t = snap[-1]["t"]

        tracks: Dict[str, List[List[float]]] = {}
        for rec in snap:
            rel = round(rec["t"] - first_t, 2)
            for d in rec["detections"]:
                tracks.setdefault(d["class"], []).append(
                    [rel, d["x"], d["y"]]
                )

        # 토큰 절약을 위해 클래스당 최대 20포인트로 다운샘플
        for k, pts in tracks.items():
            if len(pts) > 20:
                step = len(pts) // 20
                tracks[k] = pts[::step][:20]

        return {
            "frames": len(snap),
            "duration": round(last_t - first_t, 2),
            "tracks": tracks,
        }
