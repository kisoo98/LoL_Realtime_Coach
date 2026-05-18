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
from poc.paths import APP_ROOT

# 사이드카 리소스 루트 — config / 모델 / .env 의 기준점 (exe 옆 폴더 또는 repo 루트)
_REPO_ROOT = APP_ROOT

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
        self._latest_frame   = None
        self._frame_lock     = threading.Lock()
        # [RISK] 콘솔 로그 throttle (초). 매 프레임 찍지 않고 5초당 1회.
        self._risk_log_interval = 5.0
        self._last_risk_log_t   = 0.0
        # Live API 에서 수신한 내 챔피언 영문명
        self._my_champ: str  = ""
        self._champ_lock     = threading.Lock()
        # Live API 에서 수신한 게임의 10명 챔피언 리스트 (필터링용)
        self._valid_champs: set = set()
        self._champ_list_lock = threading.Lock()
        # 위험도 산정 (v2.1 멀티팩터, 쿨타임 관리 포함)
        self._risk_analyzer  = RiskAnalyzer() if CORE_AVAILABLE else None
        # 일시정지 플래그 (컨트롤러 YOLO 토글에서 set)
        self._paused = False

    # ── 외부 API ─────────────────────────────────────────────────────────────
    def pause(self) -> None:
        """YOLO 파이프라인 일시정지 (스레드는 살아있되 캡처·감지를 건너뜀)."""
        self._paused = True

    def resume(self) -> None:
        """YOLO 파이프라인 재개."""
        self._paused = False

    def set_my_champion(self, champ_name: str) -> None:
        """LiveClientThread → 내 챔피언명 갱신 (스레드 안전)."""
        with self._champ_lock:
            self._my_champ = champ_name

    def set_champ_list(self, champ_list: set) -> None:
        """LiveClientThread → 게임의 10명 챔피언 리스트 갱신 (필터링용, 스레드 안전)."""
        with self._champ_list_lock:
            self._valid_champs = champ_list.copy() if champ_list else set()
        logger.debug(f"[필터링] 유효한 챔피언 목록 갱신: {len(self._valid_champs)}명")

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
                model_a_path=_REPO_ROOT / "models" / "best.pt",
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

            # 일시정지 상태면 캡처·감지를 건너뜀
            if self._paused:
                time.sleep(target_dt)
                continue

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

                    # ── 위험도 콘솔 로그 (작동 확인용, 5초 throttle) ─────────
                    # 위험도 계산은 매 프레임 그대로, 콘솔 출력만 self._risk_log_interval
                    # 초 간격으로 제한. LLM 트리거 시점은 [LLM-TRIGGER]/[LLM-REQ]
                    # 라인이 별도로 찍히므로 throttle해도 가시성 손실 없음.
                    now_t = time.perf_counter()
                    if (now_t - self._last_risk_log_t) >= self._risk_log_interval:
                        self._last_risk_log_t = now_t
                        ally_n  = len(result.get("ally", []))
                        enemy_n = len(result.get("enemy", []))
                        my_pos  = bbox_center(result.get("my_position"))
                        my_pos_s = f"({my_pos[0]:.0f},{my_pos[1]:.0f})" if my_pos else "—"
                        logger.info(
                            f"[RISK] {risk:5.1f}/100  ally={ally_n} enemy={enemy_n} "
                            f"my={my_champ or '?'}@{my_pos_s}"
                        )

                    if self._risk_analyzer.should_trigger_alert(risk):
                        logger.warning(
                            f"[LLM-TRIGGER] auto  risk={risk:.1f} "
                            f"(threshold={RISK_AUTO_ALERT}, cooldown={RISK_ALERT_COOLDOWN}s)"
                        )
                        self._send_llm_feedback(coach, result)
                except Exception as e:
                    logger.exception(f"감지/위험도 오류: {e}")

            elapsed = time.perf_counter() - t0
            if elapsed < target_dt:
                time.sleep(target_dt - elapsed)

        try:
            capturer.close()
        except Exception:
            pass

    # ── 헬퍼 ─────────────────────────────────────────────────────────────────
    def _send_llm_feedback(self, coach, result: dict) -> None:
        """Gemini에 현재 상황을 보내고 피드백을 시그널로 전달.

        자동 호출은 risk≥RISK_AUTO_ALERT 임계에서만 트리거된다.
        """
        import json as _json

        # 위험도 점수/레벨을 LLM에 명시적으로 전달 → 톤 차별화 가능 (v2.1)
        risk = float(getattr(self._risk_analyzer, "last_risk", 0.0))
        if risk < 31:
            risk_level = "낮음"
        elif risk < 65:
            risk_level = "보통"
        elif risk < 85:
            risk_level = "높음"
        else:
            risk_level = "매우높음"

        summary = {
            "risk_score":  round(risk, 1),
            "risk_level":  risk_level,
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
        # frame_snap 은 MinimapCapturer.grab() 결과 = numpy ndarray (BGR, H×W×C).
        # PIL.Image.size 는 (w,h) 튜플이지만 ndarray.size 는 총 원소수(int) 라
        # 과거 코드 `frame_snap.size[0]` 가 TypeError 를 일으켰음 — shape 으로 교체.
        if frame_snap is None:
            frame_info = "None"
        elif hasattr(frame_snap, "shape") and len(frame_snap.shape) >= 2:
            frame_info = f"{frame_snap.shape[1]}x{frame_snap.shape[0]}"
        elif hasattr(frame_snap, "size") and isinstance(frame_snap.size, tuple):
            frame_info = f"{frame_snap.size[0]}x{frame_snap.size[1]}"
        else:
            frame_info = "unknown"

        # ── 요청 payload 콘솔 출력 (전문) ──────────────────────────────────────
        logger.info(
            f"[LLM-REQ] risk={risk:.1f} ({risk_level})  frame={frame_info}"
        )
        try:
            payload_str = _json.dumps(summary, indent=2, ensure_ascii=False, default=str)
        except Exception:
            payload_str = repr(summary)
        logger.info(f"[LLM-REQ] payload:\n{payload_str}")

        t_start = time.perf_counter()
        try:
            text = coach.get_feedback(summary, frame_snap)
            dt_ms = (time.perf_counter() - t_start) * 1000
            n_chars = len(text or "")
            logger.success(
                f"[LLM-RESP] OK  {dt_ms:6.0f}ms  ({n_chars} chars)"
            )
            logger.info(f"[LLM-RESP] full text:\n{text or '[empty]'}")
            self.feedback_signal.emit(text or "[응답 없음]")
        except Exception as e:
            dt_ms = (time.perf_counter() - t_start) * 1000
            msg = str(e).lower()
            if "timeout" in msg or "deadline" in msg or "504" in msg:
                logger.error(f"[LLM-RESP] TIMEOUT after {dt_ms:.0f}ms: {e}")
                self.feedback_signal.emit("[지연] LLM 응답 지연 — 곧 재시도합니다")
            else:
                logger.exception(f"[LLM-RESP] FAILED after {dt_ms:.0f}ms: {e}")
                self.feedback_signal.emit(f"[오류] Gemini 요청 실패: {e}")

    def stop(self) -> None:
        self.running = False
        self.wait()
