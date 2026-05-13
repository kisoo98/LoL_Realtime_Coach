# LoLCoach 패키징 / 배포 가이드

PyInstaller 로 Windows 용 onedir exe 를 빌드하고 사이드카 리소스와 함께 배포한다.

## 1. 빌드 환경

- Windows 10/11
- Anaconda/Miniconda 가 설치되어 있고 conda env `lolcoach` 가 준비된 상태
- `feature/poc-final` 브랜치의 최신 코드

```cmd
conda activate lolcoach
python -c "from poc.integrated_overlay import IntegratedOverlay; print('import OK')"
```

import OK 가 떨어지면 빌드 가능 상태다.

## 2. 빌드 실행

리포 루트에서 한 줄:

```cmd
build.bat
```

내부적으로 수행:

1. `conda activate lolcoach`
2. `pyinstaller` 미설치 시 `pip install pyinstaller`
3. 이전 `build/`, `dist/` 삭제
4. `pyinstaller LoLCoach.spec --noconfirm`
5. `configs/`, `models/`, `.env`, `.env.example` 을 `dist\LoLCoach\` 로 복사

빌드 시간은 PC 사양/캐시 상태에 따라 5~15 분.

## 3. 배포 패키지 구조

빌드 후 `dist\LoLCoach\` 안에 다음 구조가 생성된다:

```
LoLCoach\
├─ LoLCoach.exe              ← 진입점
├─ _internal\                ← Python / PyQt / torch / ultralytics 등 런타임
├─ configs\
│   └─ config.yaml
├─ models\
│   ├─ best.pt
│   └─ champion_classifier.pt
├─ .env                       ← 사용자별 API 키 (배포 패키지에는 .env.example 만)
└─ .env.example
```

배포 시 `dist\LoLCoach\` 폴더 전체를 zip 으로 묶어 전달. 사용자는 압축 해제 후 `.env`
를 자기 API 키로 채우고 `LoLCoach.exe` 더블클릭으로 실행.

## 4. 사용자 셋업 매뉴얼 요약

1. zip 압축 해제 (한글 경로 피하기 — `C:\LoLCoach\` 권장)
2. `.env.example` 을 `.env` 로 복사하고 안의 `GEMINI_API_KEY=` 값을 본인 키로 교체
3. 리그 오브 레전드 클라이언트 1920×1080 풀스크린 또는 가짜 풀스크린 실행
4. `LoLCoach.exe` 더블클릭 (Windows Defender 첫 실행 경고 시 "추가 정보" → "실행")
5. 우측 하단에 ⚙ Coach 컨트롤러 패널이 뜨면 정상

## 5. 트러블슈팅 체크리스트

| 증상                                  | 원인 / 대처                                          |
|---|---|
| 더블클릭해도 아무 창도 안 뜸           | `_internal\` 폴더가 빠짐 — zip 압축/해제 다시         |
| 콘솔에 `ImportError: ...`              | `LoLCoach.spec` 의 `_hiddenimports` 보강 후 재빌드    |
| `models\best.pt` not found             | `models\` 폴더 복사 누락 — `build.bat` 재실행         |
| Gemini 401 / 키 오류                   | `.env` 의 `GEMINI_API_KEY` 값 확인                    |
| 글로벌 핫키(Ctrl+Shift+C/Q) 무반응     | UAC — `LoLCoach.exe` 마우스 우클릭 → "관리자 권한 실행" |
| 트레이 아이콘이 안 보임                | 시스템 트레이 알림 영역 설정에서 "LoLCoach" 허용      |
| Windows Defender 가 차단               | 코드 서명 미적용 — "추가 정보" → "실행" 또는 예외 등록 |

## 6. 콘솔 / 윈도우드 모드 전환

첫 빌드는 디버그 편의를 위해 **콘솔 ON** (`LoLCoach.spec` 의 `console=True`).
시연 직전 콘솔 창이 거슬리면 spec 의 한 줄만 바꿔서 재빌드:

```python
# LoLCoach.spec
console=False,
```

```cmd
build.bat
```

이러면 검은 cmd 창 없이 트레이/오버레이만 뜨는 윈도우드 모드.

## 7. 아이콘 적용 (선택)

`.ico` 파일을 `assets\coach.ico` 로 두고 `LoLCoach.spec` 에서 두 줄을 살린다:

```python
# EXE(...) 안
icon="assets/coach.ico",
```

QSystemTrayIcon 도 자동으로 같은 아이콘을 사용하려면 `integrated_main.py` 의 main 진입부에:

```python
from PyQt6.QtGui import QIcon
from poc.paths import APP_ROOT
app.setWindowIcon(QIcon(str(APP_ROOT / "assets" / "coach.ico")))
```

## 8. 사이즈 줄이기 (시간 여유 있을 때)

- `torch` CPU-only 빌드 권장 (PC 가 CPU 추론 중일 때만):
  ```cmd
  pip uninstall torch torchvision
  pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
  ```
  최종 dist 사이즈가 ~50% 감소.
- UPX 압축은 안티바이러스 오탐 확률을 높이므로 권장하지 않음.
