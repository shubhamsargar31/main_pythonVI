import sys
import os
import pyttsx3
import speech_recognition as sr
import re
import signal

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel,
    QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QScrollArea
)
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer

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


class SpeakWorker(QThread):
    """Runs TTS in background thread so GUI doesn't freeze while speaking."""

    def __init__(self, text):
        super().__init__()
        self.text = text

    def run(self):
        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', 165)
            engine.setProperty('volume', 1)

            voices = engine.getProperty('voices')
            if len(voices) > 1:
                engine.setProperty('voice', voices[1].id)  # female voice
            else:
                engine.setProperty('voice', voices[0].id)

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


# ──────────────────────────────────────────────
# 🖥 Main Application Window
# ──────────────────────────────────────────────
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
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 🖼 Character Image
        self.character = QLabel()
        self.character.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_expression("neutral")

        # 💬 Chat Display Area (scrollable)
        self.chat_area = QLabel("")
        self.chat_area.setWordWrap(True)
        self.chat_area.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.chat_area.setStyleSheet("""
            QLabel {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 12px;
                padding: 16px;
                font-size: 14px;
                line-height: 1.5;
                color: #e6edf3;
            }
        """)
        self.chat_area.setMinimumHeight(150)

        scroll = QScrollArea()
        scroll.setWidget(self.chat_area)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)

        # ⌨ Input Box
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Kahi bhi type kar...")
        self.input_box.setStyleSheet("""
            QLineEdit {
                background-color: #161b22;
                border: 2px solid #30363d;
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 14px;
                color: #e6edf3;
            }
            QLineEdit:focus {
                border-color: #58a6ff;
            }
        """)
        self.input_box.returnPressed.connect(self.process_text)

        # 🔘 Buttons
        button_layout = QHBoxLayout()

        self.send_button = QPushButton("📩 Send")
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: bold;
                color: white;
            }
            QPushButton:hover { background-color: #2ea043; }
            QPushButton:disabled { background-color: #21262d; color: #484f58; }
        """)
        self.send_button.clicked.connect(self.process_text)

        self.voice_button = QPushButton("🎤 Speak")
        self.voice_button.setStyleSheet("""
            QPushButton {
                background-color: #1f6feb;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: bold;
                color: white;
            }
            QPushButton:hover { background-color: #388bfd; }
            QPushButton:disabled { background-color: #21262d; color: #484f58; }
        """)
        self.voice_button.clicked.connect(self.voice_input)

        self.clear_button = QPushButton("🗑 Clear Memory")
        self.clear_button.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 12px;
                color: #8b949e;
            }
            QPushButton:hover { background-color: #30363d; color: #e6edf3; }
        """)
        self.clear_button.clicked.connect(self.clear_memory)

        button_layout.addWidget(self.send_button)
        button_layout.addWidget(self.voice_button)

        # Add all widgets to layout
        layout.addWidget(self.character)
        layout.addWidget(scroll, stretch=1)
        layout.addWidget(self.input_box)
        layout.addLayout(button_layout)
        layout.addWidget(self.clear_button)

        self.setLayout(layout)

        # Show greeting
        self.chat_area.setText("💙 Hi! Mi Vi aahe — tuza AI companion. Bola, kaay chaallay?")
        self._prewarm()

    # 🎭 Change Character Expression
    def set_expression(self, emotion):
        img_path = os.path.join(BASE_DIR, "assets", f"{emotion}.png")
        if not os.path.exists(img_path):
            img_path = os.path.join(BASE_DIR, "assets", "neutral.png")
        pixmap = QPixmap(img_path)
        self.character.setPixmap(
            pixmap.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
        )

    # 🔒 Lock/Unlock UI during processing
    def set_ui_enabled(self, enabled):
        self.input_box.setEnabled(enabled)
        self.send_button.setEnabled(enabled)
        self.voice_button.setEnabled(enabled)

    # 💬 Process Text Input (async via QThread)
    def process_text(self):
        user_text = self.input_box.text().strip()
        if not user_text:
            return

        # Show user message
        self.chat_area.setText(f"🧑 You: {user_text}\n\n⏳ Vi sochte aahe...")
        self.input_box.clear()
        self.set_ui_enabled(False)
        self._last_user = user_text

        # Save user message to memory
        save_message("user", user_text)

        # Get conversation history
        history = get_recent_history(2)

        # Start background worker
        self.worker = ResponseWorker(user_text, history)
        self.worker.finished.connect(self.on_response)
        self.worker.progress.connect(self.on_progress)
        self.worker.start()

    # ✅ Handle LLM Response
    def on_response(self, user_text, response, emotion):
        # Disconnect signal to prevent duplicate callbacks
        try:
            self.worker.finished.disconnect(self.on_response)
        except TypeError:
            pass

        # Save assistant response to memory
        save_message("assistant", response, emotion)

        # Update UI
        self.chat_area.setText(f"🧑 You: {user_text}\n\n💙 Vi: {response}")
        self.set_expression(emotion)
        self.set_ui_enabled(True)
        self.input_box.setFocus()

        # Speak the response in background
        self.speak(response)

    def on_progress(self, buffer_text):
        m = re.search(r'"response"\s*:\s*"([^"]*)', buffer_text)
        text = m.group(1) if m else buffer_text
        self.chat_area.setText(f"🧑 You: {getattr(self, '_last_user', '')}\n\n💙 Vi: {text}")

    def _prewarm(self):
        class PrewarmWorker(QThread):
            def run(self_inner):
                try:
                    prewarm_model()
                except Exception:
                    pass
        if self.prewarm_worker is None:
            self.prewarm_worker = PrewarmWorker()
            self.prewarm_worker.finished.connect(self._on_prewarm_finished)
            self.prewarm_worker.start()

    def _on_prewarm_finished(self):
        try:
            self.prewarm_worker.finished.disconnect(self._on_prewarm_finished)
        except Exception:
            pass
        try:
            self.prewarm_worker.deleteLater()
        except Exception:
            pass
        self.prewarm_worker = None

    def closeEvent(self, event):
        try:
            if self.worker and self.worker.isRunning():
                self.worker.requestInterruption()
                self.worker.wait(1000)
        except Exception:
            pass
        try:
            if self.speak_worker and self.speak_worker.isRunning():
                self.speak_worker.requestInterruption()
                self.speak_worker.wait(1000)
        except Exception:
            pass
        try:
            if self.prewarm_worker and self.prewarm_worker.isRunning():
                self.prewarm_worker.requestInterruption()
                self.prewarm_worker.wait(1000)
        except Exception:
            pass
        event.accept()

    # 🎤 Voice Input
    def voice_input(self):
        self.chat_area.setText("🎤 Listening... bola!")
        self.set_ui_enabled(False)
        QApplication.processEvents()

        try:
            with sr.Microphone() as source:
                audio = self.recognizer.listen(source, phrase_time_limit=5)

            self.chat_area.setText("⏳ Processing...")
            QApplication.processEvents()

            text = self.recognizer.recognize_google(audio)
            self.input_box.setText(text)
            self.set_ui_enabled(True)
            self.process_text()

        except sr.UnknownValueError:
            self.chat_area.setText("😅 Samajla nahi, parat bola na!")
            self.set_ui_enabled(True)
        except sr.RequestError:
            self.chat_area.setText("🌐 Internet check kar, connection nahi!")
            self.set_ui_enabled(True)
        except Exception as e:
            self.chat_area.setText(f"⚠ Error: {e}")
            self.set_ui_enabled(True)

    # 🗑 Clear Conversation Memory
    def clear_memory(self):
        from memory import clear_memory
        clear_memory()
        self.chat_area.setText("🧹 Memory clear zali! Fresh start! Bola kaay chaallay?")
        self.set_expression("neutral")

    # 🔊 Text-to-Speech (runs in background thread)
    def speak(self, text):
        self.speak_worker = SpeakWorker(text)
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
