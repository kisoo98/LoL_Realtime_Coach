# Riot API 데이터 정리
> 작성자: 박창민 | 기준일: 2026-04-24 | 프로젝트: LoL 실시간 AI 코칭

---

## API 종류 개요

Riot API는 크게 두 종류로 나뉜다.

| 종류 | 주소 | API 키 | 사용 시점 |
|---|---|---|---|
| **Live Client API** | `127.0.0.1:2999` | 불필요 | 게임 진행 중에만 |
| **Riot 공식 API** | `kr.api.riotgames.com` | 필요 | 게임 밖에서도 |

---

## 1. Live Client API (창민님 담당 — 이미 구현 완료)

> 게임이 실행 중일 때만 로컬에서 호출 가능. API 키 불필요.  
> 기본 주소: `https://127.0.0.1:2999/liveclientdata`

### 엔드포인트 목록

#### 내 플레이어 정보 (Active Player)

| 엔드포인트 | 설명 | 주요 필드 |
|---|---|---|
| `GET /activeplayer` | 내 전체 스탯 | `championStats`, `currentGold`, `level` |
| `GET /activeplayername` | 내 소환사명 | `"창민GG#KR1"` |
| `GET /activeplayerabilities` | 내 스킬 레벨 | `Q/W/E/R.abilityLevel` |
| `GET /activeplayerrunes` | 내 룬 | `keystone`, `primaryRuneTree`, `secondaryRuneTree` |

**championStats 세부 필드:**
```
currentHealth       현재 체력
maxHealth           최대 체력
resourceValue       현재 마나/에너지
resourceMax         최대 마나/에너지
resourceType        자원 유형 (MANA / ENERGY)
attackDamage        공격력
attackSpeed         공격 속도
moveSpeed           이동 속도
armor               방어력
magicResist         마법 저항력
critChance          치명타 확률 (0.5 = 50%)
abilityHaste        스킬 가속
lifeSteal           흡혈
tenacity            강인함
```

---

#### 전체 플레이어 정보 (All Players)

| 엔드포인트 | 설명 | 주요 필드 |
|---|---|---|
| `GET /playerlist` | 전체 10명 목록 | `championName`, `team`, `isDead`, `items`, `scores` |
| `GET /playerscores?riotId=` | 특정 플레이어 점수 | `kills`, `deaths`, `assists`, `creepScore` |
| `GET /playeritems?riotId=` | 특정 플레이어 아이템 | `displayName`, `itemID`, `slot` |
| `GET /playersummonerspells?riotId=` | 소환사 주문 | `summonerSpellOne`, `summonerSpellTwo` |
| `GET /playermainrunes?riotId=` | 기본 룬 | `keystone`, `primaryRuneTree` |

**playerlist 세부 필드:**
```
championName        챔피언 이름
team                팀 구분 (ORDER=아군 / CHAOS=적군)
position            라인 포지션 (TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY/NONE)
level               챔피언 레벨
isDead              사망 여부 (true/false)
respawnTimer        부활까지 남은 시간 (초)
isBot               AI봇 여부
scores.kills        킬
scores.deaths       데스
scores.assists      어시스트
scores.creepScore   CS (미니언 처치 수)
scores.wardScore    와드 점수
items[]             보유 아이템 목록
summonerSpells      소환사 주문 2개
```

> ⚠️ **위치 좌표(x, y) 없음** — 챔피언 맵 좌표는 Live Client API에서 제공하지 않음.  
> 미니맵 위치 파악은 **YOLO 모델(황기수)** 담당.

---

#### 게임 이벤트 (Events)

| 엔드포인트 | 설명 |
|---|---|
| `GET /eventdata` | 게임 내 발생한 전체 이벤트 목록 |

**주요 EventName 목록:**
```
GameStart           게임 시작
ChampionKill        챔피언 처치 (KillerName, VictimName, Assisters)
Multikill           더블킬 이상 (KillStreak)
FirstBlood          퍼스트 블러드
TurretKilled        포탑 파괴 (TurretKilled, KillerName)
FirstBrick          첫 포탑 파괴
DragonKill          드래곤 처치 (DragonType)
BaronKill           바론 처치
HordeKill           공허 유충 처치
HeraldKill          전령 처치
GameEnd             게임 종료 (Result: Win/Lose)
```

---

#### 게임 메타 (Game Stats)

| 엔드포인트 | 설명 | 주요 필드 |
|---|---|---|
| `GET /gamestats` | 게임 기본 정보 | `gameTime`, `gameMode`, `mapName` |
| `GET /allgamedata` | 위 전체 데이터 한 번에 | 전부 포함 |

```
gameTime        게임 경과 시간 (초) — 예: 342.5
gameMode        게임 모드 (CLASSIC / PRACTICETOOL / ARAM)
mapName         맵 이름 (Map11 = 소환사 협곡)
mapNumber       맵 번호 (11)
mapTerrain      지형 타입 (Default)
```

---

## 2. Riot 공식 API (W2 이후 — 김대원 + 창민 협업)

> API 키 필요. `.env` 파일에 저장.  
> 한국 서버: `https://kr.api.riotgames.com`  
> 광역 서버: `https://asia.api.riotgames.com`

### 이 프로젝트에서 쓸 API

| API | 엔드포인트 | 받는 데이터 | 담당 | 활용 |
|---|---|---|---|---|
| `account-v1` | `/riot/account/v1/accounts/by-riot-id/{name}/{tag}` | PUUID | 창민 | 플레이어 식별 |
| `summoner-v4` | `/lol/summoner/v4/summoners/by-puuid/{puuid}` | summonerID, 레벨 | 창민 | 기본 정보 |
| `league-v4` | `/lol/league/v4/entries/by-summoner/{summonerID}` | 티어, 랭크, 승률, LP | 창민 | 위험도 보정 보조 |
| `match-v5` | `/lol/match/v5/matches/by-puuid/{puuid}/ids` | 최근 경기 ID 목록 | 김대원 | 승률 그래프 |
| `match-v5` | `/lol/match/v5/matches/{matchId}` | 경기 상세 (KDA, 챔피언, 아이템) | 김대원 | 승률 그래프 |
| `spectator-v5` | `/lol/spectator/v5/active-games/by-summoner/{summonerID}` | 현재 게임 픽/밴 정보 | 창민 | 조합 분석 |

### 주요 응답 필드

#### league-v4 (티어/랭크)
```
queueType       RANKED_SOLO_5x5 / RANKED_FLEX_SR
tier            IRON / BRONZE / SILVER / GOLD / PLATINUM / EMERALD / DIAMOND / MASTER / ...
rank            I / II / III / IV
leaguePoints    LP
wins            승리 수
losses          패배 수
```

#### match-v5 (경기 상세)
```
info.gameDuration       게임 시간 (초)
info.gameMode           게임 모드
info.participants[]     10명 참가자 정보
  └ championName        챔피언 이름
  └ teamId              팀 (100=아군 / 200=적군)
  └ kills / deaths / assists
  └ totalMinionsKilled  CS
  └ items               아이템 ID (0~6번 슬롯)
  └ win                 승리 여부
  └ role / lane         포지션
```

---

## 3. 이 프로젝트에서 쓰지 않는 것 (정책 위반 또는 불필요)

| 항목 | 이유 |
|---|---|
| 클라이언트 역설계 (LCU API) | Riot 정책 위반 — 비공식 API |
| 적 궁 쿨타임 자동 추적 | 게임 무결성 정책 위반 |
| 외부 서버로 게임 데이터 전송 | 보안 정책 위반 |
| champion-mastery, 경기 후 피드백 | MVP 범위 외 (확장 목표) |

---

## 4. Rate Limit 주의사항

| 키 종류 | 제한 |
|---|---|
| 개발 키 (Development) | 20 req/1초, 100 req/2분, **24시간마다 만료** |
| 개인 키 (Personal) | 승인 후 제한 완화 |

> ⚠️ **개발 키는 매일 재발급 필요!**  
> `developer.riotgames.com` → Dashboard → Generate API Key

---

## 5. 한국 서버 라우팅

```python
# 플랫폼 (summoner, league, spectator API)
KR_PLATFORM = "https://kr.api.riotgames.com"

# 광역 (account, match API)
ASIA_REGION = "https://asia.api.riotgames.com"

# 헤더
headers = {"X-Riot-Token": os.getenv("RIOT_API_KEY")}
```

---

## 변경 이력

| 날짜 | 내용 |
|---|---|
| 2026-04-24 | v1.0 최초 작성 (박창민) |
