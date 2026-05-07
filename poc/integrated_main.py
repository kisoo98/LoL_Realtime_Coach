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
수동 피드백:
  F9 (글로벌 핫키) → Gemini에 즉시 요청
"""
from __future__ import annotations

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 — poc/ 안에서 직접 실행해도 src/* 임포트 가능
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from PyQt6.QtWidgets import QApplication  # noqa: E402
from loguru import logger  # noqa: E402

from poc.integrated_live import LIVE_API_AVAILABLE  # noqa: E402
from poc.integrated_overlay import IntegratedOverlay  # noqa: E402
from poc.integrated_voice import TTS_AVAILABLE  # noqa: E402
from poc.integrated_yolo import CORE_AVAILABLE  # noqa: E402


def _setup_logger() -> None:
    log_dir = _REPO_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level="INFO")
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
    logger.info("  F9: manual feedback  |  Ctrl+Shift+Q: quit")
    logger.info("=" * 60)

    app = QApplication(sys.argv)
    overlay = IntegratedOverlay()
    overlay.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
