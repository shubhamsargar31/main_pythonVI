import sys
import os
import pyttsx3
import speech_recognition as sr
import re
import signal
import json
import winsound  # For playing Coqui TTS output on Windows

try:
    from TTS.api import TTS  
    COQUI_AVAILABLE = True
    # Global model instance to avoid reloading
    COQUI_MODEL = None
except ImportError:
    COQUI_AVAILABLE = False
    COQUI_MODEL = None

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel,
    QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QScrollArea, QFrame, QStackedLayout
)
from PyQt6.QtGui import QPixmap, QFont, QMovie, QPalette, QBrush, QGuiApplication
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize, QUrl, QObject, pyqtSlot
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel

from brain import get_response, stream_response, parse_response, prewarm_model, detect_emotion_from_user
from memory import init_db, save_message, get_recent_history

# Ensure asset paths work regardless of working directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ──────────────────────────────────────────────
# 🧵 Background Worker for LLM calls
# ──────────────────────────────────────────────
class ResponseWorker(QThread):
    """Runs Gemini API call in background thread so GUI stays responsive."""
    finished = pyqtSignal(str, str, str)
    progress = pyqtSignal(str)

    def __init__(self, user_input, history):
        super().__init__()
        self.user_input = user_input
        self.history = history

    def run(self):
        try:
            buffer = ""
            for chunk in stream_response(self.user_input, self.history):
                if self.isInterruptionRequested():
                    break
                buffer += chunk
                self.progress.emit(buffer)
            if buffer:
                response, emotion = parse_response(buffer)
                study_words = [
                    "study", "homework", "definition", "notes", "formula", "solve", "practice",
                    "explain", "steps", "how", "why",
                ]
                is_study = any(w in (self.user_input or "").lower() for w in study_words)
                emotion = "neutral" if is_study else detect_emotion_from_user(self.user_input)
                self.finished.emit(self.user_input, response, emotion)
        except KeyboardInterrupt:
            pass


class PrewarmWorker(QThread):
    """Initializes LLM model on startup to reduce first-response delay."""
    def run(self):
        try:
            prewarm_model()
        except Exception:
            pass


class SpeakWorker(QThread):
    """Runs TTS in background thread so GUI doesn't freeze while speaking."""
    speaking_started = pyqtSignal()
    speaking_finished = pyqtSignal()

    def __init__(self, text):
        super().__init__()
        self.text = text

    def run(self):
        try:
            try:
                self.speaking_started.emit()
            except Exception:
                pass
            if COQUI_AVAILABLE:
                global COQUI_MODEL
                if COQUI_MODEL is None:
                    # Using a fast and small model
                    COQUI_MODEL = TTS(model_name="tts_models/en/ljspeech/vits", progress_bar=False, gpu=False)
                
                temp_path = os.path.join(BASE_DIR, "temp_voice.wav")
                COQUI_MODEL.tts_to_file(text=self.text, file_path=temp_path)
                
                if os.path.exists(temp_path):
                    winsound.PlaySound(temp_path, winsound.SND_FILENAME)
            else:
                engine = pyttsx3.init()
                engine.setProperty('rate', 140)
                engine.setProperty('volume', 1)

                voices = engine.getProperty('voices')
                preferred_voice = None
                for v in voices:
                    name = (v.name or "").lower()
                    vid = (v.id or "").lower()
                    if "zira" in name or "female" in name or "woman" in name or "zira" in vid:
                        preferred_voice = v.id
                        break
                if preferred_voice is None and voices:
                    preferred_voice = voices[0].id
                if preferred_voice:
                    engine.setProperty('voice', preferred_voice)

                engine.say(self.text)
                engine.runAndWait()
                engine.stop()
        except Exception as e:
            print(f"[Speech Error] {e}")
        except KeyboardInterrupt:
            try:
                engine.stop()
            except Exception:
                pass
        finally:
            try:
                self.speaking_finished.emit()
            except Exception:
                pass


# ──────────────────────────────────────────────
# 🖥 Main Application Window
# ──────────────────────────────────────────────
# ──────────────────────────────────────────────
# 🔗 Python-JS Bridge
# ──────────────────────────────────────────────
class Backend(QObject):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

    @pyqtSlot(str)
    def process_text(self, text):
        self.main_window.process_text_from_web(text)

    @pyqtSlot()
    def start_voice_input(self):
        self.main_window.voice_input()

class AIAssistant(QWidget):
    def __init__(self):
        super().__init__()

        # Initialize memory database
        init_db()

        self.setWindowTitle("Vi — Your AI Companion 💙")
        self.setGeometry(100, 100, 450, 700)
        self.setMinimumSize(400, 600)
        self.setStyleSheet("""
            QWidget {
                background-color: #0d1117;
                color: #e6edf3;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
        """)

        # 🎤 Speech Recognizer
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 150
        self.recognizer.pause_threshold = 0.8
        self.recognizer.dynamic_energy_threshold = True

        # Track worker threads
        self.worker = None
        self.speak_worker = None
        self.prewarm_worker = None

        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle("Vi Companion")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 🌐 Web View
        self.web_view = QWebEngineView()
        self.web_view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        
        # Setup Bridge
        self.channel = QWebChannel()
        self.backend = Backend(self)
        self.channel.registerObject("backend", self.backend)
        self.web_view.page().setWebChannel(self.channel)

        # Load HTML
        ui_file = os.path.join(BASE_DIR, "ui", "index.html")
        self.web_view.setUrl(QUrl.fromLocalFile(ui_file))
        
        layout.addWidget(self.web_view)

        self._prewarm()
        self._center_and_resize()
        try:
            self.web_view.loadFinished.connect(lambda _: self._push_start_gifs())
        except Exception:
            pass

    def _center_and_resize(self):
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            w = min(450, int(geo.width() * 0.45))
            h = min(900, int(geo.height() * 0.78))
            self.resize(w, h)
            fg = self.frameGeometry()
            fg.moveCenter(geo.center())
            self.move(fg.topLeft())

    def _prewarm(self):
        """Warm up the model in a background thread."""
        self.prewarm_worker = PrewarmWorker()
        self.prewarm_worker.start()

    def _push_start_gifs(self):
        try:
            start_dir = os.path.join(BASE_DIR, "assets", "Start")
            files = []
            if os.path.isdir(start_dir):
                for name in os.listdir(start_dir):
                    if name.lower().endswith(".gif"):
                        files.append(f"../assets/Start/{name}")
            # stable order but JS will randomize
            files.sort()
            import json as _json
            js = f"window.START_GIFS = {_json.dumps(files)};"
            self.web_view.page().runJavaScript(js)
        except Exception:
            pass

    def process_text_from_web(self, text):
        self._last_user = text
        save_message("user", text)
        history = get_recent_history(2)
        
        self.worker = ResponseWorker(text, history)
        self.worker.finished.connect(self.on_response)
        self.worker.progress.connect(self.on_progress)
        self.worker.start()

    def on_progress(self, buffer_text):
        # Update text in Web UI
        m = re.search(r'"response"\s*:\s*"([^"]*)', buffer_text)
        text = m.group(1) if m else buffer_text
        clean_text = text.replace('"', '\\"').replace('\n', '<br>')
        self.web_view.page().runJavaScript(f"updateResponse(\"{clean_text}\")")

    def on_response(self, user_input, response, emotion):
        save_message("assistant", response)
        
        # Route logic for visual
        study_words = ["study", "homework", "definition", "notes", "formula", "solve", "practice", "explain", "steps", "how", "why"]
        is_study = any(w in (user_input or "").lower() for w in study_words)
        
        final_emotion = "smile" if is_study else (emotion if emotion != "neutral" else "talk")
        
        # Update Web UI
        clean_resp = response.replace('"', '\\"').replace('\n', '<br>')
        self.web_view.page().runJavaScript(f"updateResponse(\"{clean_resp}\")")
        # Emotion during speaking is handled by SpeakWorker signals
        self.web_view.page().runJavaScript("stopListening()")
        
        self.speak(response, final_emotion)

    def voice_input(self):
        # Notify web UI that we are listening
        self.web_view.page().runJavaScript("document.body.classList.add('listening')")
        
        class VoiceWorker(QThread):
            text_received = pyqtSignal(str)
            error_occurred = pyqtSignal(str)
            
            def run(self_inner):
                import speech_recognition as sr
                recognizer = self.recognizer
                with sr.Microphone() as source:
                    try:
                        recognizer.adjust_for_ambient_noise(source, duration=0.6)
                        audio = recognizer.listen(source, timeout=6, phrase_time_limit=12)
                        text = recognizer.recognize_google(audio)
                        self_inner.text_received.emit(text or "")
                    except Exception as e:
                        self_inner.error_occurred.emit(str(e))

        self.voice_worker = VoiceWorker()
        self.voice_worker.text_received.connect(
            lambda t: (
                self.web_view.page().runJavaScript("stopListening()"),
                self.web_view.page().runJavaScript(f"setInputAndSend({json.dumps(t)})")
            ) if t.strip() else self.web_view.page().runJavaScript("updateResponse(\"Voice input ऐकू आलं नाही. पुन्हा try करा.\")")
        )
        self.voice_worker.error_occurred.connect(
            lambda e: (
                self.web_view.page().runJavaScript("stopListening()"),
                self.web_view.page().runJavaScript("updateResponse(\"Mic error आला. कृपया microphone access तपासा.\")"),
            )
        )
        self.voice_worker.start()

    # 🗑 Clear Conversation Memory
    def clear_memory(self):
        from memory import clear_memory
        clear_memory()
        self.chat_area.setText("🧹 Memory clear zali! Fresh start! Bola kaay chaallay?")
        self.set_expression("neutral")

    # 🔊 Text-to-Speech (runs in background thread)
    def speak(self, text, emotion="talk"):
        self.speak_worker = SpeakWorker(text)
        self.speak_worker.speaking_started.connect(
            lambda: (
                self.web_view.page().runJavaScript(f"updateEmotion('{emotion}')"),
                self.web_view.page().runJavaScript("startSpeaking()"),
            )
        )
        self.speak_worker.speaking_finished.connect(
            lambda: (
                self.web_view.page().runJavaScript("stopSpeaking()"),
                self.web_view.page().runJavaScript("updateEmotion('idle')"),
            )
        )
        # Do not force 'idle' after speaking; keep last emotion's GIF visible
        self.speak_worker.start()


# 🚀 Run Application
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Set global font
    font = QFont("Segoe UI", 11)
    app.setFont(font)

    def _sigint_handler(sig, frame):
        try:
            QApplication.instance().quit()
        except Exception:
            pass
    try:
        signal.signal(signal.SIGINT, _sigint_handler)
    except Exception:
        pass
    t = QTimer()
    t.start(250)
    t.timeout.connect(lambda: None)

    window = AIAssistant()
    window.show()
    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        try:
            QApplication.instance().quit()
        except Exception:
            pass
