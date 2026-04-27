# LIVE_CLIENT_API_FIELDS.md
# Live Client Data API — 응답 필드 정리

> **기준 엔드포인트:** `GET https://127.0.0.1:2999/liveclientdata/allgamedata`  
> **작성자:** 박창민  
> **작성일:** 2026-04-23  
> **참고:** API 키 불필요 (로컬 전용, 게임 실행 중에만 응답)

---

## 최상위 구조

```
allgamedata
├── activePlayer     # 나(현재 플레이어) 상세 정보
├── allPlayers       # 전체 10명 플레이어 목록
├── events           # 게임 내 발생 이벤트 목록
└── gameData         # 게임 메타 정보
```

---

## 1. `activePlayer` — 내 캐릭터 상세

| 필드 | 타입 | 설명 | 예시 |
|---|---|---|---|
| `summonerName` | string | 내 소환사명 | `"챙 렬#KR1"` |
| `riotIdGameName` | string | Riot ID 이름 | `"챙 렬"` |
| `level` | int | 현재 레벨 | `16` |
| `currentGold` | float | 현재 보유 골드 | `7525.5` |
| `abilities.Q/W/E/R` | object | 스킬 레벨 및 이름 | `abilityLevel: 5` |
| `championStats.currentHealth` | float | 현재 체력 | `2408.5` |
| `championStats.maxHealth` | float | 최대 체력 | `2408.5` |
| `championStats.resourceValue` | float | 현재 마나/에너지 | `1067.4` |
| `championStats.resourceMax` | float | 최대 마나/에너지 | `1067.4` |
| `championStats.resourceType` | string | 자원 유형 | `"MANA"` |
| `championStats.attackDamage` | float | 공격력 | `226.9` |
| `championStats.attackSpeed` | float | 공격 속도 | `1.38` |
| `championStats.moveSpeed` | float | 이동 속도 | `799.8` |
| `championStats.armor` | float | 방어력 | `88.8` |
| `championStats.magicResist` | float | 마법 저항력 | `48.8` |
| `championStats.critChance` | float | 치명타 확률 | `0.5` (= 50%) |

> ⚠️ **위치 좌표 없음** — `activePlayer`에 x, y 좌표 필드가 존재하지 않음.  
> 미니맵 위치 파악은 **YOLO 모델(황기수)** 담당.

---

## 2. `allPlayers[]` — 전체 10명 플레이어

| 필드 | 타입 | 설명 | 예시 |
|---|---|---|---|
| `summonerName` | string | 소환사명 | `"챙 렬#KR1"` |
| `championName` | string | 챔피언 이름 (한글) | `"루시안"` |
| `rawChampionName` | string | 내부 챔피언 ID | `"game_character_displayname_Lucian"` |
| `team` | string | 팀 구분 | `"ORDER"` / `"CHAOS"` |
| `position` | string | 라인 포지션 | `"BOTTOM"` / `"NONE"` |
| `level` | int | 챔피언 레벨 | `16` |
| `isDead` | bool | 사망 여부 | `false` |
| `respawnTimer` | float | 부활까지 남은 시간(초) | `0.0` |
| `isBot` | bool | AI봇 여부 | `false` |
| `scores.kills` | int | 킬 수 | `12` |
| `scores.deaths` | int | 데스 수 | `0` |
| `scores.assists` | int | 어시스트 수 | `2` |
| `scores.creepScore` | int | CS (미니언 처치) | `10` |
| `scores.wardScore` | float | 와드 점수 | `0.0` |
| `items[]` | array | 보유 아이템 목록 | 아래 참고 |
| `summonerSpells` | object | 소환사 주문 | `"점멸"`, `"강력 순간이동"` |
| `skinID` | int | 스킨 ID | `6` |

### 2-1. `items[]` — 아이템 상세

| 필드 | 타입 | 설명 |
|---|---|---|
| `displayName` | string | 아이템 표시 이름 |
| `itemID` | int | 아이템 고유 ID |
| `slot` | int | 인벤토리 슬롯 (0~6) |
| `canUse` | bool | 능동 사용 가능 여부 |
| `consumable` | bool | 소모품 여부 |
| `count` | int | 수량 |
| `price` | int | 판매가 (골드) |

---

## 3. `events.Events[]` — 게임 이벤트

| 필드 | 타입 | 설명 | 예시 |
|---|---|---|---|
| `EventID` | int | 이벤트 순번 | `54` |
| `EventName` | string | 이벤트 종류 | 아래 목록 참고 |
| `EventTime` | float | 발생 시간(초) | `1252.9` |
| `KillerName` | string | 킬/파괴 주체 | `"챙 렬"` |
| `VictimName` | string | 사망자 (ChampionKill) | `"케일 봇"` |
| `Assisters[]` | array | 어시스트 플레이어 목록 | `["모르가나 봇"]` |
| `TurretKilled` | string | 파괴된 포탑 ID (TurretKilled) | `"Turret_TOrder_..."` |
| `KillStreak` | int | 연속킬 수 (Multikill) | `2` |

### 주요 EventName 목록

| EventName | 설명 |
|---|---|
| `GameStart` | 게임 시작 |
| `ChampionKill` | 챔피언 처치 |
| `Multikill` | 더블킬 이상 |
| `FirstBlood` | 퍼스트 블러드 |
| `TurretKilled` | 포탑 파괴 |
| `FirstBrick` | 첫 포탑 파괴 |
| `DragonKill` | 드래곤 처치 |
| `BaronKill` | 바론 처치 |

> 💡 **위험도 엔진 활용 포인트**  
> `ChampionKill`의 `VictimName`이 내 소환사명이면 → 방금 죽었음을 감지 가능  
> `respawnTimer > 0` 이면 → 현재 사망 중

---

## 4. `gameData` — 게임 메타

| 필드 | 타입 | 설명 | 예시 |
|---|---|---|---|
| `gameTime` | float | 게임 경과 시간(초) | `1290.7` |
| `gameMode` | string | 게임 모드 | `"PRACTICETOOL"` / `"CLASSIC"` |
| `mapName` | string | 맵 이름 | `"Map11"` (소환사 협곡) |
| `mapNumber` | int | 맵 번호 | `11` |
| `mapTerrain` | string | 지형 타입 | `"Default"` |

---

## 5. 위험도 엔진 활용 필드 요약

> `risk_engine.py`에서 실제로 쓰는 필드만 추린 것

```python
# Live Client API에서 뽑아 쓰는 것
game_time    = data["gameData"]["gameTime"]          # 게임 시간
my_name      = data["activePlayer"]["summonerName"]  # 내 이름 (팀 구분용)
my_hp_ratio  = (
    data["activePlayer"]["championStats"]["currentHealth"] /
    data["activePlayer"]["championStats"]["maxHealth"]
)  # 내 체력 비율 (보조 위험도 판단 가능)

for p in data["allPlayers"]:
    p["team"]          # "ORDER" / "CHAOS" → 아군/적군 구분
    p["isDead"]        # 사망 여부
    p["respawnTimer"]  # 부활 대기 시간

# ⚠️ 위치(x, y) 좌표는 없음 → YOLO(황기수) 담당
```

---

## 6. 기타 참고

- **pollingInterval 권장:** 0.5초 ~ 1초 (너무 빠르면 CPU 부담)
- **게임 미실행 시:** `ConnectionError` 발생 → `try/except`로 처리
- **SSL 경고:** `verify=False` + `urllib3.disable_warnings()`로 억제
- **연습 모드:** `gameMode = "PRACTICETOOL"`, 실제 게임은 `"CLASSIC"`
