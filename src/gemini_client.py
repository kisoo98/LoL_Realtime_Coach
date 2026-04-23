"""Gemini (Google AI Studio) vision client.

Sends summary JSON + minimap image to Gemini 2.5 Pro.
Uses google-generativeai SDK (free tier available).

Interface matches GrokCoach so main.py can swap providers via config.
"""
from __future__ import annotations

import json
from typing import Dict, Optional

import cv2
import numpy as np

from .settings import GeminiCfg

SYSTEM_PROMPT_KO = """너는 T1 페이커급의 LoL 매크로 코치다.
입력으로 지난 60초의 미니맵 객체 추적 데이터(JSON)와 현재 미니맵 이미지를 받는다.
다음 형식으로 한국어로 매우 간결하게 답하라:

[위험도] (낮음/보통/높음/매우높음)
[현재 상황] 한 줄
[추천 로테이션] 1~2줄, 구체적 라인/오브젝트 명시
[30초 후 예상] 한 줄

불필요한 인사말이나 설명 금지. 4개 섹션만 출력."""


def _encode_image_jpeg(frame_bgr: np.ndarray) -> bytes:
    """Encode a BGR frame to JPEG bytes (quality 80)."""
    ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise RuntimeError("Failed to encode minimap image.")
    return buf.tobytes()


class GeminiCoach:
    """Drop-in replacement for GrokCoach using Google Gemini."""

    def __init__(self, cfg: GeminiCfg, api_key: str) -> None:
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY not set. Get one free at "
                "https://aistudio.google.com/app/apikey and put it in .env"
            )
        # Imported here so the project still runs without the package if
        # the user is only using Grok.
        import google.generativeai as genai

        self._genai = genai
        self.cfg = cfg

        genai.configure(api_key=api_key)

        generation_config = {
            "temperature": cfg.temperature,
            "max_output_tokens": cfg.max_tokens,
            "response_mime_type": "text/plain",
        }

        self.model = genai.GenerativeModel(
            model_name=cfg.model,
            generation_config=generation_config,
            system_instruction=SYSTEM_PROMPT_KO,
        )

    def get_feedback(
        self,
        summary: Dict,
        minimap_bgr: Optional[np.ndarray],
    ) -> str:
        """Send JSON summary + optional minimap image, return Korean feedback."""
        parts: list = [
            "지난 60초 미니맵 데이터:\n"
            + json.dumps(summary, ensure_ascii=False)
        ]

        if minimap_bgr is not None:
            image_bytes = _encode_image_jpeg(minimap_bgr)
            parts.append(
                {
                    "mime_type": "image/jpeg",
                    "data": image_bytes,
                }
            )

        # google-generativeai does not accept a per-call timeout in every
        # version; rely on its own internal default. Network hiccups are
        # caught by the caller in main.py.
        response = self.model.generate_content(parts)

        # `.text` raises if the response was blocked; fall back to candidates.
        try:
            return response.text or ""
        except Exception:
            if response.candidates:
                cand = response.candidates[0]
                if cand.content and cand.content.parts:
                    return "".join(
                        getattr(p, "text", "") for p in cand.content.parts
                    )
            return ""
