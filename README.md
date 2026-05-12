# LoL Realtime Coach

LoL 게임 중 미니맵을 실시간 분석해 위험 상황을 코칭해주는 오버레이 앱.

> **버전**: Demo v0.1  
> **상태**: 팀 내부 테스트용 (feature/poc-integration)  
> **외부 마감**: 2026-05-18

---

## 주요 기능 (Demo v0.1)

- **YOLO 미니맵 감지** — 실시간 캡처 + 챔피언 아이콘 인식 (172개 챔피언)
- **팀 분류** — HSV 링 색 분석으로 아군/적군 자동 구분 (정확도 98.86%)
- **위험도 산정 v2.1** — 거리 + 수치 우위 + 집중도 + 신뢰도 멀티팩터 (0~100점)
- **Gemini LLM 코칭** — 위험도 ≥ 65 시 자동 호출 (10초 쿨타임)
- **음성 TTS** — gTTS 기반 한국어 코칭 음성
- **Live Client API** — 내 챔피언/10명 목록 자동 수신

---

## 팀원 셋업 가이드

### 필요 사항

- Windows 10/11
- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) 또는 Anaconda
- Gemini API Key ([무료 발급](https://aistudio.google.com/app/apikey))
- 모델 파일 (`models/` 폴더) — 기수에게 요청

### 1. 저장소 클론

```bash
git clone https://github.com/<org>/LoL_Realtime_Coach.git
cd LoL_Realtime_Coach
git checkout feature/poc-integration
```

### 2. Conda 환경 생성

```bash
conda create -n lolcoach python=3.11 -y
conda activate lolcoach
pip install PyQt6 ultralytics loguru gtts pygame keyboard requests opencv-python
pip install "google-generativeai>=0.8"
```

> **주의**: 반드시 `lolcoach` 환경에서 실행하세요. base 환경은 PyQt6 DLL 충돌 발생.

### 3. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 Gemini API Key 입력:

```
GEMINI_API_KEY=your-actual-key-here
```

### 4. 모델 파일 배치

`models/` 폴더에 다음 파일이 있어야 합니다:

```
models/
  lol_minimap_1class_l.pt     # A' 모델 (챔피언 위치 감지)
  champion_classifier.pt      # B 모델 (챔피언 분류)
```

파일이 없으면 기수(황기수)에게 공유 요청.

### 5. 미니맵 좌표 설정

`configs/config.yaml`에서 본인 모니터 해상도 확인:

```yaml
capture:
  active_resolution: "1920x1080"   # 본인 해상도로 변경
```

지원 해상도: `1920x1080`, `2560x1440`, `3840x2160`

---

## 실행

```bash
conda activate lolcoach
cd LoL_Realtime_Coach
python main.py
```

### 핫키

| 키 | 기능 |
|---|---|
| **F9** | 즉시 Gemini 코칭 요청 (쿨타임 무시) |
| **Ctrl+Shift+Q** | 앱 종료 |

---

## 동작 조건

- LoL 게임이 **실행 중**이어야 합니다 (Live Client API 자동 연결)
- 미니맵이 화면 **우측 하단**에 있어야 합니다 (기본 설정)
- 게임이 없으면 YOLO 감지는 동작하지만 내 챔피언 정보는 없음

---

## 위험도 계산 기준 (v2.1)

| 범위 | 상태 | LLM 호출 |
|------|------|---------|
| 0~30 | 🟢 안전 | X |
| 31~65 | 🟡 주의 | X |
| 66~100 | 🔴 위험 | O (10초 쿨타임) |

세부 계산 방식: `LoL_Realtime_Coach_Official_Rules.md` 참고

---

## 테스트 실행

```bash
conda activate lolcoach
cd LoL_Realtime_Coach
python tests/test_risk_analyzer.py
```

---

## 프로젝트 구조

```
poc/
  integrated_main.py       # 진입점 (python main.py)
  integrated_yolo.py       # YOLO + 위험도 + Gemini 스레드
  integrated_live.py       # Live Client API 스레드
  integrated_overlay.py    # PyQt6 오버레이 UI
  integrated_constants.py  # 상수 정의
  integrated_helpers.py    # 공통 헬퍼
  integrated_tips.py       # 규칙 기반 코칭 팁
  integrated_voice.py      # TTS 스레드

src/
  risk_analyzer.py         # 위험도 계산 모듈 (v2.1)
  two_stage_detector.py    # A' + F + B 3단계 파이프라인
  capture.py               # 미니맵 캡처
  gemini_client.py         # Gemini API 클라이언트
  settings.py              # 설정 로더

configs/
  config.yaml              # 앱 설정 (해상도, LLM 등)

models/
  lol_minimap_1class_l.pt  # 챔피언 위치 감지 모델
  champion_classifier.pt   # 챔피언 분류 모델

tests/
  test_risk_analyzer.py    # 위험도 모듈 단위 테스트
```

---

## 팀

| 이름 | 역할 | 담당 |
|------|------|------|
| 황기수 | AI/ML + PM | YOLO 학습, LLM 연동, 아키텍처, 문서화 |
| 한승우 | 프론트엔드 | 오버레이 UI, 위험도 시각화 |
| 박창민 | 백엔드 | Riot API 연동 |
| 김대원 | 데이터 엔지니어 | 미니맵 데이터 수집/라벨링 |

---

**공식 규칙 문서**: `LoL_Realtime_Coach_Official_Rules.md`
