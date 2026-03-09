// Initialize Qt Bridge
let backend;
if (typeof QWebChannel !== 'undefined') {
    new QWebChannel(qt.webChannelTransport, function (channel) {
        backend = channel.objects.backend;
        console.log("Qt Bridge Connected");
    });
}

const inputField = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const micBtn = document.getElementById('mic-btn');
const responseText = document.getElementById('output-text');
const charImg = document.getElementById('character-img');
const outputBubble = document.querySelector('.output-bubble');
const characterContainer = document.querySelector('.character-container');

let currentEmotion = 'idle';
let lastIdleGif = null;
let idleLoopTimer = null;
const IDLE_GIF_INTERVAL = 10000; // ms; rotate start/idle gifs

// If the default Start.gif is missing, fallback to a valid one from Start folder
function ensureStartOnError() {
    if (!charImg) return;
    charImg.onerror = () => {
        pickStartGif((src) => { charImg.src = src; });
    };
}
ensureStartOnError();

function shuffle(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
}

function startGifCandidates() {
    const base = "../assets/Start/";
    const idleActCaps = Array.from({ length: 12 }, (_, i) => `${base}IDLEACT${i + 1}.gif`);
    const idleActCamel = Array.from({ length: 12 }, (_, i) => `${base}IdleAct${i + 1}.gif`);
    const idleCaps = Array.from({ length: 12 }, (_, i) => `${base}IDLE${i + 1}.gif`);
    const idleCamel = Array.from({ length: 12 }, (_, i) => `${base}Idle${i + 1}.gif`);
    const caps = Array.from({ length: 12 }, (_, i) => `${base}START${i + 1}.gif`);
    const camel = Array.from({ length: 12 }, (_, i) => `${base}Start${i + 1}.gif`);
    return shuffle([
        ...idleActCaps,
        ...idleActCamel,
        ...idleCaps,
        ...idleCamel,
        ...caps,
        ...camel,
        `${base}start.gif`,
        `${base}Start.gif`,
        `${base}START.gif`,
        `${base}idle.gif`,
        `${base}Idle.gif`,
        `${base}IDLE.gif`,
        `${base}IdleAct.gif`,
        `${base}IDLEACT.gif`
    ]);
}

function pickStartGif(cb) {
    let list = [];
    if (Array.isArray(window.START_GIFS) && window.START_GIFS.length) {
        list = shuffle(window.START_GIFS.slice());
    } else {
        list = startGifCandidates();
    }
    if (lastIdleGif) {
        list = list.filter((p) => p !== lastIdleGif);
        if (list.length === 0) list = startGifCandidates();
    }
    function tryNext(idx) {
        if (idx >= list.length) {
            cb("../assets/AnsEx/Explain1.gif");
            return;
        }
        const src = list[idx];
        const img = new Image();
        img.onload = () => { lastIdleGif = src; cb(src); };
        img.onerror = () => tryNext(idx + 1);
        img.src = src;
    }
    tryNext(0);
}

let revealOnce = false;
function triggerReveal() {
    if (revealOnce) return;
    startIdleLoop(true);
    requestAnimationFrame(() => charImg.classList.add('reveal'));
    revealOnce = true;
}
if (charImg.complete) {
    setTimeout(triggerReveal, 50);
} else {
    charImg.addEventListener('load', triggerReveal, { once: true });
}

function setStartGifOnce(onAfterSet) {
    pickStartGif((src) => {
        const nextImg = new Image();
        nextImg.onload = () => {
            charImg.onerror = () => { pickStartGif((s)=> { charImg.src = s; }); };
            const syncAfterLoad = () => { syncOutputBubble(); };
            charImg.addEventListener('load', syncAfterLoad, { once: true });
            charImg.src = src;
            if (typeof onAfterSet === 'function') onAfterSet();
        };
        nextImg.src = src;
    });
}

function startIdleLoop(immediate = false) {
    if (idleLoopTimer) return;
    const rotate = () => {
        setStartGifOnce(() => {
            idleLoopTimer = setTimeout(rotate, IDLE_GIF_INTERVAL);
        });
    };
    if (immediate) {
        rotate();
    } else {
        idleLoopTimer = setTimeout(rotate, IDLE_GIF_INTERVAL);
    }
}

function stopIdleLoop() {
    if (idleLoopTimer) {
        clearTimeout(idleLoopTimer);
        idleLoopTimer = null;
    }
}

function syncOutputBubble() {
    if (!outputBubble || !characterContainer || !charImg) return;
    const imgRect = charImg.getBoundingClientRect();
    const contRect = characterContainer.getBoundingClientRect();
    const centerX = imgRect.left - contRect.left + imgRect.width / 2;
    const centerY = imgRect.top - contRect.top + imgRect.height / 2;
    outputBubble.style.width = `${imgRect.width}px`;
    outputBubble.style.height = `${imgRect.height}px`;
    outputBubble.style.left = `${centerX}px`;
    outputBubble.style.top = `${centerY}px`;
}

window.addEventListener('resize', () => {
    syncOutputBubble();
});
charImg.addEventListener('load', () => {
    syncOutputBubble();
});

 

// 📩 Send Message
function sendMessage() {
    const text = inputField.value.trim();
    if (!text) return;
    inputField.value = '';
    responseText.innerText = "...";
    if (backend) {
        backend.process_text(text);
    }
}

inputField.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});

sendBtn.addEventListener('click', sendMessage);

// 🎤 Mic Action
micBtn.addEventListener('click', () => {
    if (backend) {
        document.body.classList.add('listening');
        backend.start_voice_input();
    }
});

// 🧠 Update UI from Python
function updateResponse(text) {
    responseText.innerText = text;
}

function updateEmotion(emotion) {
    if (!emotion) return;
    const e = String(emotion).toLowerCase();
    if (e === currentEmotion) return; // avoid redundant reloads
    currentEmotion = e;

    // Emotion-specific mapping
    let gifPath = "../assets/Start/Start.gif"; // default/idle
    if (e === "idle" || e === "talk" || e === "smile" || e === "answer") {
        startIdleLoop(true);
        return;
    } else if (e === "question" || e === "ask" || e === "explain") {
        stopIdleLoop();
        gifPath = "../assets/AnsEx/Explain1.gif";
    } else if (e === "happy" || e === "joy") {
        stopIdleLoop();
        const rand = Math.floor(Math.random() * 6) + 1; // HAPPY1..6
        gifPath = `../assets/Happy/HAPPY${rand}.gif`;
    } else if (e === "sad") {
        stopIdleLoop();
        const rand = Math.floor(Math.random() * 4) + 1; // SAD1..4
        gifPath = `../assets/Sad/SAD${rand}.gif`;
    } else if (e.includes("alone") || e.includes("lonely")) {
        stopIdleLoop();
        gifPath = "../assets/Sad/SAD4.gif";
    } else if (e === "love" || e === "heart") {
        stopIdleLoop();
        gifPath = "../assets/Happy/HAPPY1.gif";
    } else {
        // Fallback: default to idle loop
        startIdleLoop(true);
        return;
    }

    // Preload image to avoid visible re-render hitch
    const nextImg = new Image();
    nextImg.onload = () => {
        charImg.onerror = () => { pickStartGif((s)=> { charImg.src = s; }); };
        const syncAfterLoad = () => { syncOutputBubble(); };
        charImg.addEventListener('load', syncAfterLoad, { once: true });
        charImg.src = gifPath;
    };
    nextImg.src = gifPath;
}

function stopListening() {
    document.body.classList.remove('listening');
}

function startSpeaking() {
    document.body.classList.add('speaking');
}

function stopSpeaking() {
    document.body.classList.remove('speaking');
}

function setInputAndSend(text) {
    inputField.value = text || '';
    sendMessage();
}

// Expose functions to Python
window.updateResponse = updateResponse;
window.updateEmotion = updateEmotion;
window.stopListening = stopListening;
window.startSpeaking = startSpeaking;
window.stopSpeaking = stopSpeaking;
window.setInputAndSend = setInputAndSend;
