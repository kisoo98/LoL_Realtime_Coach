import sys
import time
import os
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen

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
# 2. 실시간 정보 폴링 스레드
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
                
                # --- AI 코칭 팁 판별 ---
                coaching_tip = ""
                if health_pct <= 20 and curr_health > 0:
                    coaching_tip = "🛑 체력이 20% 이하로 위험합니다! 무리하지 말고 귀환을 고려하세요."
                elif current_gold >= 1500:
                    coaching_tip = f"💰 현재 {int(current_gold)} 골드 보유. 집에 다녀와서 코어 아이템을 구매할 타이밍입니다!"
                elif current_gold >= 1100 and game_time < 600:
                    coaching_tip = f"💡 전술 팁: {int(current_gold)} 골드로 라인전을 압박할 하위템을 구매하세요."
                elif game_time < 100:
                    coaching_tip = "초반 시야 장악을 준비하세요. 적 정글 위치 파악이 중요합니다."
                elif 840 < game_time < 900:
                    coaching_tip = "⏰ 곧 14분입니다. 타워 방패가 소멸되니 굴려놓은 이득을 수거하세요!"
                elif 1140 < game_time < 1500:
                    coaching_tip = "🐉 20분이 다가옵니다. 바론 시야를 장악할 준비를 하세요!"
                else:
                    coaching_tip = "미니맵을 수시로 확인하세요."

                # --- 실시간 타임라인 이벤트 판별 ---
                event_tip = ""
                if len(events) > self.last_event_count:
                    recent_event = events[-1]
                    evt_type = recent_event.get("EventName")
                    
                    if evt_type == "ChampionKill":
                        killer = recent_event.get("KillerName", "")
                        victim = recent_event.get("VictimName", "")
                        if killer == my_name:
                            event_tip = "🔥 나이스 킬! 이제 라인을 밀어넣고 귀환 타이밍을 잡으세요."
                        elif victim == my_name:
                            event_tip = "💀 데스 발생. 부활 전까지 상대 스펠 여부를 브리핑하세요."
                        else:
                            event_tip = f"⚔️ 교전 발생! {killer} 님이 {victim} 님을 처치했습니다."
                            
                    elif evt_type == "DragonKill":
                        killer = recent_event.get("KillerName", "")
                        event_tip = f"🐉 용 처치됨. 상대 정글 동선 예측에 활용하세요! 처치자: {killer}"
                        
                    elif evt_type == "TurretKilled":
                        killer = recent_event.get("KillerName", "")
                        event_tip = f"🏰 포탑 파괴 알림! 다른 라인으로 로밍 갈 기회입니다."
                    
                    self.last_event_count = len(events)

                # --- 처음 발생한 멘트만 TTS 큐 및 화면 알림에 넣기 위해 분리 ---
                speeches = []
                new_coaching_tip = None
                
                # 코칭 팁이 새롭게 바뀌었을 때
                if coaching_tip and coaching_tip != self.last_coaching_tip:
                    self.last_coaching_tip = coaching_tip
                    new_coaching_tip = coaching_tip
                    # 기호나 이모티콘은 TTS 오류를 방지하기 위해 제거
                    clean_text = coaching_tip.replace("🛑", "").replace("💰", "").replace("💡", "").replace("⏰", "").replace("🐉", "")
                    speeches.append(clean_text)

                # 이벤트 알림이 새롭게 발생했을 때
                new_event_tip = None
                if event_tip and event_tip != self.last_event_tip:
                    self.last_event_tip = event_tip
                    new_event_tip = event_tip
                    clean_text = event_tip.replace("🔥", "").replace("💀", "").replace("⚔️", "").replace("🐉", "").replace("🏰", "")
                    speeches.append(clean_text)

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
        self.setGeometry(0, 0, 1920, 1080)
        self.setWindowTitle('League of Legends AI Coach (PyQt6)')
        
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowTransparentForInput | 
            Qt.WindowType.ToolTip
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.showFullScreen()

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

        bg_brush = QBrush(QColor(30, 30, 40, 230))
        text_pen = QPen(QColor(255, 255, 255))
        
        if self.status == "waiting":
            painter.setBrush(bg_brush)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(800, 50, 320, 60, 12, 12)
            
            painter.setPen(text_pen)
            painter.setFont(QFont("Malgun Gothic", 12, QFont.Weight.Bold))
            painter.drawText(800, 50, 320, 60, Qt.AlignmentFlag.AlignCenter, self.msg)
            
        elif self.status == "ingame":
            base_y = 150
            margin_right = 20
            width = 540
            height = 55
            x_pos = 1920 - width - margin_right

            # 💡 1. 메인 코칭 배너 / 경고 배너
            if self.current_coaching_tip:
                # 🛑 이 포함되어 있는지로 경고성 멘트 여부 판단
                is_warning = "🛑" in self.current_coaching_tip
                
                if is_warning:
                    # 사진처럼 하단 챔피언 포트레이트 바로 위쪽(우측 중간)으로 위치 변경!
                    warn_y = 570
                    warn_height = 65
                    
                    # 붉은 반투명 배경 및 선명한 붉은색 테두리
                    painter.setBrush(QBrush(QColor(180, 40, 40, 220))) 
                    border_pen = QPen(QColor(255, 80, 80, 255))
                    border_pen.setWidth(2)
                    painter.setPen(border_pen)
                    
                    # 모서리가 많이 둥근 테두리
                    painter.drawRoundedRect(x_pos, warn_y, width, warn_height, 15, 15)
                    
                    # 다시 텍스트 작성용 흰색 펜으로 복귀
                    painter.setPen(text_pen)
                    painter.setFont(QFont("Malgun Gothic", 12, QFont.Weight.Bold))
                    
                    # 텍스트 앞에 경고 기호로 대체 삽입
                    warn_text = self.current_coaching_tip.replace("🛑", "⚠ 경고:")
                    
                    flags = int(Qt.AlignmentFlag.AlignVCenter) | int(Qt.AlignmentFlag.AlignLeft) | int(Qt.TextFlag.TextWordWrap)
                    painter.drawText(x_pos + 20, warn_y, width - 30, warn_height, flags, warn_text)
                    
                else:
                    painter.setBrush(QBrush(QColor(43, 33, 43, 230))) 
                    painter.setPen(Qt.PenStyle.NoPen)
                    
                    painter.drawRoundedRect(x_pos, base_y, width, height, 10, 10)
                    
                    painter.setBrush(QBrush(QColor(255, 105, 180))) 
                    painter.drawRoundedRect(x_pos, base_y, 6, height, 3, 3)

                    painter.setPen(text_pen)
                    painter.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
                    
                    flags = int(Qt.AlignmentFlag.AlignVCenter) | int(Qt.AlignmentFlag.AlignLeft) | int(Qt.TextFlag.TextWordWrap)
                    painter.drawText(x_pos + 15, base_y, width - 25, height, flags, self.current_coaching_tip)
                    
                    base_y += height + 10 

            # 🔔 2. 우측 상단 긴급 알림 배너 (일반 이벤트)
            if self.current_event_tip:
                painter.setBrush(QBrush(QColor(56, 128, 255, 220)))
                painter.setPen(Qt.PenStyle.NoPen)
                
                painter.drawRoundedRect(x_pos, base_y, width, height, 10, 10)
                
                painter.setPen(text_pen)
                painter.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
                
                flags = int(Qt.AlignmentFlag.AlignVCenter) | int(Qt.AlignmentFlag.AlignLeft) | int(Qt.TextFlag.TextWordWrap)
                painter.drawText(x_pos + 15, base_y, width - 25, height, flags, f"ⓘ {self.current_event_tip}")

        painter.end()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    print("Voice AI Coaching Overlay 가동 중... 터미널에서 Ctrl+C를 눌러 종료하세요.")
    coaching_app = CoachingOverlay()
    coaching_app.show()
    
    sys.exit(app.exec())
