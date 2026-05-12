"""
LoL Realtime Coach -- Demo v0.1
================================
실행:
    conda activate lolcoach
    python main.py

핫키:
    F9            : 즉시 Gemini 코칭 요청
    Ctrl+Shift+Q  : 종료
"""
from __future__ import annotations

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent))

from poc.integrated_main import main  # noqa: E402

if __name__ == "__main__":
    main()
