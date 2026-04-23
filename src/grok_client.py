"""Grok (xAI) vision client. Sends summary JSON + minimap image."""
from __future__ import annotations

import base64
import json
from typing import Dict, Optional

import cv2
import numpy as np
from openai import OpenAI

from .settings import GrokCfg

SYSTEM_PROMPT_KO = """너는 T1 페이커급의 LoL 매크로 코치다.
입력으로 지난 60초의 미니맵 객체 추적 데이터(JSON)와 현재 미니맵 이미지를 받는다.
다음 형식으로 한국어로 매우 간결하게 답하라:

[위험도] (낮음/보통/높음/매우높음)
[현재 상황] 한 줄
[추천 로테이션] 1~2줄, 구체적 라인/오브젝트 명시
[30초 후 예상] 한 줄

불필요한 인사말이나 설명 금지. 4개 섹션만 출력."""


def encode_image_b64(frame_bgr: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise RuntimeError("Failed to encode minimap image.")
    return base64.b64encode(buf.tobytes()).decode("ascii")


class GrokCoach:
    def __init__(self, cfg: GrokCfg, api_key: str) -> None:
        if not api_key:
            raise RuntimeError(
                "XAI_API_KEY not set. Copy .env.example to .env and fill it."
            )
        self.cfg = cfg
        self.client = OpenAI(api_key=api_key, base_url=cfg.base_url)

    def get_feedback(
        self,
        summary: Dict,
        minimap_bgr: Optional[np.ndarray],
    ) -> str:
        user_content = [
            {
                "type": "text",
                "text": "지난 60초 미니맵 데이터:\n"
                + json.dumps(summary, ensure_ascii=False),
            }
        ]
        if minimap_bgr is not None:
            b64 = encode_image_b64(minimap_bgr)
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                    },
                }
            )

        resp = self.client.chat.completions.create(
            model=self.cfg.model,
            max_tokens=self.cfg.max_tokens,
            temperature=self.cfg.temperature,
            timeout=self.cfg.timeout_seconds,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_KO},
                {"role": "user", "content": user_content},
            ],
        )
        return resp.choices[0].message.content or ""
