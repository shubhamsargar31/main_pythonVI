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

let revealOnce = false;
function triggerReveal() {
    if (revealOnce) return;
    requestAnimationFrame(() => charImg.classList.add('reveal'));
    revealOnce = true;
}
if (charImg.complete) {
    setTimeout(triggerReveal, 50);
} else {
    charImg.addEventListener('load', triggerReveal, { once: true });
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
    let gifPath = "../assets/Start/starting.png"; // default/idle
    if (e === "idle") {
        gifPath = "../assets/Start/starting.png";
    } else if (e === "happy" || e === "joy") {
        const rand = Math.floor(Math.random() * 6) + 1; // HAPPY1..6
        gifPath = `../assets/Happy/HAPPY${rand}.gif`;
    } else if (e === "sad") {
        const rand = Math.floor(Math.random() * 4) + 1; // SAD1..4
        gifPath = `../assets/Sad/SAD${rand}.gif`;
    } else if (e.includes("alone") || e.includes("lonely")) {
        gifPath = "../assets/Sad/SAD4.gif";
    } else if (e === "love" || e === "heart") {
        gifPath = "../assets/Happy/HAPPY1.gif";
    } else if (e === "talk" || e === "smile" || e === "answer" || e === "question" || e === "ask" || e === "explain") {
        gifPath = "../assets/AnsEx/Explain1.gif";
    } else {
        // Fallback for unknown emotions: use explain GIF while speaking
        gifPath = "../assets/AnsEx/Explain1.gif";
    }

    // Preload image to avoid visible re-render hitch
    const nextImg = new Image();
    nextImg.onload = () => {
        charImg.onerror = () => { charImg.src = "../assets/Start/starting.png"; };
        const syncAfterLoad = () => { syncOutputBubble(); };
        charImg.addEventListener('load', syncAfterLoad, { once: true });
        charImg.src = gifPath;
    };
    nextImg.src = gifPath;
}

function stopListening() {
    document.body.classList.remove('listening');
}

// Expose functions to Python
window.updateResponse = updateResponse;
window.updateEmotion = updateEmotion;
window.stopListening = stopListening;
