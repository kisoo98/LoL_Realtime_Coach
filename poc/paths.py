"""
런타임 경로 헬퍼 — 개발(소스) 실행과 PyInstaller 번들(exe) 실행을 모두 지원.

사용처:
    from poc.paths import APP_ROOT, BUNDLE_ROOT

- APP_ROOT
    사용자가 보는 '앱 루트'. configs/.env/models/logs 가 모여 있는 위치.
    - 개발 모드     : <repo>/                    (이 파일의 두 단계 상위)
    - 번들(exe) 모드: <exe가 있는 폴더>/         (사이드카 리소스 위치)

- BUNDLE_ROOT
    PyInstaller 가 풀어놓은 임시 디렉터리(_MEIPASS).
    번들 안에 read-only 리소스를 넣고 싶을 때 사용.
    - 개발 모드     : APP_ROOT 와 동일
    - 번들 모드     : sys._MEIPASS 경로
"""
from __future__ import annotations

import sys
from pathlib import Path


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """사용자가 직접 다루는 사이드카 리소스(.env / configs / models / logs) 의 루트."""
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundle_root() -> Path:
    """PyInstaller 번들 내부 read-only 루트. 개발 모드에서는 app_root() 와 동일."""
    if _is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return app_root()


# 모듈 임포트 시 한 번만 평가
APP_ROOT:    Path = app_root()
BUNDLE_ROOT: Path = bundle_root()
