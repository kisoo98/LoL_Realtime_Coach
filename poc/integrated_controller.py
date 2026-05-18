"""
인게임 컨트롤러 위젯.

게임 화면 위에 작은 드래그 가능한 패널을 띄워
TTS / YOLO / Live API 토글, 종료 등을 제공한다.
Ctrl+Shift+C 핫키로 보이기/숨기기 전환 가능.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath,
    QPen, QBrush, QMouseEvent, QPaintEvent,
)
from PyQt6.QtWidgets import QWidget, QApplication, QSystemTrayIcon, QStyle
from loguru import logger


class _ToggleSwitch(QWidget):
    """작은 ON/OFF 토글 스위치 위젯."""

    toggled = pyqtSignal(bool)

    def __init__(self, label: str, initial: bool = True, parent=None):
        super().__init__(parent)
        self._label = label
        self._checked = initial
        self.setFixedSize(130, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @property
    def checked(self) -> bool:
        return self._checked

    @checked.setter
    def checked(self, val: bool):
        self._checked = val
        self.update()

    def mousePressEvent(self, ev: QMouseEvent):
        self._checked = not self._checked
        self.toggled.emit(self._checked)
        self.update()

    def paintEvent(self, ev: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 라벨
        p.setPen(QPen(QColor(220, 220, 230)))
        p.setFont(QFont("Malgun Gothic", 9))
        p.drawText(0, 0, 70, 32, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label)

        # 트랙
        track_x, track_y, track_w, track_h = 75, 6, 48, 20
        track_radius = track_h // 2

        if self._checked:
            track_color = QColor(80, 180, 120)
        else:
            track_color = QColor(100, 100, 110)

        p.setBrush(QBrush(track_color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(track_x, track_y, track_w, track_h, track_radius, track_radius)

        # 노브
        knob_radius = 14
        knob_y = track_y + (track_h - knob_radius) // 2
        if self._checked:
            knob_x = track_x + track_w - knob_radius - 2
            knob_color = QColor(255, 255, 255)
        else:
            knob_x = track_x + 2
            knob_color = QColor(180, 180, 180)

        p.setBrush(QBrush(knob_color))
        p.drawEllipse(knob_x, knob_y, knob_radius, knob_radius)

        p.end()


class _ActionButton(QWidget):
    """간단한 커스텀 버튼 위젯."""

    clicked = pyqtSignal()

    def __init__(self, text: str, color: QColor, parent=None):
        super().__init__(parent)
        self._text = text
        self._base_color = color
        self._hover = False
        self.setFixedSize(130, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, ev):
        self._hover = True
        self.update()

    def leaveEvent(self, ev):
        self._hover = False
        self.update()

    def mousePressEvent(self, ev: QMouseEvent):
        self.clicked.emit()

    def paintEvent(self, ev: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        c = self._base_color.lighter(125) if self._hover else self._base_color
        p.setBrush(QBrush(c))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 8, 8)

        p.setPen(QPen(QColor(255, 255, 255)))
        p.setFont(QFont("Malgun Gothic", 9, QFont.Weight.Bold))
        p.drawText(0, 0, self.width(), self.height(), Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()


class _VolumeSlider(QWidget):
    """수평 음량 슬라이더 (0.0 ~ 1.0)."""

    volume_changed = pyqtSignal(float)

    def __init__(self, initial: float = 0.7, parent=None):
        super().__init__(parent)
        self._volume = max(0.0, min(1.0, initial))
        self._dragging = False
        self.setFixedSize(130, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, val: float):
        self._volume = max(0.0, min(1.0, val))
        self.update()

    def _vol_from_x(self, x: float) -> float:
        """위젯 X좌표 → 0.0~1.0 볼륨값."""
        track_x, track_w = 10, 110
        return max(0.0, min(1.0, (x - track_x) / track_w))

    def mousePressEvent(self, ev: QMouseEvent):
        self._dragging = True
        self._volume = self._vol_from_x(ev.position().x())
        self.volume_changed.emit(self._volume)
        self.update()

    def mouseMoveEvent(self, ev: QMouseEvent):
        if self._dragging:
            self._volume = self._vol_from_x(ev.position().x())
            self.volume_changed.emit(self._volume)
            self.update()

    def mouseReleaseEvent(self, ev: QMouseEvent):
        self._dragging = False

    def paintEvent(self, ev: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        track_x, track_y, track_w, track_h = 10, 18, 110, 6

        # 라벨
        p.setPen(QPen(QColor(200, 200, 210)))
        p.setFont(QFont("Malgun Gothic", 8))
        pct = int(self._volume * 100)
        p.drawText(0, 0, 130, 16, Qt.AlignmentFlag.AlignLeft, f"🔈 음량  {pct}%")

        # 트랙 배경
        p.setBrush(QBrush(QColor(60, 60, 70)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(track_x, track_y, track_w, track_h, 3, 3)

        # 채워진 부분
        fill_w = int(track_w * self._volume)
        if fill_w > 0:
            p.setBrush(QBrush(QColor(80, 180, 220)))
            p.drawRoundedRect(track_x, track_y, fill_w, track_h, 3, 3)

        # 핸들 (노브)
        knob_r = 10
        knob_x = track_x + fill_w - knob_r // 2
        knob_y = track_y + track_h // 2 - knob_r // 2
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.drawEllipse(knob_x, knob_y, knob_r, knob_r)

        p.end()


class ControllerPanel(QWidget):
    """드래그 가능한 인게임 컨트롤러 패널.

    시그널을 통해 IntegratedOverlay와 통신한다.
    """

    # 부모(IntegratedOverlay)가 연결할 시그널
    tts_toggled  = pyqtSignal(bool)
    yolo_toggled = pyqtSignal(bool)
    live_toggled = pyqtSignal(bool)
    volume_changed = pyqtSignal(float)
    quit_requested = pyqtSignal()

    PANEL_W = 170
    PANEL_H = 320  # 타이틀바 + 토글 3개 + 슬라이더 + 최소화 + 종료 + 여백

    # 타이틀바 우측 끝의 접기 버튼 히트 영역 (마우스 트래킹 / 페인트 공통)
    TITLE_H = 36
    COLLAPSE_BTN_W = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos: QPoint | None = None
        self._collapsed = False
        self._collapse_hover = False
        # mouseMoveEvent를 누르지 않은 상태에서도 받기 위해 트래킹 ON
        self.setMouseTracking(True)

        self.setWindowTitle("Coach Controller")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint  |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.PANEL_W, self.PANEL_H)

        # ── 위젯 배치 ────────────────────────────────────────────────────
        top = 40  # 타이틀바 높이
        gap = 6

        self._tts_toggle = _ToggleSwitch("🔊 TTS", True, self)
        self._tts_toggle.move(20, top)
        self._tts_toggle.toggled.connect(self.tts_toggled.emit)
        top += 32 + gap

        self._volume_slider = _VolumeSlider(0.7, self)
        self._volume_slider.move(20, top)
        self._volume_slider.volume_changed.connect(self.volume_changed.emit)
        top += 36 + gap

        self._yolo_toggle = _ToggleSwitch("👁 AI 피드백", True, self)
        self._yolo_toggle.move(20, top)
        self._yolo_toggle.toggled.connect(self.yolo_toggled.emit)
        top += 32 + gap

        self._live_toggle = _ToggleSwitch("📡 Live 코칭", True, self)
        self._live_toggle.move(20, top)
        self._live_toggle.toggled.connect(self.live_toggled.emit)
        top += 32 + gap + 8

        self._min_btn = _ActionButton("➖ 최소화", QColor(80, 90, 120), self)
        self._min_btn.move(20, top)
        self._min_btn.clicked.connect(self._minimize_to_tray)
        top += 30 + gap

        self._quit_btn = _ActionButton("✖ 종료", QColor(180, 50, 50), self)
        self._quit_btn.move(20, top)
        self._quit_btn.clicked.connect(self.quit_requested.emit)

        # 시스템 트레이 아이콘 — 최소화 시 표시, 더블클릭으로 복원
        self._setup_tray()

        # 화면 우측 하단에 배치
        self._place_bottom_right()

    def _place_bottom_right(self):
        """현재 스크린의 우측 하단에 배치."""
        app = QApplication.instance()
        if app is None:
            return
        screen = app.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + geo.width() - self.PANEL_W - 30
        y = geo.y() + geo.height() - self.PANEL_H - 60
        self.move(x, y)

    # ── 트레이 (완전 최소화) ──────────────────────────────────────────────
    def _setup_tray(self) -> None:
        """시스템 트레이 아이콘 준비. 시스템에서 트레이를 지원하지 않으면 비활성."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = None
            logger.warning("시스템 트레이 사용 불가 — 최소화 버튼이 showMinimized()로 대체됨")
            return
        self._tray = QSystemTrayIcon(self)
        # 앱 아이콘이 없으면 표준 아이콘으로 폴백
        icon = QApplication.instance().windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self._tray.setIcon(icon)
        self._tray.setToolTip("LoL Coach — 더블클릭으로 복원")
        self._tray.activated.connect(self._on_tray_activated)

    def _minimize_to_tray(self) -> None:
        """패널을 화면에서 완전히 숨기고 트레이 아이콘 표시."""
        if self._tray is not None:
            self.hide()
            self._tray.show()
            logger.info("컨트롤러 → 트레이 최소화 (더블클릭으로 복원)")
        else:
            # 트레이 미지원 환경 폴백 — 작업표시줄 최소화
            self.showMinimized()

    def _restore_from_tray(self) -> None:
        """트레이에서 패널을 다시 화면으로 복원."""
        if self._tray is not None:
            self._tray.hide()
        self.show()
        self.raise_()
        self.activateWindow()
        logger.info("컨트롤러 ← 트레이 복원")

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # 더블클릭(요구사항) + 단일 트리거(접근성)도 복원으로 처리
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick,
                      QSystemTrayIcon.ActivationReason.Trigger):
            self._restore_from_tray()

    # ── 접기 버튼 ─────────────────────────────────────────────────────────
    def _is_in_collapse_button(self, x: float, y: float) -> bool:
        """타이틀바 우측 끝 영역(▲/▼ 버튼) 안에 좌표가 있는지."""
        return (x >= self.PANEL_W - self.COLLAPSE_BTN_W
                and 0 <= y < self.TITLE_H)

    def _toggle_collapse(self) -> None:
        """접기/펼치기 상태 토글 + 자식 위젯 가시성 + 패널 높이 조정."""
        self._collapsed = not self._collapsed
        if self._collapsed:
            self.setFixedSize(self.PANEL_W, self.TITLE_H)
        else:
            self.setFixedSize(self.PANEL_W, self.PANEL_H)
        for child in (self._tts_toggle, self._volume_slider, self._yolo_toggle,
                      self._live_toggle, self._min_btn, self._quit_btn):
            child.setVisible(not self._collapsed)
        self.update()

    # ── 드래그 ────────────────────────────────────────────────────────────
    def mousePressEvent(self, ev: QMouseEvent):
        if ev.button() == Qt.MouseButton.LeftButton:
            x = ev.position().x()
            y = ev.position().y()
            # 우측 ▲/▼ 영역 → 토글 (드래그하지 않음)
            if self._is_in_collapse_button(x, y):
                self._toggle_collapse()
                ev.accept()
                return
            # 타이틀바 나머지 영역 → 드래그 시작
            if y < self.TITLE_H:
                self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
                ev.accept()
                return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev: QMouseEvent):
        # 호버 상태 갱신 (▲/▼ 영역 위에 있으면 강조)
        hover = self._is_in_collapse_button(ev.position().x(), ev.position().y())
        if hover != self._collapse_hover:
            self._collapse_hover = hover
            self.update()

        if self._drag_pos is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)
            ev.accept()
        else:
            super().mouseMoveEvent(ev)

    def leaveEvent(self, ev) -> None:
        if self._collapse_hover:
            self._collapse_hover = False
            self.update()
        super().leaveEvent(ev)

    def mouseReleaseEvent(self, ev: QMouseEvent):
        self._drag_pos = None
        super().mouseReleaseEvent(ev)

    # mouseDoubleClickEvent 제거 — 더블클릭 토글 비활성화 (요구사항).
    # 접기/펼치기는 타이틀바 우측의 ▲/▼ 버튼 단일 클릭으로만 작동.

    # ── 그리기 ────────────────────────────────────────────────────────────
    def paintEvent(self, ev: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # 배경 — 반투명 다크 글래스
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, 14, 14)
        p.setClipPath(path)

        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(30, 30, 45, 230))
        grad.setColorAt(1.0, QColor(20, 20, 30, 240))
        p.fillPath(path, QBrush(grad))

        # 테두리
        p.setClipping(False)
        border_pen = QPen(QColor(80, 80, 120, 150))
        border_pen.setWidth(1)
        p.setPen(border_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(0, 0, w, h, 14, 14)

        # 타이틀바
        title_path = QPainterPath()
        title_path.addRoundedRect(0, 0, w, 36, 14, 14)
        # 아래쪽 모서리는 직각으로
        title_path.addRect(0, 20, w, 16)
        title_grad = QLinearGradient(0, 0, w, 0)
        title_grad.setColorAt(0.0, QColor(50, 50, 80, 200))
        title_grad.setColorAt(1.0, QColor(40, 40, 65, 200))
        p.fillPath(title_path, QBrush(title_grad))

        # 타이틀 텍스트 (왼쪽)
        p.setPen(QPen(QColor(200, 210, 255)))
        p.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        btn_w = self.COLLAPSE_BTN_W
        title_h = self.TITLE_H
        p.drawText(10, 0, w - btn_w - 10, title_h,
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   "⚙ Coach")

        # 접기 버튼 영역 (오른쪽 끝) — 호버 시 배경 강조
        btn_x = w - btn_w
        if self._collapse_hover:
            p.setBrush(QBrush(QColor(255, 255, 255, 40)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(btn_x + 2, 4, btn_w - 6, title_h - 8, 6, 6)

        # 접기 아이콘 (▲ 펼침 / ▼ 접힘)
        p.setPen(QPen(QColor(220, 230, 255)))
        p.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        collapse_icon = "▲" if not self._collapsed else "▼"
        p.drawText(btn_x, 0, btn_w, title_h,
                   Qt.AlignmentFlag.AlignCenter, collapse_icon)

        # 구분선
        if not self._collapsed:
            p.setPen(QPen(QColor(80, 80, 120, 100)))
            p.drawLine(10, title_h, w - 10, title_h)

        p.end()

    # ── 외부 제어 API ─────────────────────────────────────────────────────
    def set_tts_state(self, on: bool):
        self._tts_toggle.checked = on

    def set_yolo_state(self, on: bool):
        self._yolo_toggle.checked = on

    def set_live_state(self, on: bool):
        self._live_toggle.checked = on

    def toggle_visibility(self):
        """Ctrl+Shift+C 핫키 — 보이기/숨기기 전환. 트레이 최소화 상태면 복원."""
        if self.isVisible():
            self.hide()
        else:
            # 트레이에 떠 있는 상태(최소화)에서 핫키를 누른 경우 — 트레이도 같이 정리
            if getattr(self, "_tray", None) is not None and self._tray.isVisible():
                self._tray.hide()
            self.show()
            self.raise_()
