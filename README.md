# Nova: Open-Source Real-Time Voice Assistant

[![Demo Video](PLACEHOLDER_LINK_TO_DEMO_VIDEO)](PLACEHOLDER_LINK_TO_DEMO_VIDEO)

## What it does
Nova is an ultra-low-latency, real-time Healthcare Triage Voice Assistant built entirely on open-source weights. Designed to alleviate frontline medical bottlenecks, it acts as a conversational first point of contact for patients. 

Patients can verbally describe their symptoms to Nova naturally. It provides brief, empathetic, purely informational health advice and explicitly recommends the specific medical specialist they should consult (e.g., Dermatologist, ENT). It streams audio continuously, so if a patient interrupts to clarify a symptom, the local client instantly detects their voice and stops the assistant from talking over them.

## Why I built this
The current ecosystem of voice assistants (like Siri or basic smart speakers) suffers from jarring turn-taking latency. This latency breaks the illusion of natural conversation. I wanted to build a proof-of-concept that demonstrates how modern open-source models, when coupled with aggressive pipelining and low-level Web Audio API scheduling, can achieve conversational fluidity previously only seen in proprietary, closed-source models.

## How to run it
This system is designed to be deployed on an Ubuntu-based GPU instance with at least 16GB of VRAM (e.g., JarvisLabs).

### 1. Environment Setup
Clone the repository and install the dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Secrets (.env)
We use `python-decouple` to securely handle API keys and instance configurations. Copy the template and create a `.env` file:
```bash
cp .env.template .env
```
Then edit `.env` with your actual values:
```env
DJANGO_SECRET_KEY=your_local_secret_key_change_in_production
DJANGO_DEBUG=True
JARVISLABS_API_KEY=your_secret_api_key_here
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
```
**Important:** `.env` is in `.gitignore` and will never be committed to Git. The template (`.env.template`) is tracked for documentation only.
When Daphne boots, `settings.py` safely pulls this key from the environment (and logs a masked verification), ensuring it is never exposed to Git while still allowing full management of the JarvisLabs GPU instance.

### 3. Backing Store (Redis)
Django Channels requires Redis for its channel layer. On Ubuntu/JarvisLabs:
```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server
```

### 4. Spin up the Reasoning Engine (vLLM)
Start the local vLLM API server to host the reasoning model in the background:
```bash
chmod +x start_vllm.sh
./start_vllm.sh &
```

### 5. Start the Application
Run database migrations and start Daphne (the ASGI server) on port 8000:
```bash
python manage.py migrate
daphne -b 0.0.0.0 -p 8000 VoiceAssistantApp.asgi:application
```
Visit `http://<your-jarvislabs-ip>:8000` to interact with the assistant.

## Architecture Decisions

* **Django Channels & WebSockets (Latency Handling):** Standard HTTP requests cause jarring delays in voice applications. We used Django Channels to establish a persistent bidirectional WebSocket. By aggressively decoupling our processing stages using parallel `asyncio` background tasks and `asyncio.Queue`s, we built a non-blocking pipeline. The ASR task ingests 100ms micro-chunks, the LLM task streams response tokens as they generate, and the TTS task intercepts those tokens at sentence boundaries to immediately stream 24kHz PCM audio back to the client. This concurrent architecture ensures no stage waits for another to finish, resulting in near-zero perceived latency.
* **Voxtral Mini 4B Realtime (ASR):** This model was selected for its native streaming capabilities. Running on `float16` via `transformers` with a rolling 400ms buffer allows us to trigger continuous partial transcriptions without blowing up GPU memory.
* **gpt-oss-20b (MXFP4):** To run a highly competent 20B reasoning model on a single 16GB GPU, we utilized MXFP4 quantization. Served via `vLLM`, it provides aggressive continuous batching and SSE token streaming, generating thoughts faster than a human can speak.
* **Client-Side VAD (Interruption):** Rather than waiting for the backend ASR to realize the user interrupted, we implemented native RMS volume metering inside the browser's `AudioWorkletProcessor`. This instantly halts the Web Audio playback queue locally.

## Latency Metrics
* **Microphone to ASR Yield (Stage 1):** `[PLACEHOLDER_METRIC]` ms
* **ASR to First LLM Token (Stage 2):** `[PLACEHOLDER_METRIC]` ms
* **First Token to First Audio Chunk (Stage 3):** `[PLACEHOLDER_METRIC]` ms
* **End-to-End Latency:** `[PLACEHOLDER_METRIC]` ms

## What I used AI for
During this project, AI (via an agentic coding assistant) was heavily utilized for:
* Scaffolding the initial Django Channels architecture and ASGI configurations.
* Writing the complex asynchronous generator pipelines (`asyncio.Queue`, decoupling tasks).
* Structuring the low-level Web Audio API components (`AudioWorkletProcessor`, Float32 to 16-bit PCM array conversions).
* Implementing the CSS styling for the glassmorphism UI and dynamic pulsing animations.

## What I would change with 4 more weeks
1. **True Audio-to-Audio LLM:** Skip the ASR->LLM->TTS pipeline entirely by fine-tuning an audio-native multimodal model that directly predicts semantic audio tokens, slashing end-to-end latency.
2. **Turn-Taking Heuristics:** Implement a smarter local VAD (like Silero) combined with prosody detection so the assistant knows the difference between a natural pause and the end of a thought.
3. **Containerization & K8s:** Package the decoupled services (ASR, LLM, TTS) into separate Docker containers to scale them independently using Kubernetes depending on load.
