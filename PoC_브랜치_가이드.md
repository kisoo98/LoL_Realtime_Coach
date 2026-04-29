# PoC 브랜치 가이드 — 팀원용

> 각자 역할별 PoC 코드를 GitHub에 올리는 방법입니다.  
> 순서대로 따라하면 됩니다.

---

## 1단계: 저장소 클론 (처음 하는 경우만)

```bash
git clone https://github.com/kisoo98/LoL_Realtime_Coach.git
cd LoL_Realtime_Coach
```

이미 클론했으면 최신 상태로 업데이트:

```bash
git checkout dev
git pull origin dev
```

---

## 2단계: 내 PoC 브랜치 생성

> **반드시 `dev` 기준으로 브랜치를 만드세요.**

### 한승우 (오버레이 UI)
```bash
git checkout dev
git checkout -b feature/poc-overlay
```

### 박창민 (Live Client API)
```bash
git checkout dev
git checkout -b feature/poc-riot-api
```

### 김대원 (데이터 수집)
```bash
git checkout dev
git checkout -b feature/poc-data
```

---

## 3단계: PoC 파일 작성

각자 역할에 맞게 파일을 만드세요.

| 이름 | 파일 | 위치 |
|------|------|------|
| 한승우 | `poc_overlay.py` | `poc/` 폴더 안 |
| 박창민 | `poc_riot_api.py`, `LIVE_CLIENT_API_FIELDS.md` | `poc/` 폴더 안 |
| 김대원 | 미니맵 샘플 + 라벨 파일 | `data/raw_minimap/`, `data/labels/` |

---

## 4단계: 파일 저장 (커밋 & Push)

파일 작성이 끝났으면 GitHub에 올립니다.

```bash
# 변경된 파일 전체 추가
git add .

# 커밋 (메시지는 아래 예시 참고)
git commit -m "feat: Live Client API PoC 구현"

# GitHub에 올리기
git push origin feature/poc-riot-api   # 본인 브랜치 이름으로
```

### 커밋 메시지 예시
- 한승우: `feat: PyQt6 오버레이 PoC 구현`
- 박창민: `feat: Live Client API PoC 구현`
- 김대원: `feat: 미니맵 샘플 데이터 및 라벨링 추가`

---

## 5단계: PR(Pull Request) 생성

1. [GitHub 저장소](https://github.com/kisoo98/LoL_Realtime_Coach) 접속
2. 상단에 뜨는 **"Compare & pull request"** 버튼 클릭
3. 아래처럼 설정 확인:
   ```
   base: dev  ←  compare: feature/poc-본인브랜치
   ```
4. PR 제목 작성 예시:
   - `[PoC] PyQt6 오버레이 구현`
   - `[PoC] Live Client API 연동`
   - `[PoC] 미니맵 샘플 데이터 수집`
5. **Create pull request** 클릭

---

## 6단계: 리뷰 & Merge

- 팀원 **1명 이상** 리뷰 후 Merge
- PR 페이지 맨 아래 **"Merge pull request"** 버튼 클릭
- Merge 완료 → `dev` 브랜치에 코드 합쳐짐 ✅

---

## 브랜치 정리

```
main
└── dev
    ├── feature/poc-overlay      ← 한승우
    ├── feature/poc-riot-api     ← 박창민
    ├── feature/poc-yolo         ← 황기수
    ├── feature/poc-llm          ← 황기수
    └── feature/poc-data         ← 김대원
```

---

## 자주 발생하는 오류

**브랜치가 이미 존재한다고 뜰 때:**
```bash
# -b 없이 이동만 하면 됩니다
git checkout feature/poc-riot-api
```

**push 명령어 오류:**
```bash
# push 앞에 git 붙이는 것 잊지 마세요
git push origin feature/poc-riot-api
```

**최신 dev 코드 반영이 안 됐을 때:**
```bash
git checkout dev
git pull origin dev
git checkout feature/poc-본인브랜치
git merge dev
```

---

> 문의: 황기수 (PM)
