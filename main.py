"""
LoL Realtime Coach -- Demo v0.1
================================
실행:
    conda activate lolcoach
    python main.py

핫키:
    Ctrl+Shift+Q  : 종료
    Ctrl+Shift+C  : 인게임 컨트롤러 패널 보이기/숨기기

LLM 호출은 위험도(0~100)가 자동 알림 임계를 넘고 쿨타임이 풀린 순간에만
자동으로 발생합니다. 작동 확인용 콘솔 로그는 dev 실행 시 stderr에 실시간 출력됩니다.
"""
from __future__ import annotations

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent))

from poc.integrated_main import main  # noqa: E402

if __name__ == "__main__":
    main()
