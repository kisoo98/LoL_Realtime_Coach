"""
LoL Realtime Coach — 최종 PoC 통합본 (entry point)
====================================================
모든 실제 로직은 모듈로 분리되어 있다:

  poc/integrated_constants.py — 위험도 임계 / 표시 시간 등 상수
  poc/integrated_helpers.py   — bbox_center, parse_raw_champ_name
  poc/integrated_tips.py      — 규칙 기반 코칭/이벤트 팁
  poc/integrated_voice.py     — VoiceThread (gTTS + pygame)
  poc/integrated_yolo.py      — YoloCoachThread (β 파이프라인 + Gemini)
  poc/integrated_live.py      — LiveClientThread (Live Client API)
  poc/integrated_overlay.py   — IntegratedOverlay (PyQt6 풀스크린 위젯)

실행:
  conda activate lolcoach
  cd <repo_root>
  python poc/integrated_main.py

종료:
  Ctrl+C  또는  Ctrl+Shift+Q (글로벌 핫키)
컨트롤러 토글:
  Ctrl+Shift+C (글로벌 핫키) → 인게임 컨트롤러 패널 보이기/숨기기
"""
from __future__ import annotations

import sys
from pathlib import Path

# 개발 모드에서만 sys.path 보강 (PyInstaller 번들은 자체 import 트리 사용)
if not getattr(sys, "frozen", False):
    _DEV_REPO_ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_DEV_REPO_ROOT))

from PyQt6.QtWidgets import QApplication  # noqa: E402
from loguru import logger  # noqa: E402

from poc.integrated_live import LIVE_API_AVAILABLE  # noqa: E402
from poc.integrated_overlay import IntegratedOverlay  # noqa: E402
from poc.integrated_voice import TTS_AVAILABLE  # noqa: E402
from poc.integrated_yolo import CORE_AVAILABLE  # noqa: E402
from poc.paths import APP_ROOT  # noqa: E402


def _setup_logger() -> None:
    log_dir = APP_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    # PyInstaller windowed 모드(console=False)에서는 sys.stderr 가 None.
    # 콘솔이 살아 있을 때만 stderr sink 등록 — 그 외에는 파일 로그만.
    #
    # 작동 테스트/녹화 시: `python main.py` 로 dev 실행하면 콘솔이 자동으로 연결되어
    #   [RISK] 매 프레임 위험도
    #   [LLM-TRIGGER] 자동 호출 트리거 (risk≥임계 + 쿨타임 OK)
    #   [LLM-REQ]  요청 payload 전문
    #   [LLM-RESP] 응답 소요시간 + 응답 전문
    # 라인이 실시간으로 보입니다.
    if sys.stderr is not None:
        logger.add(
            sys.stderr,
            level="DEBUG",
            format=(
                "<green>{time:HH:mm:ss.SSS}</green> "
                "| <level>{level: <8}</level> "
                "| <cyan>{message}</cyan>"
            ),
            colorize=True,
            backtrace=False,
            diagnose=False,
        )
    logger.add(
        str(log_dir / "integrated_poc.log"),
        level="DEBUG", rotation="10 MB", retention=3,
    )


def main() -> None:
    _setup_logger()

    logger.info("=" * 60)
    logger.info("  LoL Realtime Coach -- Final PoC")
    logger.info("  YOLO beta : %s", "OK" if CORE_AVAILABLE else "DISABLED")
    logger.info("  Live API  : %s", "OK" if LIVE_API_AVAILABLE else "DISABLED")
    logger.info("  TTS       : %s", "OK" if TTS_AVAILABLE else "DISABLED")
    logger.info("  Ctrl+Shift+Q: quit  |  Ctrl+Shift+C: toggle controller")
    logger.info("=" * 60)

    app = QApplication(sys.argv)


    overlay = IntegratedOverlay()
    overlay.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
