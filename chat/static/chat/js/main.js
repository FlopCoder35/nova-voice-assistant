let audioContext;
let websocket;
let mediaStream;
let audioWorkletNode;

let nextPlayTime = 0;
let activeSources = [];

function playAudioChunk(arrayBuffer) {
    if (!audioContext) return;
    
    // Decode 16-bit PCM to Float32 for Web Audio API
    const int16Array = new Int16Array(arrayBuffer);
    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
        float32Array[i] = int16Array[i] / 32768.0;
    }
    
    // Create an audio buffer at the 24kHz target sample rate
    const audioBuffer = audioContext.createBuffer(1, float32Array.length, 24000);
    audioBuffer.getChannelData(0).set(float32Array);
    
    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);
    
    // Schedule exact playback time for seamless gapless chaining
    if (nextPlayTime < audioContext.currentTime) {
        nextPlayTime = audioContext.currentTime;
    }
    
    source.start(nextPlayTime);
    nextPlayTime += audioBuffer.duration;
    
    activeSources.push(source);
    
    source.onended = () => {
        const idx = activeSources.indexOf(source);
        if (idx > -1) activeSources.splice(idx, 1);
    };
}

function stopAndClearAudio() {
    activeSources.forEach(source => {
        try { source.stop(); } catch (e) {}
    });
    activeSources = [];
    nextPlayTime = 0;
}

const startBtn = document.getElementById('start-btn');
const stopBtn = document.getElementById('stop-btn');
const orbContainer = document.querySelector('.orb-container');
const orb = document.getElementById('orb');
const statusText = document.getElementById('status-text');
const serverMessages = document.getElementById('server-messages');

function addServerMessage(msg) {
    // Remove placeholder if it exists
    const placeholder = document.querySelector('.message-placeholder');
    if (placeholder) placeholder.remove();

    const p = document.createElement('p');
    p.textContent = `> ${msg}`;
    serverMessages.appendChild(p);
    serverMessages.scrollTop = serverMessages.scrollHeight;
}

startBtn.addEventListener('click', async () => {
    try {
        statusText.textContent = "Requesting microphone access...";
        
        // 1. Get audio stream at 16kHz
        mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                sampleRate: 16000,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true
            }
        });

        statusText.textContent = "Connecting to server...";

        // 2. Setup WebSocket connection
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        websocket = new WebSocket(`${wsProtocol}//${window.location.host}/ws/audio/`);
        websocket.binaryType = 'arraybuffer'; // Expect and send binary data

        websocket.onopen = async () => {
            statusText.textContent = "Listening...";
            statusText.style.color = "var(--secondary)";
            
            // UI Updates
            startBtn.disabled = true;
            stopBtn.disabled = false;
            orbContainer.classList.add('active');
            orb.classList.add('active');
            serverMessages.innerHTML = ''; // Clear old messages
            addServerMessage("Connection established.");

            // 3. Setup AudioContext and Worklet
            audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000
            });

            // Need absolute or correct relative path to the processor script
            await audioContext.audioWorklet.addModule('/static/chat/js/audio_processor.js');
            
            const source = audioContext.createMediaStreamSource(mediaStream);
            audioWorkletNode = new AudioWorkletNode(audioContext, 'pcm-processor');

            // 4. Handle chunks from the AudioWorklet
            let lastInterruptTime = 0;
            audioWorkletNode.port.onmessage = (event) => {
                // Interruption hook: local volume metering says user is speaking
                if (typeof event.data === 'string' && event.data === 'user_speaking') {
                    const now = Date.now();
                    if (now - lastInterruptTime > 1000) { // Debounce 1 second
                        stopAndClearAudio();
                        if (websocket && websocket.readyState === WebSocket.OPEN) {
                            websocket.send(JSON.stringify({ type: "interrupt" }));
                        }
                        lastInterruptTime = now;
                    }
                    return;
                }
                
                if (websocket && websocket.readyState === WebSocket.OPEN) {
                    // Send binary PCM chunk to Django Channels consumer
                    websocket.send(event.data);
                }
            };

            source.connect(audioWorkletNode);
            // Connect to destination to keep processing alive in some browsers
            audioWorkletNode.connect(audioContext.destination); 
        };

        websocket.onmessage = (event) => {
            // Intercept binary TTS PCM stream from backend
            if (event.data instanceof ArrayBuffer) {
                playAudioChunk(event.data);
                return;
            }

            try {
                const data = JSON.parse(event.data);
                
                if (data.status === 'transcription') {
                    addServerMessage(`User: ${data.message}`);
                } else if (data.status === 'llm_start') {
                    const p = document.createElement('p');
                    p.id = 'current-llm-response';
                    p.style.color = "var(--secondary)";
                    p.textContent = `Nova: `;
                    serverMessages.appendChild(p);
                    serverMessages.scrollTop = serverMessages.scrollHeight;
                } else if (data.status === 'llm_token') {
                    const p = document.getElementById('current-llm-response');
                    if (p) {
                        p.textContent += data.message;
                        serverMessages.scrollTop = serverMessages.scrollHeight;
                    }
                } else if (data.status === 'llm_end') {
                    const p = document.getElementById('current-llm-response');
                    if (p) p.removeAttribute('id');
                } else {
                    addServerMessage(data.message);
                }
            } catch (e) {
                console.error("Failed to parse message:", event.data);
            }
        };

        websocket.onclose = () => stopConversation("Disconnected");
        websocket.onerror = () => stopConversation("Connection error");

    } catch (err) {
        console.error('Error starting conversation:', err);
        statusText.textContent = "Error: Could not access microphone.";
        statusText.style.color = "var(--danger)";
    }
});

stopBtn.addEventListener('click', () => {
    stopConversation("Session ended");
});

function stopConversation(reason = "Ready to connect") {
    // Clean up AudioContext
    if (audioContext && audioContext.state !== 'closed') {
        audioContext.close();
    }
    
    // Stop microphone tracks
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
    }

    // Close WebSocket
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.close();
    }

    // UI Updates
    statusText.textContent = reason;
    statusText.style.color = "var(--text-main)";
    startBtn.disabled = false;
    stopBtn.disabled = true;
    orbContainer.classList.remove('active');
    orb.classList.remove('active');
    
    if (reason !== "Ready to connect") {
        addServerMessage(`Connection closed: ${reason}`);
    }
}
