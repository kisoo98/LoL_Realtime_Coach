import sys
import time
import os
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QScreen

# 음성 출력을 위한 라이브러리
from gtts import gTTS
import pygame

import live_game

# ----------------------------------------------------
# 1. 음성 출력 전용 스레드 (API나 UI가 멈추지 않도록 비동기 처리)
# ----------------------------------------------------
class VoiceThread(QThread):
    def __init__(self):
        super().__init__()
        self.queue = []
        pygame.mixer.init()
        self.running = True

    def speak(self, text):
        """외부에서 음성으로 읽을 텍스트를 큐에 넣습니다."""
        self.queue.append(text)

    def run(self):
        while self.running:
            if self.queue:
                text = self.queue.pop(0)
                try:
                    # 구글 TTS에 요청하여 mp3 생성
                    tts = gTTS(text=text, lang='ko')
                    filename = "temp_voice.mp3"
                    tts.save(filename)
                    
                    # pygame을 이용해 mp3 재생
                    pygame.mixer.music.load(filename)
                    pygame.mixer.music.play()
                    
                    # 재생이 끝날 때까지 대기
                    while pygame.mixer.music.get_busy() and self.running:
                        time.sleep(0.1)
                        
                    # 파일 잠금 해제 (다음 음성이 덮어쓸 수 있도록)
                    pygame.mixer.music.unload()
                except Exception as e:
                    print(f"TTS 재생 오류: {e}")
            time.sleep(0.1)

    def stop(self):
        self.running = False
        self.wait()


# ----------------------------------------------------
# 2. 2025 시즌 기준 오브젝트 타이머 상수
# ----------------------------------------------------
DRAGON_FIRST_SPAWN = 300       # 5:00 첫 용 등장
DRAGON_RESPAWN = 300           # 5분 간격 리스폰
VOID_GRUBS_SPAWN = 480         # 8:00 공허 유충 등장
RIFT_HERALD_SPAWN = 900        # 15:00 전령 등장
BARON_SPAWN = 1200             # 20:00 바론 등장
TOWER_PLATE_FALL = 840         # 14:00 타워 방패 소멸

# ----------------------------------------------------
# 3. 실시간 정보 폴링 스레드
# ----------------------------------------------------
class LiveAPIThread(QThread):
    update_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.running = True
        self.last_event_count = 0
        
        # 중복 안내 방지용 이전 텍스트 저장
        self.last_coaching_tip = ""
        self.last_event_tip = ""
        
        # 오브젝트 타이머 알림 플래그 (한 번만 울림)
        self.alerted = {
            "dragon_30s": False,    # 용 등장 30초 전
            "dragon_spawn": False,  # 용 등장 시점
            "grubs_30s": False,     # 공허 유충 30초 전
            "grubs_spawn": False,   # 공허 유충 등장
            "herald_30s": False,    # 전령 30초 전
            "herald_spawn": False,  # 전령 등장
            "baron_60s": False,     # 바론 1분 전
            "baron_spawn": False,   # 바론 등장
            "plate_60s": False,     # 방패 소멸 1분 전
            "plate_fall": False,    # 방패 소멸
        }
        
        # 용/바론 처치 후 리스폰 타이머
        self.next_dragon_time = DRAGON_FIRST_SPAWN
        self.dragon_respawn_alerted = False
        self.next_baron_time = BARON_SPAWN
        self.baron_respawn_alerted = False

    def _check_objective_timers(self, game_time):
        """오브젝트 등장 시간 기반 코칭 팁을 반환합니다."""
        tip = ""
        
        # --- 용 타이머 ---
        if not self.alerted["dragon_30s"] and self.next_dragon_time - 30 <= game_time < self.next_dragon_time:
            self.alerted["dragon_30s"] = True
            secs_left = int(self.next_dragon_time - game_time)
            tip = f"🐉 약 {secs_left}초 후 드래곤이 등장합니다! 봇 라인 시야를 확보하세요."
        elif not self.alerted["dragon_spawn"] and game_time >= self.next_dragon_time:
            self.alerted["dragon_spawn"] = True
            tip = "🐉 드래곤이 등장했습니다! 팀과 함께 용 싸움을 준비하세요."
        
        # --- 공허 유충 타이머 ---
        elif not self.alerted["grubs_30s"] and VOID_GRUBS_SPAWN - 30 <= game_time < VOID_GRUBS_SPAWN:
            self.alerted["grubs_30s"] = True
            tip = "🪱 30초 후 공허 유충이 등장합니다. 탑 사이드 시야를 확보하세요."
        elif not self.alerted["grubs_spawn"] and game_time >= VOID_GRUBS_SPAWN and not self.alerted["grubs_spawn"]:
            self.alerted["grubs_spawn"] = True
            tip = "🪱 공허 유충이 등장했습니다! 유충을 빠르게 처리하면 타워 압박에 유리합니다."
        
        # --- 전령 타이머 ---
        elif not self.alerted["herald_30s"] and RIFT_HERALD_SPAWN - 30 <= game_time < RIFT_HERALD_SPAWN:
            self.alerted["herald_30s"] = True
            tip = "👁 30초 후 협곡의 전령이 등장합니다. 미리 탑 사이드 시야를 확보하세요."
        elif not self.alerted["herald_spawn"] and game_time >= RIFT_HERALD_SPAWN and not self.alerted["herald_spawn"]:
            self.alerted["herald_spawn"] = True
            tip = "👁 전령이 등장했습니다! 전령을 잡아서 포탑을 밀 수 있습니다."
        
        # --- 바론 타이머 ---
        elif not self.alerted["baron_60s"] and self.next_baron_time - 60 <= game_time < self.next_baron_time:
            self.alerted["baron_60s"] = True
            tip = "🟣 1분 후 바론이 등장합니다! 바론 주변 시야를 장악하세요."
        elif not self.alerted["baron_spawn"] and game_time >= self.next_baron_time and not self.alerted["baron_spawn"]:
            self.alerted["baron_spawn"] = True
            tip = "🟣 바론 내셔가 등장했습니다! 팀 합류 후 바론을 노려보세요."
        
        # --- 타워 방패 소멸 ---
        elif not self.alerted["plate_60s"] and TOWER_PLATE_FALL - 60 <= game_time < TOWER_PLATE_FALL:
            self.alerted["plate_60s"] = True
            tip = "⏰ 1분 후 타워 방패가 소멸됩니다! 남은 방패골드를 수거하세요."
        elif not self.alerted["plate_fall"] and game_time >= TOWER_PLATE_FALL and not self.alerted["plate_fall"]:
            self.alerted["plate_fall"] = True
            tip = "⏰ 타워 방패가 소멸되었습니다. 이제 로밍과 오브젝트에 집중하세요."
        
        return tip

    def _handle_event(self, event, my_name, game_time):
        """개별 이벤트를 분석하여 코칭 메시지를 반환합니다."""
        evt_type = event.get("EventName")
        tip = ""
        
        if evt_type == "ChampionKill":
            killer = event.get("KillerName", "")
            victim = event.get("VictimName", "")
            assisters = event.get("Assisters", [])
            
            if killer == my_name:
                tip = "🔥 나이스 킬! 라인을 밀어넣고 귀환 또는 오브젝트를 노리세요."
            elif victim == my_name:
                tip = "💀 데스 발생. 부활 전 미니맵을 보고 팀원에게 적 스펠 정보를 공유하세요."
            elif my_name in assisters:
                tip = f"🤝 어시스트! {killer} 님의 킬에 기여했습니다. 좋은 협동이에요."
            else:
                tip = f"⚔️ 교전 발생! {killer} 님이 {victim} 님을 처치했습니다."
        
        elif evt_type == "Multikill":
            killer = event.get("KillerName", "")
            kill_streak = event.get("KillStreak", 0)
            streak_names = {2: "더블킬", 3: "트리플킬", 4: "쿼드라킬", 5: "펜타킬"}
            streak_text = streak_names.get(kill_streak, f"{kill_streak}연속 킬")
            if killer == my_name:
                tip = f"🔥 {streak_text}! 이 기세를 몰아 오브젝트를 챙기세요!"
            else:
                tip = f"⚔️ {killer} 님이 {streak_text}을 달성했습니다!"
                
        elif evt_type == "DragonKill":
            killer = event.get("KillerName", "")
            dragon_type = event.get("DragonType", "")
            dragon_names = {
                "Fire": "화염", "Earth": "대지", "Water": "바다",
                "Air": "바람", "Hextech": "마법공학", "Chemtech": "화학공학",
                "Elder": "장로"
            }
            dname = dragon_names.get(dragon_type, dragon_type)
            tip = f"🐉 {dname} 용 처치! 다음 용은 약 5분 후 리스폰됩니다."
            # 리스폰 타이머 갱신
            self.next_dragon_time = game_time + DRAGON_RESPAWN
            self.alerted["dragon_30s"] = False
            self.alerted["dragon_spawn"] = False
                
        elif evt_type == "BaronKill":
            killer = event.get("KillerName", "")
            tip = "🟣 바론 처치! 바론 버프로 라인을 밀고 이니시를 잡으세요."
            self.next_baron_time = game_time + 360  # 바론 리스폰 6분
            self.alerted["baron_60s"] = False
            self.alerted["baron_spawn"] = False
        
        elif evt_type == "HeraldKill":
            tip = "👁 전령 처치! 전령을 소환해서 포탑을 밀어보세요."
        
        elif evt_type == "TurretKilled":
            turret_id = event.get("TurretKilled", "")
            killer = event.get("KillerName", "")
            # 포탑 ID에서 라인 판별
            if "Mid" in turret_id or "C_" in turret_id:
                tip = "🏰 미드 포탑 파괴! 미드 라인이 열렸습니다. 시야를 넓히고 사이드 라인 로밍 또는 정글 침입을 시도하세요."
            elif "Bot" in turret_id or "R_" in turret_id:
                tip = "🏰 봇 포탑 파괴! 봇 듀오는 미드로 로테이션하여 용 싸움 주도권을 잡으세요."
            elif "Top" in turret_id or "L_" in turret_id:
                tip = "🏰 탑 포탑 파괴! 전령/바론 라인 압박이 수월해졌습니다."
            else:
                tip = "🏰 포탑이 파괴되었습니다! 열린 라인을 활용해 시야를 확보하세요."
        
        elif evt_type == "InhibKilled":
            tip = "🏰 억제기 파괴! 슈퍼 미니언 압박을 활용해 바론이나 용을 노리세요."
        
        elif evt_type == "FirstBlood":
            tip = "🩸 퍼스트 블러드! 초반 이득을 라인 주도권으로 전환하세요."
        
        return tip

    def run(self):
        while self.running:
            try:
                data = live_game.get_all_game_data()
                if not data:
                    self.update_signal.emit({"status": "waiting", "msg": "롤 게임 진입 및 로딩 대기 중..."})
                    time.sleep(2)
                    continue

                active_player = data.get("activePlayer", {})
                events = data.get("events", {}).get("Events", [])
                stats = data.get("gameData", {})
                
                champ_stats = active_player.get("championStats", {})
                max_health = champ_stats.get("maxHealth", 1)
                curr_health = champ_stats.get("currentHealth", 1)
                health_pct = (curr_health / max_health) * 100 if max_health > 0 else 100
                
                current_gold = active_player.get("currentGold", 0)
                game_time = stats.get("gameTime", 0)
                my_name = active_player.get("summonerName", "")
                my_level = active_player.get("level", 1)
                
                # --- 1. 오브젝트 타이머 기반 코칭 (최우선) ---
                objective_tip = self._check_objective_timers(game_time)
                
                # --- 2. 상태 기반 AI 코칭 팁 ---
                coaching_tip = ""
                if objective_tip:
                    coaching_tip = objective_tip
                elif health_pct <= 20 and curr_health > 0:
                    coaching_tip = "🛑 체력이 20% 이하로 위험합니다! 무리하지 말고 귀환을 고려하세요."
                elif current_gold >= 2000:
                    coaching_tip = f"💰 {int(current_gold)} 골드 보유! 즉시 귀환하여 핵심 아이템을 완성하세요."
                elif current_gold >= 1300 and game_time < 600:
                    coaching_tip = f"💡 {int(current_gold)} 골드로 초반 핵심 하위템을 구매하세요."
                elif game_time < 90:
                    coaching_tip = "🔍 게임 시작! 적 정글 시작 위치를 파악하고 시야를 확보하세요."
                elif 1800 < game_time < 2400:
                    coaching_tip = "⚔️ 후반 진입! 혼자 다니지 말고 팀과 함께 움직이세요."
                elif game_time >= 2400:
                    coaching_tip = "🛡 초후반입니다. 한 번의 데스가 게임을 결정합니다. 신중하게!"

                # --- 3. 실시간 타임라인 이벤트 판별 ---
                event_tip = ""
                if len(events) > self.last_event_count:
                    for evt in events[self.last_event_count:]:
                        result = self._handle_event(evt, my_name, game_time)
                        if result:
                            event_tip = result  # 마지막 의미있는 이벤트 사용
                    self.last_event_count = len(events)

                # --- TTS 및 화면 알림 분리 ---
                speeches = []
                new_coaching_tip = None
                emoji_chars = "🛑💰💡⏰🐉🪱👁🟣🔍⚔️🛡"
                
                if coaching_tip and coaching_tip != self.last_coaching_tip:
                    self.last_coaching_tip = coaching_tip
                    new_coaching_tip = coaching_tip
                    clean = coaching_tip
                    for ch in emoji_chars:
                        clean = clean.replace(ch, "")
                    speeches.append(clean.strip())

                new_event_tip = None
                event_emoji = "🔥💀⚔️🐉🏰🤝🩸"
                if event_tip and event_tip != self.last_event_tip:
                    self.last_event_tip = event_tip
                    new_event_tip = event_tip
                    clean = event_tip
                    for ch in event_emoji:
                        clean = clean.replace(ch, "")
                    speeches.append(clean.strip())

                packet = {
                    "status": "ingame",
                    "new_coaching_tip": new_coaching_tip,
                    "event_tip": new_event_tip,
                    "speeches": speeches
                }
                
                self.update_signal.emit(packet)

            except Exception as e:
                pass
                
            time.sleep(1)

    def stop(self):
        self.running = False
        self.wait()


# ----------------------------------------------------
# 3. 메인 오버레이 렌더러
# ----------------------------------------------------
class CoachingOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.status = "waiting"
        self.msg = "롤 게임 실행 대기 중..."
        
        self.current_coaching_tip = ""
        self.coaching_timer = 0
        
        self.current_event_tip = ""
        self.event_timer = 0
        
        self.initUI()
        
        # 음성 TTS 스레드 부팅
        self.voice_thread = VoiceThread()
        self.voice_thread.start()
        
        # API 모니터링 스레드 부팅
        self.thread = LiveAPIThread()
        self.thread.update_signal.connect(self.update_data)
        self.thread.start()

    def initUI(self):
        # 실제 주 모니터의 해상도를 동적으로 가져옴 (하드코딩 제거)
        screen: QScreen = QApplication.primaryScreen()
        geo = screen.geometry()
        self.screen_w = geo.width()
        self.screen_h = geo.height()
        
        self.setGeometry(geo)
        self.setWindowTitle('League of Legends AI Coach (PyQt6)')
        
        # Tool: 테두리없음/풀스크린 게임 위에서 안정적으로 동작하는 플래그
        # ToolTip 대신 Tool을 쓰면 DirectX/게임 전체화면과의 충돌이 줄어듦
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowTransparentForInput |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # showFullScreen() 대신 show()를 사용 — 게임 전체화면과 z-order 충돌 방지
        self.show()

    def update_data(self, data):
        self.status = data.get("status")
        if self.status == "waiting":
            self.msg = data.get("msg")
        else:
            # 음성으로 내보낼 항목이 있다면 VoiceThread 큐에 추가
            speeches = data.get("speeches", [])
            for text in speeches:
                self.voice_thread.speak(text)
                
            # 코칭 알림 로직 (10초 유지, 단 경고는 조건 해제 시까지 지속)
            new_coach = data.get("new_coaching_tip")
            if new_coach:
                self.current_coaching_tip = new_coach
                self.coaching_timer = 10 
            
            # 위험 상태(경고)일 경우 타이머를 고정시켜 메시지가 사라지지 않게 합니다.
            if self.current_coaching_tip and "🛑" in self.current_coaching_tip:
                self.coaching_timer = 10
            
            if self.coaching_timer > 0:
                self.coaching_timer -= 1
            else:
                self.current_coaching_tip = ""
            
            # 이벤트 알림 로직 (10초 유지)
            new_evt = data.get("event_tip")
            if new_evt:
                self.current_event_tip = new_evt
                self.event_timer = 10 
            
            if self.event_timer > 0:
                self.event_timer -= 1
            else:
                self.current_event_tip = ""
                
        self.raise_()
        self.repaint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        text_pen = QPen(QColor(255, 255, 255))

        # ─── 공통 레이아웃 상수 (해상도 독립) ───────────────────────────
        margin_right = 20
        banner_w = 300           # 레퍼런스 이미지 기준 배너 너비
        banner_h = 70            # 배너 높이
        icon_area = 56           # 좌측 아이콘 영역 너비

        # 우측 고정 x 좌표
        x_pos = self.screen_w - banner_w - margin_right

        # ─── 대기 상태 ───────────────────────────────────────────────────
        if self.status == "waiting":
            box_w, box_h = 340, 60
            box_x = (self.screen_w - box_w) // 2
            painter.setBrush(QBrush(QColor(30, 30, 40, 220)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(box_x, 50, box_w, box_h, 12, 12)
            painter.setPen(text_pen)
            painter.setFont(QFont("Malgun Gothic", 12, QFont.Weight.Bold))
            painter.drawText(box_x, 50, box_w, box_h,
                             Qt.AlignmentFlag.AlignCenter,
                             self.msg)
            painter.end()
            return

        # ─── 인게임 상태 ─────────────────────────────────────────────────
        # 레퍼런스 이미지: 배너가 미니맵 바로 위, 화면 세로 약 55% 지점에 위치
        # 해상도 독립적으로 screen_h 비율로 계산
        lower_anchor_y = int(self.screen_h * 0.55)  # 미니맵 위 경고/이벤트 배너 y

        # ── 헬퍼: 레퍼런스 스타일 배너 그리기 ──────────────────────────
        def draw_banner(y, bg_color, icon_color, icon_char, message, font_size=11):
            """레퍼런스 이미지 스타일의 좌측 아이콘 + 텍스트 배너를 그립니다."""
            # 배경
            painter.setBrush(QBrush(bg_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(x_pos, y, banner_w, banner_h, 12, 12)

            # 좌측 아이콘 영역 (더 진한 색으로 구분)
            icon_bg = QColor(bg_color)
            icon_bg.setAlpha(255)
            icon_bg = icon_bg.darker(130)
            painter.setBrush(QBrush(icon_bg))
            painter.drawRoundedRect(x_pos, y, icon_area, banner_h, 12, 12)
            # 아이콘 영역 오른쪽 모서리는 직각으로 처리
            painter.drawRect(x_pos + icon_area - 12, y, 12, banner_h)

            # 아이콘 텍스트 (삼각형 경고 기호 등)
            painter.setPen(QPen(icon_color))
            painter.setFont(QFont("Malgun Gothic", 20, QFont.Weight.Bold))
            painter.drawText(x_pos, y, icon_area, banner_h,
                             Qt.AlignmentFlag.AlignCenter, icon_char)

            # 메시지 텍스트
            painter.setPen(text_pen)
            painter.setFont(QFont("Malgun Gothic", font_size, QFont.Weight.Bold))
            flags = (int(Qt.AlignmentFlag.AlignVCenter) |
                     int(Qt.AlignmentFlag.AlignLeft) |
                     int(Qt.TextFlag.TextWordWrap))
            painter.drawText(x_pos + icon_area + 8, y,
                             banner_w - icon_area - 14, banner_h,
                             flags, message)

        # ── 1. 우측 상단 일반 코칭 팁 (작은 배너) ───────────────────────
        if self.current_coaching_tip and "🛑" not in self.current_coaching_tip:
            tip_w = 320
            tip_h = 50
            tip_x = self.screen_w - tip_w - margin_right
            painter.setBrush(QBrush(QColor(20, 20, 35, 210)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(tip_x, 80, tip_w, tip_h, 10, 10)
            # 왼쪽 액센트 바
            painter.setBrush(QBrush(QColor(255, 105, 180)))
            painter.drawRoundedRect(tip_x, 80, 5, tip_h, 3, 3)
            painter.setPen(text_pen)
            painter.setFont(QFont("Malgun Gothic", 9, QFont.Weight.Bold))
            flags = (int(Qt.AlignmentFlag.AlignVCenter) |
                     int(Qt.AlignmentFlag.AlignLeft) |
                     int(Qt.TextFlag.TextWordWrap))
            clean_tip = self.current_coaching_tip
            for ch in "🛑💰💡⏰🐉🪱👁🟣🔍⚔️🛡":
                clean_tip = clean_tip.replace(ch, "")
            painter.drawText(tip_x + 12, 80, tip_w - 18, tip_h, flags, clean_tip.strip())

        # ── 2. 경고 배너 — 레퍼런스 이미지 위치 (우측 중하단) ──────────
        if self.current_coaching_tip and "🛑" in self.current_coaching_tip:
            warn_text = self.current_coaching_tip.replace("🛑", "").strip()
            draw_banner(
                y=lower_anchor_y,
                bg_color=QColor(190, 30, 30, 230),   # 진한 붉은색
                icon_color=QColor(255, 230, 0),       # 노란 경고 삼각형
                icon_char="▲",
                message=warn_text,
                font_size=11
            )

        # ── 3. 이벤트 알림 배너 — 경고 바로 위 or 단독으로 같은 위치 ────
        if self.current_event_tip:
            # 경고 배너가 있으면 그 위에, 없으면 같은 위치
            has_warning = bool(self.current_coaching_tip and "🛑" in self.current_coaching_tip)
            evt_y = lower_anchor_y - banner_h - 10 if has_warning else lower_anchor_y

            # 이벤트 종류에 따라 색상과 아이콘 결정
            tip_text = self.current_event_tip
            if "🐉" in tip_text:
                bg = QColor(180, 80, 20, 220)   # 주황
                icon_col = QColor(255, 200, 50)
                icon = "🐉"
            elif "🟣" in tip_text or "바론" in tip_text:
                bg = QColor(100, 30, 160, 220)  # 보라
                icon_col = QColor(220, 150, 255)
                icon = "◉"
            elif "🏰" in tip_text:
                bg = QColor(30, 90, 180, 220)   # 파랑
                icon_col = QColor(150, 210, 255)
                icon = "🏰"
            elif "💀" in tip_text:
                bg = QColor(60, 60, 60, 230)    # 어두운 회색
                icon_col = QColor(200, 200, 200)
                icon = "💀"
            elif "🔥" in tip_text:
                bg = QColor(200, 100, 0, 220)   # 주황-노랑
                icon_col = QColor(255, 220, 80)
                icon = "★"
            else:
                bg = QColor(30, 100, 60, 220)   # 초록
                icon_col = QColor(150, 255, 180)
                icon = "ⓘ"

            # 이모지 제거 후 텍스트만 출력
            clean_evt = tip_text
            for ch in "🔥💀⚔️🐉🏰🤝🩸🟣👁":
                clean_evt = clean_evt.replace(ch, "")
            draw_banner(
                y=evt_y,
                bg_color=bg,
                icon_color=icon_col,
                icon_char=icon,
                message=clean_evt.strip(),
                font_size=10
            )

        painter.end()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    print("Voice AI Coaching Overlay 가동 중... 터미널에서 Ctrl+C를 눌러 종료하세요.")
    coaching_app = CoachingOverlay()
    coaching_app.show()
    
    sys.exit(app.exec())
