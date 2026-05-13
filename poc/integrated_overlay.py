"""
풀스크린 PyQt6 오버레이 위젯.

3개 워커 스레드(Voice / Yolo / Live)를 소유하고,
시그널을 받아 화면에 배너로 표시한다. 글로벌 핫키:
  Ctrl+Shift+Q  : 종료
  Ctrl+Shift+C  : 인게임 컨트롤러 패널 토글

TTS 정책:
  - LLM 응답의 [위험도] 레벨이 "높음" 또는 "매우높음"일 때만 발화
  - 발화 텍스트에서 [xxx] 형식의 모든 메타 태그를 제거
"""
from __future__ import annotations

import re
from pathlib import Path

import keyboard
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget
from loguru import logger

from poc.integrated_constants import (
    EVENT_DISPLAY_SEC,
    LIVE_DISPLAY_SEC,
    LLM_DISPLAY_SEC,
    RISK_AUTO_ALERT,
)
from poc.integrated_controller import ControllerPanel
from poc.integrated_live import LiveClientThread
from poc.integrated_voice import VoiceThread
from poc.integrated_yolo import YoloCoachThread
from poc.paths import APP_ROOT


class IntegratedOverlay(QWidget):
    """3개 워커 스레드 + 풀스크린 투명 오버레이."""

    # 표시 상태 — 인스턴스마다 갱신됨
    _llm_text:    str   = ""
    _llm_timer:   int   = 0
    _live_tip:    str   = ""
    _live_timer:  int   = 0
    _event_tip:   str   = ""
    _event_timer: int   = 0
    _risk:        float = 0.0
    _status_msg:  str   = "초기화 중..."
    _game_status: str   = "waiting"

    def __init__(self):
        super().__init__()
        Path(APP_ROOT / "logs").mkdir(parents=True, exist_ok=True)
        # 컨트롤러 토글 상태 (TTS / YOLO / Live)
        self._tts_enabled  = True
        self._yolo_enabled = True
        self._live_enabled = True
        self._init_ui()
        self._init_threads()
        self._init_controller()
        self._init_hotkeys()
        self._init_repaint_timer()

    # ── 초기화 ───────────────────────────────────────────────────────────────
    def _init_ui(self) -> None:
        # 🔥 듀얼 모니터 환경: 현재 마우스 커서 위치의 스크린 감지
        app = QApplication.instance()
        screen = self._get_screen_at_cursor()
        if screen is None:
            # Fallback: primaryScreen
            screen = app.primaryScreen()
            logger.warning("⚠️ 마우스 커서 스크린 감지 실패 → Primary Screen 사용")

        geo    = screen.geometry()
        self.screen_w = geo.width()
        self.screen_h = geo.height()
        self.screen_x = geo.x()  # 스크린 좌상단 X 좌표 (듀얼 모니터 대비)
        self.screen_y = geo.y()  # 스크린 좌상단 Y 좌표

        logger.info(f"스크린 감지: {self.screen_w}x{self.screen_h} @ ({self.screen_x}, {self.screen_y})")

        self.setGeometry(geo)
        self.setWindowTitle("LoL Realtime Coach — 최종 PoC")
        # Tool: 풀스크린 게임 위에서 안정적 (ToolTip보다 z-order 충돌 적음)
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint  |
            Qt.WindowType.WindowTransparentForInput |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.show()

    def _init_threads(self) -> None:
        self._voice = VoiceThread()
        self._voice.start()

        self._yolo = YoloCoachThread()
        self._yolo.feedback_signal.connect(self._on_llm_feedback)
        self._yolo.risk_signal.connect(self._on_risk_update)
        self._yolo.status_signal.connect(self._on_yolo_status)
        self._yolo.start()

        self._live = LiveClientThread()
        self._live.update_signal.connect(self._on_live_update)
        # 챔피언명을 YOLO 스레드로 직접 전달
        self._live.champ_signal.connect(self._yolo.set_my_champion)
        # 🔥 10명 챔피언 리스트를 YOLO 스레드로 전달 (필터링용)
        self._live.champ_list_signal.connect(self._yolo.set_champ_list)
        self._live.start()

    def _get_screen_at_cursor(self):
        """현재 마우스 커서가 있는 스크린 반환 (듀얼 모니터 대응)."""
        try:
            app = QApplication.instance()
            cursor_pos = QApplication.instance().primaryScreen().virtualGeometry().topLeft()
            # 모든 스크린에서 현재 마우스 위치 찾기
            for screen in app.screens():
                if screen.geometry().contains(cursor_pos):
                    return screen
            # 찾지 못한 경우: Primary Screen 반환
            return app.primaryScreen()
        except Exception as e:
            logger.warning(f"스크린 감지 오류: {e}")
            return None

    def _init_controller(self) -> None:
        """인게임 컨트롤러 패널 생성 + 시그널 연결."""
        self._controller = ControllerPanel()
        self._controller.tts_toggled.connect(self._on_toggle_tts)
        self._controller.yolo_toggled.connect(self._on_toggle_yolo)
        self._controller.live_toggled.connect(self._on_toggle_live)
        self._controller.volume_changed.connect(self._voice.set_volume)
        self._controller.quit_requested.connect(self._on_quit)
        self._controller.show()
        # 초기 슬라이더 표시값(70%)을 실제 TTS 음량과 동기화
        self._voice.set_volume(0.7)

    def _init_hotkeys(self) -> None:
        try:
            # 🔥 suppress=False: 키 이벤트가 계속 전파되도록 (마우스 간섭 방지)
            keyboard.add_hotkey("ctrl+shift+q", self._on_quit, suppress=False)
            keyboard.add_hotkey("ctrl+shift+c", self._controller.toggle_visibility, suppress=False)
            logger.info("핫키 등록: Ctrl+Shift+Q(종료), Ctrl+Shift+C(컨트롤러)")
        except (ImportError, Exception) as e:
            logger.warning(f"⚠️ 핫키 등록 실패 (WSL/Linux 권한 부족): {e}")
            logger.info("단축키 대신 GUI 버튼이나 다른 방식을 사용하세요.")

    def _init_repaint_timer(self) -> None:
        self._qtimer = QTimer(self)
        self._qtimer.timeout.connect(self._tick)
        self._qtimer.start(1000)

    # ── 슬롯 ─────────────────────────────────────────────────────────────────
    # LLM 응답 파싱용 정규식
    _RE_RISK_LEVEL = re.compile(r"\[\s*위험도\s*\]\s*(매우높음|높음|보통|낮음)")
    _RE_TAG        = re.compile(r"\[[^\]]+\]")
    _RE_WS         = re.compile(r"\s+")
    _TTS_LEVELS    = {"높음", "매우높음"}

    @classmethod
    def _parse_risk_level(cls, text: str) -> str:
        """LLM 응답의 [위험도] 라인에서 레벨 텍스트를 추출. 없으면 빈 문자열."""
        m = cls._RE_RISK_LEVEL.search(text)
        return m.group(1) if m else ""

    @classmethod
    def _strip_tags(cls, text: str) -> str:
        """[xxx] 형식의 모든 메타 태그를 제거하고 공백을 한 칸으로 정리."""
        return cls._RE_WS.sub(" ", cls._RE_TAG.sub("", text)).strip()

    def _on_llm_feedback(self, text: str) -> None:
        self._llm_text  = text
        self._llm_timer = LLM_DISPLAY_SEC
        if self._tts_enabled:
            # LLM이 보고한 위험도 레벨이 "높음"/"매우높음"일 때만 TTS 발화
            level = self._parse_risk_level(text)
            if level in self._TTS_LEVELS:
                spoken = self._strip_tags(text)
                if spoken:
                    self._voice.speak(spoken[:100])
            else:
                logger.debug(f"TTS 차단 — 위험도 레벨='{level or '없음'}'")
        self.repaint()

    def _on_risk_update(self, risk: float) -> None:
        self._risk = risk
        self.repaint()

    def _on_yolo_status(self, msg: str) -> None:
        self._status_msg = msg
        self.repaint()

    def _on_live_update(self, data: dict) -> None:
        prev_status       = self._game_status
        self._game_status = data.get("status", "waiting")

        # 게임 종료 감지: ingame → waiting 전환 시 표시 중인 팁 전체 초기화
        if prev_status == "ingame" and self._game_status == "waiting":
            self._llm_text    = ""
            self._llm_timer   = 0
            self._live_tip    = ""
            self._live_timer  = 0
            self._event_tip   = ""
            self._event_timer = 0
            self._risk        = 0.0

        if self._game_status == "waiting":
            self._status_msg = data.get("msg", "대기 중...")
        else:
            if self._tts_enabled:
                for s in data.get("speeches", []):
                    self._voice.speak(s)
            if self._live_enabled:
                new_tip = data.get("new_coaching_tip")
                if new_tip:
                    self._live_tip   = new_tip
                    self._live_timer = LIVE_DISPLAY_SEC
                new_ev = data.get("event_tip")
                if new_ev:
                    self._event_tip   = new_ev
                    self._event_timer = EVENT_DISPLAY_SEC
        self.repaint()

    def _on_quit(self) -> None:
        logger.info("Ctrl+Shift+Q - quit")
        self._shutdown()
        QApplication.quit()

    # ── 컨트롤러 토글 슬롯 ──────────────────────────────────────────────────
    def _on_toggle_tts(self, on: bool) -> None:
        self._tts_enabled = on
        logger.info(f"TTS {'ON' if on else 'OFF'}")

    def _on_toggle_yolo(self, on: bool) -> None:
        self._yolo_enabled = on
        if on:
            if not self._yolo.isRunning():
                self._yolo.start()
            self._yolo.resume()
            logger.info("YOLO ON")
        else:
            self._yolo.pause()
            logger.info("YOLO OFF (일시정지)")

    def _on_toggle_live(self, on: bool) -> None:
        self._live_enabled = on
        logger.info(f"Live API 표시 {'ON' if on else 'OFF'}")

    # ── tick / shutdown ──────────────────────────────────────────────────────
    def _tick(self) -> None:
        for attr, timer_attr in [
            ("_llm_text",  "_llm_timer"),
            ("_live_tip",  "_live_timer"),
            ("_event_tip", "_event_timer"),
        ]:
            t = getattr(self, timer_attr)
            if t > 0:
                setattr(self, timer_attr, t - 1)
                if t - 1 == 0:
                    setattr(self, attr, "")
        self.repaint()

    def _shutdown(self) -> None:
        # 먼저 창을 즉시 숨겨 스레드 종료 대기 중 잔상이 남지 않도록 한다
        self.hide()
        if hasattr(self, "_controller"):
            # 트레이로 최소화된 상태에서 종료하면 잔여 아이콘이 남을 수 있어 같이 정리
            tray = getattr(self._controller, "_tray", None)
            if tray is not None and tray.isVisible():
                tray.hide()
            self._controller.hide()
        self._yolo.stop()
        self._live.stop()
        self._voice.stop()

    def closeEvent(self, event):  # noqa: N802 (Qt 시그니처)
        self._shutdown()
        super().closeEvent(event)

    # ── paint ────────────────────────────────────────────────────────────────
    def paintEvent(self, event):  # noqa: N802 (Qt 시그니처)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W  = 560
        MR = 20
        X  = self.screen_w - W - MR

        # status bar — 인게임일 때만 표시 (대기 중에는 잔상 방지)
        if self._game_status == "ingame":
            risk_color = (
                QColor(255, 80, 80)   if self._risk >= RISK_AUTO_ALERT else
                QColor(255, 200, 50)  if self._risk >= 35              else
                QColor(120, 220, 120)
            )
            p.setPen(QPen(risk_color))
            p.setFont(QFont("Malgun Gothic", 9))
            p.drawText(
                10, 10, 800, 24,
                Qt.AlignmentFlag.AlignLeft,
                "LoL Coach B  |  Risk: {:.0f}%  |  {}".format(self._risk, self._status_msg),
            )

        # waiting banner
        if self._game_status == "waiting" and not self._llm_text:
            self._draw_banner(
                p,
                (self.screen_w - 340) // 2, 50, 340, 50,
                QColor(30, 30, 40, 200),
                self._status_msg,
                QColor(220, 220, 220), 10,
            )

        base_y = 150

        # 1. Gemini feedback
        if self._llm_text:
            lines_count = len(self._llm_text.strip().splitlines())
            h = max(80, lines_count * 22 + 20)
            self._draw_banner(
                p, X, base_y, W, h,
                QColor(20, 60, 120, 220),
                self._llm_text, QColor(200, 230, 255), 12,
                accent=QColor(80, 160, 255),
            )
            base_y += h + 10

        # 2. Live coaching tip
        if self._live_tip:
            if "\U0001f6d1" in self._live_tip or chr(0x1F6D1) in self._live_tip:
                warn_y = int(self.screen_h * 0.55)
                self._draw_warn_banner(p, X, warn_y, W, 65, self._live_tip)
            else:
                self._draw_banner(
                    p, X, base_y, W, 55,
                    QColor(43, 33, 43, 220),
                    self._live_tip, QColor(255, 255, 255), 10,
                    accent=QColor(255, 105, 180),
                )
                base_y += 65

        # 3. event tip
        if self._event_tip:
            self._draw_banner(
                p, X, base_y, W, 55,
                QColor(56, 128, 255, 210),
                "  " + self._event_tip, QColor(255, 255, 255), 10,
            )

        p.end()

    def _draw_banner(
        self, p, x, y, w, h, bg, text, fg, font_size, accent=None,
    ):
        p.setBrush(QBrush(bg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(x, y, w, h, 10, 10)
        if accent:
            p.setBrush(QBrush(accent))
            p.drawRoundedRect(x, y, 6, h, 3, 3)
        p.setPen(QPen(fg))
        p.setFont(QFont("Malgun Gothic", font_size, QFont.Weight.Bold))
        flags = (
            int(Qt.AlignmentFlag.AlignVCenter) |
            int(Qt.AlignmentFlag.AlignLeft)    |
            int(Qt.TextFlag.TextWordWrap)
        )
        margin = 20 if accent else 12
        p.drawText(x + margin, y, w - margin - 8, h, flags, text)

    def _draw_warn_banner(self, p, x, y, w, h, text):
        p.setBrush(QBrush(QColor(180, 40, 40, 220)))
        border_pen = QPen(QColor(255, 80, 80, 255))
        border_pen.setWidth(2)
        p.setPen(border_pen)
        p.drawRoundedRect(x, y, w, h, 15, 15)
        p.setPen(QPen(QColor(255, 255, 255)))
        p.setFont(QFont("Malgun Gothic", 12, QFont.Weight.Bold))
        warn_text = text.replace(chr(0x1F6D1), "!! 경고:")
        flags = (
            int(Qt.AlignmentFlag.AlignVCenter) |
            int(Qt.AlignmentFlag.AlignLeft)    |
            int(Qt.TextFlag.TextWordWrap)
        )
        p.drawText(x + 20, y, w - 30, h, flags, warn_text)
