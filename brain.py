import json
import requests
from config import OLLAMA_BASE_URL, MODEL_NAME, SYSTEM_PROMPT, SYSTEM_PROMPT_FAST, OLLAMA_OPTIONS, STOP_TOKENS, KEEP_ALIVE, FAST_MODE, FAST_OPTIONS
from memory import get_recent_history

VALID_EMOTIONS = {"happy", "sad", "neutral", "love"}
EMOTION_MAP = {
    "excited": "happy",
    "angry": "neutral",
    "frustrated": "neutral",
    "anxious": "neutral",
    "confused": "neutral",
    "lonely": "love",
    "happy": "happy",
    "sad": "sad",
    "neutral": "neutral",
}


def ollama_up(timeout=3):
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=timeout)
        return r.ok
    except Exception:
        return False

def parse_response(raw_text):
    text = raw_text.strip()
    emotion = "neutral"
    return text, emotion


def detect_emotion_from_user(user_text):
    txt = (user_text or "").lower()
    pos = [
        "happy", "great", "awesome", "nice", "good", "thanks", "thank you", "love",
        "mast", "khush", "आनंदी", "खुश", "छान", "भारी",
        "😍", "😊", "🙂", "❤️", "💙", "👍",
    ]
    neg_sad = [
        "sad", "upset", "down", "cry", "lonely", "alone", "depressed", "hurt",
        "dukh", "dukhi", "दुख", "दुःखी", "एकटा", "एकटी", "रडतो", "रडते",
        "😢", "🥺", "💔",
    ]
    anger = [
        "angry", "frustrated", "irritated", "mad", "annoyed", "furious", "rage",
        "raga", "राग", "चिडलो", "चिडली",
        "😡", "🤬",
    ]
    anxious_confused = [
        "anxious", "anxiety", "tension", "stress", "confused", "worry", "panic",
        "तणाव", "चिंता", "गोंधळ", "भीती",
        "😰", "😟",
    ]
    love_lonely = [
        "miss you", "need friend", "need someone", "love you", "love", "care",
        "एकटा वाटतं", "सोबत", "प्रेम", "मायेची गरज",
        "❤️", "🤗",
    ]
    score = {"happy": 0, "sad": 0, "neutral": 0, "love": 0}
    for w in pos:
        if w in txt:
            score["happy"] += 2
    for w in neg_sad:
        if w in txt:
            score["sad"] += 2
    for w in anger:
        if w in txt:
            score["neutral"] += 2
    for w in anxious_confused:
        if w in txt:
            score["neutral"] += 1
    for w in love_lonely:
        if w in txt:
            score["love"] += 2
    exclaim = txt.count("!") > 0
    if exclaim:
        if score["happy"] > 0:
            score["happy"] += 1
        if score["neutral"] > 0:
            score["neutral"] += 1
    top = max(score.items(), key=lambda x: x[1])
    if top[1] == 0:
        return "neutral"
    return top[0]


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


def decide_options(user_input):
    text = (user_input or "").lower()
    long_signals = [
        "detail", "explain", "steps", "why", "how", "full", "long",
        "samjhau", "samjhav", "समजाव", "उदाहरण", "example", "guide",
        "study", "homework", "definition", "notes", "formula", "solve", "practice",
    ]
    is_long = any(k in text for k in long_signals) or len(text) > 120
    opts = dict(FAST_OPTIONS if FAST_MODE and not is_long else OLLAMA_OPTIONS)
    if is_long:
        if opts.get("num_predict", 60) != -1:
            opts["num_predict"] = max(opts.get("num_predict", 60), 120)
        opts["temperature"] = min(opts.get("temperature", 0.6), 0.7)
        opts["top_p"] = opts.get("top_p", 0.85)
    else:
        words = len((user_input or "").split())
        if words <= 6:
            np = 40
        elif words <= 15:
            np = 70
        elif words <= 30:
            np = 100
        else:
            np = 140
        opts["num_predict"] = np
        opts["temperature"] = min(opts.get("temperature", 0.6), 0.55)
    return opts


AVAILABLE_MODELS = None

def list_available_models():
    global AVAILABLE_MODELS
    if AVAILABLE_MODELS is not None:
        return AVAILABLE_MODELS
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        if r.ok:
            data = r.json()
            AVAILABLE_MODELS = [m.get("name") for m in data.get("models", []) if m.get("name")]
        else:
            AVAILABLE_MODELS = []
    except Exception:
        AVAILABLE_MODELS = []
    return AVAILABLE_MODELS


def decide_model(user_input):
    text = (user_input or "").lower()
    long_signals = [
        "detail", "explain", "steps", "why", "how", "full", "long",
        "samjhau", "samjhav", "समजाव", "उदाहरण", "example", "guide",
    ]
    is_long = any(k in text for k in long_signals) or len(text) > 120
    available = set(list_available_models())
    if FAST_MODE and not is_long:
        if "gemma3:1b" in available:
            return "gemma3:1b"
        if "qwen2.5:3b-instruct" in available:
            return "qwen2.5:3b-instruct"
        return MODEL_NAME
    else:
        if "qwen2.5:3b-instruct" in available:
            return "qwen2.5:3b-instruct"
        return MODEL_NAME


def get_response(user_input, history=None):
    try:
        if not ollama_up(timeout=2):
            raise RuntimeError("Ollama server not reachable")
        if history is None:
            history = get_recent_history(2)

        prompt = build_prompt(user_input, history)
        options = decide_options(user_input)
        text = (user_input or "").lower()
        long_signals = [
            "detail", "explain", "steps", "why", "how", "full", "long",
            "samjhau", "samjhav", "समजाव", "उदाहरण", "example", "guide",
        ]
        is_long = any(k in text for k in long_signals) or len(text) > 120
        sys_prompt = SYSTEM_PROMPT_FAST if (FAST_MODE and not is_long) else SYSTEM_PROMPT
        model_name = decide_model(user_input)

        session = requests.Session()
        response = session.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": options,
                "system": sys_prompt,
                "keep_alive": KEEP_ALIVE,
            },
            timeout=(5, 60),
        )
        response.raise_for_status()

        raw_text = response.json()["response"]

        resp_text, _ = parse_response(raw_text)
        study_words = [
            "study", "homework", "definition", "notes", "formula", "solve", "practice",
            "explain", "steps", "how", "why",
        ]
        is_study = any(w in (user_input or "").lower() for w in study_words)
        return resp_text, ("neutral" if is_study else detect_emotion_from_user(user_input))

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
            history = get_recent_history(2)
        prompt = build_prompt(user_input, history)
        options = decide_options(user_input)
        text = (user_input or "").lower()
        long_signals = [
            "detail", "explain", "steps", "why", "how", "full", "long",
            "samjhau", "samjhav", "समजाव", "उदाहरण", "example", "guide",
        ]
        is_long = any(k in text for k in long_signals) or len(text) > 120
        sys_prompt = SYSTEM_PROMPT_FAST if (FAST_MODE and not is_long) else SYSTEM_PROMPT
        model_name = decide_model(user_input)
        session = requests.Session()
        emitted = False
        with session.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": model_name,
                "prompt": prompt,
                "stream": True,
                "options": options,
                "system": sys_prompt,
                "keep_alive": KEEP_ALIVE,
            },
            stream=True,
            timeout=(5, 120),
        ) as resp:
            if resp.status_code != 200:
                try:
                    print(f"[Stream HTTP Error] {resp.status_code} {resp.text}")
                except Exception:
                    pass
                yield '{"response":"Server la thoda issue aala. Thodya velane parat try kara.","emotion":"neutral"}'
                return
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                if "error" in data:
                    try:
                        print(f"[Stream Error] {data['error']}")
                    except Exception:
                        pass
                    continue
                chunk = data.get("response", "")
                if chunk:
                    yield chunk
                    emitted = True
                if data.get("done", False):
                    break
        if not emitted:
            r, emo = get_response(user_input, history)
            yield r
    except Exception as e:
        try:
            print(f"[Stream Exception] {e}")
        except Exception:
            pass
        yield '{"response":"Thoda issue aala, parat try karu ya!","emotion":"neutral"}'


def prewarm_model():
    try:
        if not ollama_up(timeout=2):
            return
        model_name = decide_model("hello")
        session = requests.Session()
        session.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": model_name,
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
