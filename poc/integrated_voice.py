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
except ImportError as e:
    logger.warning(f"TTS 비활성 — 패키지 미설치: {e}  →  pip install gtts pygame")
    TTS_AVAILABLE = False
except Exception as e:
    logger.warning(f"TTS 비활성 — pygame 초기화 실패: {e}")
    TTS_AVAILABLE = False


class VoiceThread(QThread):
    """gTTS로 mp3 생성 → pygame으로 재생. 큐 기반 단일 워커."""

    def __init__(self):
        super().__init__()
        # queue.Queue: put()/get() 모두 스레드 안전 (내장 Lock)
        self._queue: queue.Queue[str] = queue.Queue()
        self.running = True
        # speak() 호출 시 현재 재생 중인 음성을 즉시 스킵하는 플래그
        self._skip_current: bool = False

    def speak(self, text: str) -> None:
        """메인/다른 스레드에서 호출해도 안전.

        적체된 이전 메시지를 모두 버리고 최신 메시지만 큐에 넣는다.
        현재 재생 중인 음성도 스킵해 즉각 반응하도록 한다.
        """
        if not TTS_AVAILABLE:
            return
        # 적체된 구 메시지 제거 (최신 1개만 유지)
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._queue.put(text)
        # 현재 재생 중이던 음성을 즉시 중단
        self._skip_current = True

    def run(self) -> None:
        while self.running:
            try:
                # 0.1초마다 running 재확인 → stop() 응답성 보장
                text = self._queue.get(block=True, timeout=0.1)
            except queue.Empty:
                continue

            self._skip_current = False  # 새 메시지 처리 시작, 플래그 리셋
            try:
                tts = gTTS(text=text, lang="ko")
                # NamedTemporaryFile: 충돌 없는 임시 경로
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp_path = tmp.name
                tts.save(tmp_path)
                pygame.mixer.music.load(tmp_path)
                pygame.mixer.music.play()
                # _skip_current 플래그 감지 시 즉시 재생 중단
                while pygame.mixer.music.get_busy() and self.running and not self._skip_current:
                    time.sleep(0.1)
                if self._skip_current:
                    pygame.mixer.music.stop()
                pygame.mixer.music.unload()
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            except Exception as e:
                logger.warning(f"TTS 오류: {e}")

    def set_volume(self, vol: float) -> None:
        """TTS 재생 음량을 설정한다 (0.0 ~ 1.0). 컨트롤러 슬라이더에서 호출."""
        vol = max(0.0, min(1.0, vol))
        if TTS_AVAILABLE:
            try:
                pygame.mixer.music.set_volume(vol)
            except Exception:
                pass
        logger.debug(f"TTS 음량: {int(vol * 100)}%")

    def stop(self) -> None:
        self.running = False
        self.wait()
