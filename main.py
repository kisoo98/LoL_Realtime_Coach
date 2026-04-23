"""LoL_Realtime_Coach — main entry point.

Loop:
    capture minimap -> YOLO detect -> push to rolling buffer
    check risk score -> auto-alert if > threshold

Hotkey (default F9):
    manual feedback request (summarize buffer -> send JSON + minimap image -> show feedback)
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import keyboard
from loguru import logger

from src.buffer import RollingBuffer
from src.capture import MinimapCapturer
from src.detector import MinimapDetector
from src.notifier import show_feedback
from src.risk_analyzer import RiskAnalyzer
from src.settings import Settings, load_settings


def build_coach(cfg: Settings):
    """Instantiate the LLM coach based on app.llm_provider."""
    provider = (cfg.app.llm_provider or "gemini").lower()
    if provider == "grok":
        from src.grok_client import GrokCoach
        logger.info("LLM provider: Grok (xAI)")
        return GrokCoach(cfg.grok, cfg.xai_api_key)
    if provider == "gemini":
        from src.gemini_client import GeminiCoach
        logger.info(f"LLM provider: Gemini ({cfg.gemini.model})")
        return GeminiCoach(cfg.gemini, cfg.gemini_api_key)
    raise ValueError(
        f"Unknown llm_provider '{provider}'. Use 'gemini' or 'grok'."
    )


def setup_logging(level: str, file: str) -> None:
    Path(file).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level=level)
    logger.add(file, level=level, rotation="10 MB", retention=3)


def main() -> int:
    cfg = load_settings()
    setup_logging(cfg.logging.level, cfg.logging.file)
    logger.info("LoL_Realtime_Coach starting...")

    bbox = cfg.capture.active_bbox()
    capturer = MinimapCapturer(bbox)
    detector = MinimapDetector(
        model_path=cfg.yolo.model_path,
        classes=cfg.yolo.classes,
        conf=cfg.yolo.conf_threshold,
        iou=cfg.yolo.iou_threshold,
        device=cfg.yolo.device,
    )
    buffer = RollingBuffer(window_seconds=cfg.app.buffer_seconds)
    analyzer = RiskAnalyzer()
    coach = build_coach(cfg)

    latest_frame = {"img": None}
    stop_evt = threading.Event()

    def capture_loop() -> None:
        target_dt = 1.0 / max(1, cfg.app.loop_target_fps)
        check_risk_interval = 1.0  # Check risk every 1 second
        last_risk_check = time.time()

        while not stop_evt.is_set():
            t0 = time.perf_counter()
            frame = capturer.grab()
            if frame is not None:
                latest_frame["img"] = frame
                dets = detector.predict(frame)
                buffer.push(dets)

            # Auto-check risk score every 1 second
            now = time.time()
            if now - last_risk_check >= check_risk_interval:
                last_risk_check = now
                summary = buffer.summarize()
                risk_score = analyzer.calculate_risk(summary)

                # Auto-alert if risk is high
                if analyzer.should_trigger_alert(risk_score):
                    logger.info(f"Auto-alert triggered: risk={risk_score:.1f}%")
                    try:
                        text = coach.get_feedback(summary, latest_frame["img"])
                        show_feedback(text)
                    except Exception as e:
                        logger.exception(f"Auto-feedback failed: {e}")
                        show_feedback(f"[오류] 자동 피드백 실패: {e}")

            elapsed = time.perf_counter() - t0
            if elapsed < target_dt:
                time.sleep(target_dt - elapsed)

    def on_hotkey() -> None:
        logger.info("Hotkey pressed -> requesting manual feedback")
        summary = buffer.summarize()
        frame = latest_frame["img"]
        if summary["frames"] == 0:
            logger.warning("No data in buffer yet")
            show_feedback("[대기중] 아직 데이터가 없습니다.")
            return
        try:
            text = coach.get_feedback(summary, frame)
            show_feedback(text)
        except Exception as e:
            logger.exception(f"LLM call failed: {e}")
            show_feedback(f"[오류] 피드백 요청 실패: {e}")

    t = threading.Thread(target=capture_loop, daemon=True)
    t.start()

    keyboard.add_hotkey(cfg.app.hotkey, on_hotkey)
    logger.info("="*60)
    logger.info("✅ LoL_Realtime_Coach Ready!")
    logger.info(f"   🔴 Auto-Alert: Risk > {analyzer.THRESHOLD_AUTO_ALERT}% (every 5s min)")
    logger.info(f"   🔘 Manual Hotkey: Press '{cfg.app.hotkey}' for feedback")
    logger.info(f"   ⏹️  Exit: Press Ctrl+Shift+Q")
    logger.info("="*60)

    try:
        keyboard.wait("ctrl+shift+q")  # graceful exit hotkey
    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
        time.sleep(0.2)
        capturer.close()
        logger.info("Bye.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
