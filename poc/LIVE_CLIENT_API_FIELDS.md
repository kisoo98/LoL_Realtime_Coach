# LoL Live Client Data API — 주요 필드 정리

> 담당: 박창민  
> 참고: https://developer.riotgames.com/docs/lol#league-client-update_live-client-data-api

---

## 엔드포인트 목록

| 엔드포인트 | URL | 설명 |
|---|---|---|
| All Game Data | `GET /liveclientdata/allgamedata` | 전체 데이터 한 번에 |
| Active Player | `GET /liveclientdata/activeplayer` | 본인 플레이어 정보 |
| Player List | `GET /liveclientdata/playerlist` | 전체 플레이어 목록 |
| Game Stats | `GET /liveclientdata/gamestats` | 게임 시간·맵 정보 |
| Event Data | `GET /liveclientdata/eventdata` | 킬·드래곤·바론 등 이벤트 |

- 기본 주소: `https://127.0.0.1:2999`
- 인증 불필요 (로컬 전용)
- SSL: 자체 서명 인증서 → `verify=False` 필요

---

## `/allgamedata` 전체 구조

```
allgamedata
├── activePlayer          # 본인 플레이어
├── allPlayers[]          # 전체 10명
├── events
│   └── Events[]          # 게임 이벤트 목록
└── gameData              # 게임 메타 정보
```

---

## `activePlayer` 필드

| 필드 | 타입 | 설명 |
|---|---|---|
| `summonerName` | string | 소환사 이름 |
| `championStats.currentHealth` | float | 현재 체력 |
| `championStats.maxHealth` | float | 최대 체력 |
| `championStats.resourceValue` | float | 현재 마나/에너지 |
| `championStats.resourceMax` | float | 최대 마나/에너지 |
| `championStats.attackDamage` | float | 공격력 |
| `championStats.abilityPower` | float | 주문력 |
| `championStats.moveSpeed` | float | 이동 속도 |
| `abilities` | object | Q/W/E/R/Passive 스킬 정보 |
| `fullRunes.generalRunes[]` | array | 룬 정보 |
| `level` | int | 현재 레벨 |
| `currentGold` | float | 현재 보유 골드 |

---

## `allPlayers[]` 필드 (플레이어 1명)

| 필드 | 타입 | 설명 |
|---|---|---|
| `summonerName` | string | 소환사 이름 |
| `championName` | string | 챔피언 이름 |
| `team` | string | `"ORDER"` (블루) / `"CHAOS"` (레드) |
| `position` | string | `"TOP"`, `"JUNGLE"`, `"MIDDLE"`, `"BOTTOM"`, `"UTILITY"` |
| `isBot` | bool | 봇 여부 |
| `isDead` | bool | 현재 사망 여부 |
| `respawnTimer` | float | 부활까지 남은 시간(초) |
| `scores.kills` | int | 킬 수 |
| `scores.deaths` | int | 데스 수 |
| `scores.assists` | int | 어시스트 수 |
| `scores.creepScore` | int | CS |
| `scores.wardScore` | float | 와드 점수 |
| `items[]` | array | 보유 아이템 목록 |
| `summonerSpells.summonerSpellOne/Two` | object | 소환사 주문 (이름, 쿨타임) |
| `runes.primaryRuneTree` | object | 주 룬 트리 |

---

## `events.Events[]` 필드

| 필드 | 타입 | 설명 |
|---|---|---|
| `EventID` | int | 이벤트 고유 ID |
| `EventName` | string | 이벤트 종류 (아래 목록 참고) |
| `EventTime` | float | 이벤트 발생 시각(초) |

### 주요 EventName 목록

| EventName | 설명 |
|---|---|
| `GameStart` | 게임 시작 |
| `MinionsSpawning` | 미니언 스폰 |
| `FirstBrick` | 첫 포탑 파괴 |
| `TurretKilled` | 포탑 파괴 (`TurretKilledBy` 필드 포함) |
| `InhibKilled` | 억제기 파괴 |
| `DragonKill` | 드래곤 처치 (`DragonType`: Infernal/Mountain/Cloud/Ocean/Hextech/Chemtech/Elder) |
| `BaronKill` | 바론 처치 |
| `HeraldKill` | 전령 처치 |
| `ChampionKill` | 챔피언 킬 (`KillerName`, `VictimName`, `Assisters[]`) |
| `Multikill` | 연속 킬 (`KillStreak` 필드 포함) |
| `Ace` | 전멸 |
| `GameEnd` | 게임 종료 (`Result`: `"Win"` / `"Lose"`) |

---

## `gameData` 필드

| 필드 | 타입 | 설명 |
|---|---|---|
| `gameTime` | float | 경과 시간(초) |
| `gameMode` | string | `"CLASSIC"`, `"ARAM"` 등 |
| `mapName` | string | 맵 이름 (`"Map11"` = 소환사 협곡) |
| `mapNumber` | int | 맵 번호 |
| `mapTerrain` | string | 현재 지형 (`"Default"`, `"Infernal"` 등 — 드래곤 지형 변화 반영) |

---

## 코칭 앱 활용 포인트

| 상황 | 사용할 필드 |
|---|---|
| 적 정글러 위치 파악 | `allPlayers[].isDead`, `allPlayers[].position`, `allPlayers[].team` |
| 위험도 산정 | 아군/적군 `isDead`, `respawnTimer`, `scores.kills` |
| 오브젝트 타이밍 알림 | `events.Events[].EventName` == `DragonKill` / `BaronKill` |
| 게임 시간 기반 경보 | `gameData.gameTime` |
| 소환사 주문 쿨 추적 | `summonerSpells` (이름으로 쿨타임 계산 필요) |

---

> 마지막 업데이트: 2026-04-27  
> 문의: 박창민
