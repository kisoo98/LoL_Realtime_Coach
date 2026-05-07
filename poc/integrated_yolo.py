"""
YOLO β 파이프라인 + 위험도 산정 + Gemini 피드백 호출 스레드.

흐름:
  MinimapCapturer.grab() → TwoStageDetectorV2.predict()
    → RiskAnalyzer.calculate_risk(): 멀티팩터 v2.1 위험도 0~100점
    → 임계 초과 + 쿨타임 OK 시 GeminiCoach.get_feedback() 호출
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal
from loguru import logger

from poc.integrated_constants import (
    RISK_ALERT_COOLDOWN,
    RISK_AUTO_ALERT,
)
from poc.integrated_helpers import bbox_center

# 프로젝트 루트 — config / 모델 파일 경로 기준점
_REPO_ROOT = Path(__file__).resolve().parent.parent

# ── 핵심 의존성 (src 모듈) ───────────────────────────────────────────────────
try:
    from src.capture import MinimapCapturer
    from src.gemini_client import GeminiCoach
    from src.risk_analyzer import RiskAnalyzer
    from src.settings import load_settings
    from src.two_stage_detector import TwoStageDetectorV2
    CORE_AVAILABLE = True
except Exception as _err:  # pragma: no cover
    print(f"[경고] src 모듈 로드 실패 → YOLO/Gemini 비활성: {_err}")
    CORE_AVAILABLE = False


class YoloCoachThread(QThread):
    """YOLO β + 위험도 + Gemini 피드백 통합 스레드."""

    feedback_signal = pyqtSignal(str)    # Gemini 피드백 텍스트
    risk_signal     = pyqtSignal(float)  # 위험도 0~100
    status_signal   = pyqtSignal(str)    # 상태 메시지

    def __init__(self):
        super().__init__()
        self.running = True
        self._manual_request = threading.Event()
        self._latest_frame   = None
        self._frame_lock     = threading.Lock()
        # Live API 에서 수신한 내 챔피언 영문명
        self._my_champ: str  = ""
        self._champ_lock     = threading.Lock()
        # Live API 에서 수신한 게임의 10명 챔피언 리스트 (필터링용)
        self._valid_champs: set = set()
        self._champ_list_lock = threading.Lock()
        # 위험도 산정 (v2.1 멀티팩터, 쿨타임 관리 포함)
        self._risk_analyzer  = RiskAnalyzer() if CORE_AVAILABLE else None

    # ── 외부 API ─────────────────────────────────────────────────────────────
    def set_my_champion(self, champ_name: str) -> None:
        """LiveClientThread → 내 챔피언명 갱신 (스레드 안전)."""
        with self._champ_lock:
            self._my_champ = champ_name

    def set_champ_list(self, champ_list: set) -> None:
        """LiveClientThread → 게임의 10명 챔피언 리스트 갱신 (필터링용, 스레드 안전)."""
        with self._champ_list_lock:
            self._valid_champs = champ_list.copy() if champ_list else set()
        logger.debug(f"[필터링] 유효한 챔피언 목록 갱신: {len(self._valid_champs)}명")

    def request_manual(self) -> None:
        """F9 핫키 → 수동 피드백."""
        self._manual_request.set()

    # ── 메인 루프 ────────────────────────────────────────────────────────────
    def run(self) -> None:
        if not CORE_AVAILABLE:
            self.status_signal.emit("⚠ src 모듈 없음 — YOLO/Gemini 비활성")
            return

        # 설정 로드 ────────────────────────────────────────────────────────
        try:
            cfg = load_settings(
                config_path=_REPO_ROOT / "configs" / "config.yaml",
                env_path=_REPO_ROOT / ".env",
            )
        except Exception as e:
            self.status_signal.emit(f"⚠ 설정 로드 실패: {e}")
            return

        # 컴포넌트 초기화 ──────────────────────────────────────────────────
        try:
            capturer = MinimapCapturer(cfg.capture.active_bbox())
            # β 파이프라인: A'(검출) + F(팀 분류) + B(챔피언 분류)
            detector = TwoStageDetectorV2(
                model_a_path=_REPO_ROOT / "models" / "lol_minimap_1class_l.pt",
                model_b_path=_REPO_ROOT / "models" / "champion_classifier.pt",
                device=cfg.yolo.device,
                det_conf=cfg.yolo.conf_threshold,
                det_iou=cfg.yolo.iou_threshold,
            )
            coach = GeminiCoach(cfg.gemini, cfg.gemini_api_key)
        except Exception as e:
            self.status_signal.emit(f"⚠ 컴포넌트 초기화 실패: {e}")
            return

        self.status_signal.emit("✅ YOLO β + Gemini 준비 완료")
        target_dt = 1.0 / max(1, cfg.app.loop_target_fps)

        while self.running:
            t0 = time.perf_counter()

            # 캡처 ────────────────────────────────────────────────────────
            frame = None
            try:
                frame = capturer.grab()
                if frame is not None:
                    with self._frame_lock:
                        self._latest_frame = frame
            except Exception as e:
                logger.debug(f"캡처 오류: {e}")

            # 감지 + 위험도 + 자동 알림 ─────────────────────────────────
            if frame is not None:
                with self._champ_lock:
                    my_champ = self._my_champ
                with self._champ_list_lock:
                    valid_champs = self._valid_champs.copy()

                try:
                    result = detector.predict(
                        frame,
                        my_champion_name=my_champ or None,
                        valid_champs=valid_champs or None,
                    )
                    risk = self._risk_analyzer.calculate_risk(result)
                    self.risk_signal.emit(risk)

                    if self._risk_analyzer.should_trigger_alert(risk):
                        self._send_llm_feedback(coach, result)
                except Exception as e:
                    logger.debug(f"감지/위험도 오류: {e}")

            # 수동 요청 (F9) ─────────────────────────────────────────────
            if self._manual_request.is_set():
                self._manual_request.clear()
                if frame is not None:
                    try:
                        with self._champ_list_lock:
                            valid_champs = self._valid_champs.copy()
                        result = detector.predict(
                            frame,
                            my_champion_name=self._my_champ or None,
                            valid_champs=valid_champs or None,
                        )
                        self._risk_analyzer.reset_cooldown()  # F9: 쿨타임 무시
                        self._send_llm_feedback(coach, result)
                    except Exception as e:
                        self.feedback_signal.emit(f"[오류] Gemini 요청 실패: {e}")
                else:
                    self.feedback_signal.emit("[대기 중] 미니맵 캡처 없음")

            elapsed = time.perf_counter() - t0
            if elapsed < target_dt:
                time.sleep(target_dt - elapsed)

        try:
            capturer.close()
        except Exception:
            pass

    # ── 헬퍼 ─────────────────────────────────────────────────────────────────
    def _send_llm_feedback(self, coach, result: dict) -> None:
        """Gemini에 현재 상황을 보내고 피드백을 시그널로 전달."""
        summary = {
            "ally_count":  len(result.get("ally", [])),
            "enemy_count": len(result.get("enemy", [])),
            "my_position": bbox_center(result.get("my_position")),
            "enemies": [
                {
                    "champ": e.top1,
                    "conf":  round(e.top1_conf, 2),
                    "pos":   bbox_center(e),
                }
                for e in result.get("enemy", [])
            ],
        }
        with self._frame_lock:
            frame_snap = self._latest_frame
        try:
            text = coach.get_feedback(summary, frame_snap)
            self.feedback_signal.emit(text or "[응답 없음]")
        except Exception as e:
            self.feedback_signal.emit(f"[오류] Gemini 요청 실패: {e}")

    def stop(self) -> None:
        self.running = False
        self.wait()
