"""Minimap screen capture using dxcam (fast) with mss fallback."""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

try:
    import dxcam  # type: ignore
    _HAS_DXCAM = True
except Exception:
    _HAS_DXCAM = False

try:
    import mss  # type: ignore
    _HAS_MSS = True
except Exception:
    _HAS_MSS = False


class MinimapCapturer:
    """Captures a fixed bbox region of the primary monitor as BGR ndarray."""

    def __init__(self, bbox: Tuple[int, int, int, int]):
        self.bbox = bbox  # (left, top, right, bottom)
        self._dxcam = None
        self._mss = None

        if _HAS_DXCAM:
            self._dxcam = dxcam.create(output_color="BGR")
            self._dxcam.start(region=self.bbox, target_fps=60)
        elif _HAS_MSS:
            self._mss = mss.mss()
        else:
            raise RuntimeError(
                "Neither dxcam nor mss is installed. "
                "Run: pip install dxcam mss"
            )

    def grab(self) -> Optional[np.ndarray]:
        if self._dxcam is not None:
            frame = self._dxcam.get_latest_frame()
            return frame  # may be None if no new frame yet
        # mss fallback
        left, top, right, bottom = self.bbox
        monitor = {
            "left": left,
            "top": top,
            "width": right - left,
            "height": bottom - top,
        }
        raw = self._mss.grab(monitor)
        return np.array(raw)[:, :, :3][:, :, ::-1].copy()  # BGRA -> BGR

    def close(self) -> None:
        if self._dxcam is not None:
            try:
                self._dxcam.stop()
            except Exception:
                pass
        if self._mss is not None:
            try:
                self._mss.close()
            except Exception:
                pass
