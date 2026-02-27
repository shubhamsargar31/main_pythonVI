import json
import requests
from config import OLLAMA_BASE_URL, MODEL_NAME, SYSTEM_PROMPT, OLLAMA_OPTIONS, STOP_TOKENS, KEEP_ALIVE
from memory import get_recent_history

VALID_EMOTIONS = {"happy", "sad", "neutral", "love"}


def ollama_up(timeout=3):
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=timeout)
        return r.ok
    except Exception:
        return False

def parse_response(raw_text):
    """
    Parse JSON response from Ollama model.
    """
    text = raw_text.strip()

    try:
        data = json.loads(text)
        response = data.get("response", text)
        emotion = data.get("emotion", "neutral").lower().strip()

        if emotion not in VALID_EMOTIONS:
            emotion = "neutral"

        return response, emotion

    except json.JSONDecodeError:
        return raw_text.strip(), "neutral"


def build_prompt(user_input, history):
    """
    Combine system prompt + history + new input
    """
    conversation = ""

    for msg in history:
        role = "User" if msg["role"] == "user" else "Assistant"
        conversation += f"{role}: {msg['message']}\n"

    conversation += f"User: {user_input}\nAssistant:"

    return conversation


def get_response(user_input, history=None):
    try:
        if not ollama_up(timeout=2):
            raise RuntimeError("Ollama server not reachable")
        if history is None:
            history = get_recent_history(4)

        prompt = build_prompt(user_input, history)

        session = requests.Session()
        response = session.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": OLLAMA_OPTIONS,
                "stop": STOP_TOKENS,
                "format": "json",
                "system": SYSTEM_PROMPT,
                "keep_alive": KEEP_ALIVE,
            },
            timeout=(5, 60),
        )
        response.raise_for_status()

        raw_text = response.json()["response"]

        return parse_response(raw_text)

    except Exception as e:
        print(f"[Brain Error] {e}")
        return (
            "Arre yaar thoda technical issue aala 😅 Ek minute thaamb na.",
            "neutral",
        )


def stream_response(user_input, history=None):
    try:
        if not ollama_up(timeout=2):
            yield '{"response":"Ollama server offline distoy. Thoda velane try kara.","emotion":"neutral"}'
            return
        if history is None:
            history = get_recent_history(4)
        prompt = build_prompt(user_input, history)
        session = requests.Session()
        emitted = False
        with session.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": True,
                "options": OLLAMA_OPTIONS,
                "stop": STOP_TOKENS,
                "format": "json",
                "system": SYSTEM_PROMPT,
                "keep_alive": KEEP_ALIVE,
            },
            stream=True,
            timeout=(5, 60),
        ) as resp:
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                chunk = data.get("response", "")
                if chunk:
                    yield chunk
                    emitted = True
                if data.get("done", False):
                    break
        if not emitted:
            r, emo = get_response(user_input, history)
            yield json.dumps({"response": r, "emotion": emo})
    except Exception:
        yield '{"response":"Thoda issue aala, parat try karu ya!","emotion":"neutral"}'


def prewarm_model():
    try:
        if not ollama_up(timeout=2):
            return
        session = requests.Session()
        session.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": "User: hello\nAssistant:",
                "stream": False,
                "options": {"num_predict": 1},
                "stop": STOP_TOKENS,
                "keep_alive": KEEP_ALIVE,
            },
            timeout=(5, 30),
        )
    except Exception:
        pass
