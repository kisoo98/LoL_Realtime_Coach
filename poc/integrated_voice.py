"""
TTS(gTTS + pygame) 음성 출력 스레드.

큐를 통해 다른 스레드에서도 안전하게 speak() 호출 가능.
gTTS 또는 pygame 가져오기에 실패하면 TTS_AVAILABLE=False 로 두고
speak() 호출은 silent no-op이 된다.
"""
from __future__ import annotations

import os
import queue
import tempfile
import time

from PyQt6.QtCore import QThread
from loguru import logger

# ── TTS 의존성 — 실패해도 앱 전체가 죽지 않도록 lazy guard ──────────────────
try:
    from gtts import gTTS  # type: ignore
    import pygame  # type: ignore
    pygame.mixer.init()
    TTS_AVAILABLE = True
except Exception:  # pragma: no cover - 의존성 미설치 환경
    TTS_AVAILABLE = False


class VoiceThread(QThread):
    """gTTS로 mp3 생성 → pygame으로 재생. 큐 기반 단일 워커."""

    def __init__(self):
        super().__init__()
        # queue.Queue: put()/get() 모두 스레드 안전 (내장 Lock)
        self._queue: queue.Queue[str] = queue.Queue()
        self.running = True

    def speak(self, text: str) -> None:
        """메인/다른 스레드에서 호출해도 안전."""
        if TTS_AVAILABLE:
            self._queue.put(text)

    def run(self) -> None:
        while self.running:
            try:
                # 0.1초마다 running 재확인 → stop() 응답성 보장
                text = self._queue.get(block=True, timeout=0.1)
            except queue.Empty:
                continue

            try:
                tts = gTTS(text=text, lang="ko")
                # NamedTemporaryFile: 충돌 없는 임시 경로
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp_path = tmp.name
                tts.save(tmp_path)
                pygame.mixer.music.load(tmp_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy() and self.running:
                    time.sleep(0.1)
                pygame.mixer.music.unload()
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            except Exception as e:
                logger.warning(f"TTS 오류: {e}")

    def stop(self) -> None:
        self.running = False
        self.wait()
