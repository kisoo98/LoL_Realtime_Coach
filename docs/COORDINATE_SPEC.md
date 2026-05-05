# 좌표 양식 스펙 (Coordinate Specification)

> **작성자:** 박창민  
> **버전:** v1.1 초안 (팀 리뷰 후 확정)  
> **최종 수정:** 2026-04-30  
> **목적:** YOLO 탐지 결과 ↔ 위험도 엔진 ↔ LLM 프롬프트 간 좌표 데이터 인터페이스 통일

---

## 0. 왜 이 좌표 양식인가 (설계 근거)

### 0-1. 왜 0~1 정규화 비율인가

절대 픽셀 좌표 대신 0.0~1.0 비율 좌표를 쓰는 이유는 세 가지다.

첫째, **해상도 독립성**. 1920×1080, 2560×1440, 3840×2160 등 어떤 해상도에서 게임을 실행해도 좌표 의미가 동일하다. 미니맵의 절대 픽셀 위치와 크기는 해상도마다 달라지지만, 비율 좌표는 항상 "미니맵 내 상대 위치"를 나타낸다. 이후 HUD 스케일 설정이 바뀌어도 `coord_parser.py`의 bbox 값만 수정하면 된다.

둘째, **거리 계산의 직관성**. 두 챔피언의 유클리드 거리가 곧 미니맵 전체 대각선 대비 비율이 된다. 예를 들어 거리 0.10이면 "미니맵 대각선의 10%만큼 떨어져 있다"로 해석할 수 있어, 위험도 임계값 설정이 픽셀 기반보다 훨씬 직관적이다.

셋째, **LLM 프롬프트 효율**. 절대 픽셀 값(예: 1742, 893)은 LLM에게 의미 없는 숫자지만, 비율 좌표(0.72, 0.35)는 "미니맵 우측 상단 부근"으로 맥락 추론이 가능하다. 토큰 수도 절약된다.

### 0-2. 왜 JSON인가

CSV나 protobuf 같은 대안도 있지만, 이 프로젝트에서 JSON을 선택한 이유는 다음과 같다.

- YOLO 추론 결과를 Python dict에서 바로 `json.dumps()` 가능 — 별도 직렬화 불필요
- LLM 프롬프트에 그대로 삽입할 수 있는 포맷 (ChatGPT/Claude 모두 JSON 파싱에 최적화)
- 팀원 전원이 읽고 디버깅 가능한 사람이 읽을 수 있는 형식(human-readable)
- Live Client API 응답 자체가 JSON이므로 데이터 파이프라인 전체가 단일 포맷으로 통일

### 0-3. 좌표계 방향 선택

`(0,0) = 좌상단`으로 정한 이유는 YOLO 출력 좌표계(이미지 좌상단 원점)와 일치시키기 위함이다. 변환 없이 YOLO 바운딩 박스 중심점을 그대로 정규화하면 본 양식이 된다.

---

## 1. 기본 원칙

- 모든 좌표는 **미니맵 기준 정규화 비율 (0.0 ~ 1.0)** 사용
- `(0.0, 0.0)` = 미니맵 **좌상단** (블루팀 기지 방향)
- `(1.0, 1.0)` = 미니맵 **우하단** (레드팀 기지 방향)
- 절대 픽셀 좌표는 `coord_parser.py`가 변환 담당

```
(0,0) ──────────────── (1,0)
  │                      │
  │    미니맵 영역         │
  │                      │
(0,1) ──────────────── (1,1)
```

---

## 2. 단일 챔피언 좌표 오브젝트

```json
{
  "champion": "Jinx",
  "x": 0.72,
  "y": 0.35,
  "team": "enemy",
  "confidence": 0.91,
  "timestamp": 1234567890.123
}
```

| 필드 | 타입 | 설명 | 값 범위 |
|---|---|---|---|
| `champion` | string | 챔피언 이름 (YOLO 클래스명 기준) | 예: `"Jinx"`, `"Unknown"` |
| `x` | float | 미니맵 가로 위치 (좌→우) | `0.0 ~ 1.0` |
| `y` | float | 미니맵 세로 위치 (위→아래) | `0.0 ~ 1.0` |
| `team` | string | 소속 팀 | `"ally"` / `"enemy"` |
| `confidence` | float | YOLO 탐지 신뢰도 | `0.0 ~ 1.0` |
| `timestamp` | float | 탐지 시각 (Unix time) | `time.time()` |

---

## 3. 프레임 단위 탐지 결과 (YOLO → coordinator 전달 형식)

```json
{
  "frame_time": 1234567890.123,
  "game_time": 342.5,
  "detections": [
    { "champion": "Jinx",    "x": 0.72, "y": 0.35, "team": "enemy",  "confidence": 0.91 },
    { "champion": "Thresh",  "x": 0.68, "y": 0.40, "team": "enemy",  "confidence": 0.85 },
    { "champion": "Unknown", "x": 0.30, "y": 0.65, "team": "ally",   "confidence": 0.78 }
  ]
}
```

---

## 4. coordinator 출력 형식 (위험도 엔진 입력)

`risk_analyzer.py`의 `RiskAnalyzer.calculate_risk(summary)` 입력 형식:

```json
{
  "frames": 15,
  "duration": 5.0,
  "tracks": {
    "enemy_champion": [
      [0.0, 0.72, 0.35],
      [0.5, 0.73, 0.34]
    ],
    "ally_champion": [
      [0.0, 0.30, 0.65]
    ]
  }
}
```

`tracks` 배열 원소: `[상대시각(초), x, y]`

---

## 5. YOLO 클래스명 → team 매핑

`config.yaml`의 YOLO 클래스 기준:

| YOLO 클래스 | team 값 | 설명 |
|---|---|---|
| `blue_top`, `blue_jungle`, `blue_mid`, `blue_adc`, `blue_support` | `"ally"` | 아군 (블루팀 기준) |
| `red_top`, `red_jungle`, `red_mid`, `red_adc`, `red_support` | `"enemy"` | 적군 (레드팀 기준) |
| `ward` | `"ward"` | 와드 |
| `objective` | `"objective"` | 오브젝트 (바론/드래곤) |

> ⚠️ **팀 방향 주의:** 본인이 블루팀이면 `blue_*` = ally, 레드팀이면 반대. `coordinator.py`에서 처리.

---

## 6. Live Client API 보조 데이터 (coord_parser 불필요)

Live Client API는 좌표를 제공하지 않으므로 아래 필드를 **보조 정보**로만 사용:

```json
{
  "game_time": 342.5,
  "my_hp_ratio": 0.85,
  "my_team": "ORDER",
  "enemy_status": [
    { "championName": "직스", "isDead": true,  "respawnTimer": 12.3 },
    { "championName": "뽀삐", "isDead": false, "respawnTimer": 0.0  }
  ]
}
```

사망한 적은 위험도 판단에서 제외하거나 가중치 감소에 활용.

---

## 7. 좌표 변환 공식

```python
# 미니맵 bbox 예시 (1920x1080 기준): [1625, 815, 1920, 1080]
# bbox = [left, top, right, bottom]

norm_x = (pixel_x - bbox_left)  / (bbox_right  - bbox_left)
norm_y = (pixel_y - bbox_top)   / (bbox_bottom - bbox_top)
```

자세한 구현은 `src/coord_parser.py` 참고.

---

## 8. 파일 형태 및 저장 규칙

### 8-1. 실시간 파일 (매 폴링마다 덮어쓰기)

파일명: `game_data_latest.json`

이 파일은 게임 진행 중 매 폴링(약 1초)마다 최신 스냅샷으로 덮어쓴다. 다른 모듈(위험도 엔진, LLM 호출)이 이 파일을 읽어 현재 상태를 파악한다. 게임 종료 시 삭제된다.

### 8-2. 세션 기록 파일 (게임 종료 시 1회 저장)

파일명: `game_data_YYYYMMDD_HHMMSS.json`

게임 한 판의 전체 스냅샷 기록. 디버깅, 리플레이 분석, 모델 개선용으로 보관한다.

```json
{
  "session_start": "20260430_143022",
  "total_snapshots": 1200,
  "snapshots": [
    { "poll_index": 1, "collected_at": "2026-04-30T14:30:23", "game_time": 1.2, "detections": [...] },
    { "poll_index": 2, "collected_at": "2026-04-30T14:30:24", "game_time": 2.1, "detections": [...] }
  ]
}
```

### 8-3. 좌표 양식 파일 자체의 위치

```
프로젝트 루트/
├── docs/
│   ├── COORDINATE_SPEC.md          ← 본 문서 (양식 정의)
│   └── LIVE_CLIENT_API_FIELDS.md   ← API 필드 참조
├── poc/
│   ├── poc_riot_api.py             ← API 탐색용
│   ├── poc_core.py                 ← 통합 모듈 (폴링 + 위험도 + 저장)
│   ├── game_data_latest.json       ← 실시간 스냅샷 (런타임 생성)
│   └── game_data_*.json            ← 세션 기록 (런타임 생성)
```

---

## 9. LLM 프롬프트 초안

위험도 임계값을 초과했을 때 LLM에게 전달하는 프롬프트 구조. 좌표 데이터 + Live Client API 보조 데이터를 합쳐서 하나의 프롬프트로 구성한다.

### 9-1. 프롬프트 템플릿

```
너는 리그오브레전드 실시간 코칭 AI야. 아래 게임 상황 데이터를 보고 플레이어에게 1~2문장으로 즉각적인 조언을 해줘. TTS로 읽힐 텍스트이므로 간결하고 명확하게.

## 현재 상황
- 게임 시간: {game_time}초 ({minutes}분 {seconds}초)
- 내 챔피언: {my_champion}
- 내 체력: {my_hp_ratio * 100}%
- 위험도: {risk_score}/100 ({risk_level})

## 미니맵 좌표 (0~1 정규화, 좌상단 원점)
{minimap_positions_json}

## 적군 생사 정보 (Live Client API)
{enemy_status_json}

## 위험도 엔진 판정
- 근접 적: {nearby_enemies}
- 판정 근거: {reasons}

위 정보를 바탕으로 지금 플레이어가 해야 할 행동을 한국어로 1~2문장 조언해줘.
```

### 9-2. 실제 프롬프트 예시

```
너는 리그오브레전드 실시간 코칭 AI야. 아래 게임 상황 데이터를 보고 플레이어에게 1~2문장으로 즉각적인 조언을 해줘. TTS로 읽힐 텍스트이므로 간결하고 명확하게.

## 현재 상황
- 게임 시간: 843초 (14분 3초)
- 내 챔피언: Jinx
- 내 체력: 62%
- 위험도: 80/100 (HIGH)

## 미니맵 좌표 (0~1 정규화, 좌상단 원점)
[
  { "champion": "Jinx",   "x": 0.52, "y": 0.48, "team": "ally",  "confidence": 0.95 },
  { "champion": "Zed",    "x": 0.55, "y": 0.43, "team": "enemy", "confidence": 0.91 },
  { "champion": "Lux",    "x": 0.78, "y": 0.22, "team": "enemy", "confidence": 0.87 },
  { "champion": "Thresh", "x": 0.50, "y": 0.51, "team": "ally",  "confidence": 0.88 }
]

## 적군 생사 정보 (Live Client API)
[
  { "championName": "Zed",     "isDead": false, "respawnTimer": 0.0 },
  { "championName": "Lux",     "isDead": false, "respawnTimer": 0.0 },
  { "championName": "LeeSin",  "isDead": true,  "respawnTimer": 18.5 },
  { "championName": "Jinx",    "isDead": false, "respawnTimer": 0.0 },
  { "championName": "Nautilus","isDead": false, "respawnTimer": 0.0 }
]

## 위험도 엔진 판정
- 근접 적: Zed
- 판정 근거: Zed 매우 근접 (거리: 0.06)

위 정보를 바탕으로 지금 플레이어가 해야 할 행동을 한국어로 1~2문장 조언해줘.
```

### 9-3. 기대 LLM 응답 예시

> "제드가 바로 옆에 있어요! 체력이 62%밖에 안 되니 쓰레쉬 쪽으로 즉시 후퇴하세요."

---

## 10. 코멘트 및 추가 고려사항

### 10-1. 위험도 임계값 전환 (픽셀 → 비율)

기존 `risk_engine.py`의 픽셀 기반 임계값을 비율 기반으로 전환해야 한다. 미니맵 크기를 약 300px로 가정하면 대략적인 변환은 다음과 같다.

| 기존 (픽셀) | 변환 (비율) | 의미 |
|---|---|---|
| `DANGER_RADIUS_HIGH = 60px` | `≈ 0.20` | 매우 근접 — 즉시 교전 가능 거리 |
| `DANGER_RADIUS_MID = 120px` | `≈ 0.40` | 주의 구간 — 스킬 사거리 내 |

정확한 값은 실제 미니맵 bbox 크기 확정 후 조정 필요. 대각선 길이(√2 ≈ 1.414)도 고려해야 한다.

### 10-2. YOLO 탐지 못 하는 적 처리

미니맵에 표시되지 않는 적(안개 속에 있는 적)은 YOLO가 탐지할 수 없다. 이 경우 Live Client API의 `isDead` 정보와 결합해서 "죽지도 않았고 미니맵에도 안 보이는 적 = 잠재 위험"으로 처리하는 로직이 필요하다. 이 부분은 위험도 엔진 v2에서 반영 예정.

### 10-3. champion 이름 표기 통일

현재 YOLO 클래스명은 영문(예: `Jinx`), Live Client API는 `championName` 필드로 영문을 반환한다. 그러나 LLM 프롬프트에서 한국어 조언을 생성하므로, champion 이름은 **영문 원본을 유지**하되 LLM이 알아서 한국어로 번역하도록 맡긴다. 별도의 한영 매핑 테이블은 만들지 않는다.

### 10-4. LLM 호출 빈도 제어

위험도가 임계값을 넘을 때마다 LLM을 호출하면 API 비용이 과다해진다. 최소 호출 간격(쿨타임)을 두는 것이 필요하며, 이 값은 황기수님 `llm_caller.py`에서 관리한다. 권장 쿨타임: 10~15초.

### 10-5. 향후 확장 가능성

현재 양식은 챔피언 위치만 포함하지만, YOLO 클래스에 `ward`와 `objective`가 이미 정의되어 있다 (섹션 5 참조). Phase 2 이후 와드 시야 범위, 바론/드래곤 타이머 등을 좌표 데이터에 추가하면 LLM 조언의 품질이 크게 올라갈 것으로 예상한다.

---

## 11. 미결 사항 (팀 리뷰 필요)

- [ ] 챔피언 이름 표기 방식 통일 — YOLO 클래스명 vs Live Client `championName` (한글/영문)
- [ ] 레드팀 플레이 시 `ally`/`enemy` 방향 전환 로직 확정
- [ ] `confidence` 최소 임계값 확정 (현재 `poc/risk_engine.py` 기준 0.5)
- [ ] 와드/오브젝트 좌표 위험도 반영 여부 결정

---

> 변경 이력:
> - 2026-04-27 박창민 초안 작성
> - 2026-04-30 설계 근거(섹션 0), 파일 형태(섹션 8), LLM 프롬프트 초안(섹션 9), 코멘트(섹션 10) 추가
