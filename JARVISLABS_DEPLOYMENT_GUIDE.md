# JarvisLabs Deployment & Submission Guide

## Phase 1: JarvisLabs Instance Setup

### Step 1: Create GPU Instance on JarvisLabs
1. Go to [jarvislabs.ai](https://jarvislabs.ai)
2. Create account or log in
3. Click **"Create Instance"**
4. Select:
   - **Framework**: PyTorch
   - **GPU**: NVIDIA A100 40GB or RTX 4090 (must have 16GB+ VRAM)
   - **Storage**: 100GB minimum
   - **Base Image**: Ubuntu 22.04 (with CUDA pre-installed)
5. Launch instance and note the SSH connection details

### Step 2: SSH into Instance
```bash
ssh -i /path/to/key.pem ubuntu@<jarvislabs-ip>
```

### Step 3: Clone Your GitHub Repository
```bash
cd /home/ubuntu
git clone https://github.com/FlopCoder35/nova-voice-assistant.git
cd nova-voice-assistant
```

---

## Phase 2: Environment Setup on JarvisLabs

### Step 1: Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install vllm  # For the reasoning engine
```

### Step 3: Create `.env` File with Production Values
```bash
cp .env.template .env
nano .env
```

Edit `.env` with:
```env
DJANGO_SECRET_KEY=your_production_secret_key_here_change_this_now
DJANGO_DEBUG=False
JARVISLABS_API_KEY=your_api_key_here
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
VLLM_HOST=127.0.0.1
VLLM_PORT=8001
DAPHNE_BIND_ADDRESS=0.0.0.0
DAPHNE_PORT=8000
```

### Step 4: Install Redis
```bash
sudo apt update
sudo apt install redis-server -y
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

Verify Redis is running:
```bash
redis-cli ping
# Should return: PONG
```

---

## Phase 3: Download & Cache Models

This step pre-downloads models to avoid delays during runtime.

### Step 1: Download ASR Model (Voxtral Mini 4B)
```bash
python3 << 'EOF'
from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq
import torch

print("Downloading Voxtral Mini 4B ASR model...")
model_id = "mistralai/Voxtral-Mini-4B-Realtime"
processor = AutoProcessor.from_pretrained(model_id)
dtype = torch.float16
model = AutoModelForSpeechSeq2Seq.from_pretrained(
    model_id, 
    torch_dtype=dtype,
    low_cpu_mem_usage=True
)
print("✅ ASR model cached successfully")
EOF
```

### Step 2: Download LLM Model (gpt-oss-20b)
```bash
python3 << 'EOF'
from vllm import LLM
print("Downloading gpt-oss-20b model (this will take 5-10 minutes)...")
llm = LLM(
    model="openai/gpt-oss-20b",
    quantization="mxfp4",
    tensor_parallel_size=1,
    max_model_len=4096
)
print("✅ LLM model cached successfully")
EOF
```

### Step 3: Download TTS Model (VITS)
```bash
python3 << 'EOF'
from transformers import VitsModel, AutoTokenizer
print("Downloading VITS TTS model...")
model_id = "kakao-enterprise/vits-ljs"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = VitsModel.from_pretrained(model_id)
print("✅ TTS model cached successfully")
EOF
```

---

## Phase 4: Start Services (3 Terminal Windows)

### Terminal 1: Start Redis (if not already running)
```bash
redis-server
```

### Terminal 2: Start vLLM API Server
```bash
cd /home/ubuntu/nova-voice-assistant
source venv/bin/activate
./start_vllm.sh
```

Expected output:
```
INFO:     Started server process [PID]
INFO:     Uvicorn running on http://127.0.0.1:8001
```

### Terminal 3: Start Django Channels Server
```bash
cd /home/ubuntu/nova-voice-assistant
source venv/bin/activate
python manage.py migrate
daphne -b 0.0.0.0 -p 8000 VoiceAssistantApp.asgi:application
```

Expected output:
```
2026-06-07 12:34:56,789 daphne.server INFO Listening on TCP port 8000
```

---

## Phase 5: Test Deployment

### Verify All Services are Running
```bash
# Check Redis
redis-cli ping  # Should return: PONG

# Check vLLM (from a new terminal)
curl http://127.0.0.1:8001/v1/models

# Check Django (from a new terminal)
curl http://127.0.0.1:8000/
```

### Access Web Interface
Open in your browser:
```
http://<jarvislabs-ip>:8000
```

You should see the Nova Voice interface with the breathing orb animation.

---

## Phase 6: Measure Latency Metrics

Create a latency measurement script:

```bash
cat > measure_latency.py << 'EOF'
import asyncio
import time
import numpy as np
import json
from chat.asr_service import AudioSession
from chat.llm_service import LLMService
from chat.tts_service import TTSService

async def measure_latency():
    """
    Measure end-to-end and per-stage latency.
    """
    # Create a sample audio (2 seconds of silence at 16kHz)
    sample_rate = 16000
    duration = 2  # seconds
    silence = np.zeros(sample_rate * duration, dtype=np.int16)
    
    print("=" * 60)
    print("LATENCY MEASUREMENT TEST")
    print("=" * 60)
    
    # Stage 1: ASR
    print("\n[Stage 1] ASR (Speech to Text)")
    asr_service = AudioSession()
    start_asr = time.time()
    asr_service.push_chunk(silence.tobytes())
    text = ""
    async for transcribed in asr_service.transcribe_stream():
        text = transcribed
        break
    asr_latency = (time.time() - start_asr) * 1000
    print(f"  ASR Latency: {asr_latency:.2f} ms")
    
    # Stage 2: LLM
    print("\n[Stage 2] LLM (Reasoning)")
    llm_service = LLMService()
    conversation_history = []
    start_llm = time.time()
    llm_tokens = []
    async for token in llm_service.stream_response("What is healthcare?", conversation_history):
        llm_tokens.append(token)
        if len(llm_tokens) == 1:
            first_token_time = (time.time() - start_llm) * 1000
            print(f"  Time to First Token: {first_token_time:.2f} ms")
    total_llm_latency = (time.time() - start_llm) * 1000
    print(f"  Total LLM Latency: {total_llm_latency:.2f} ms")
    
    # Stage 3: TTS
    print("\n[Stage 3] TTS (Text to Speech)")
    tts_service = TTSService()
    start_tts = time.time()
    
    async def token_generator():
        for token in llm_tokens:
            yield token
        yield "\n"
    
    tts_chunks = 0
    async for audio_chunk in tts_service.stream_tts(token_generator()):
        if tts_chunks == 0:
            first_audio_time = (time.time() - start_tts) * 1000
            print(f"  Time to First Audio Chunk: {first_audio_time:.2f} ms")
        tts_chunks += 1
    total_tts_latency = (time.time() - start_tts) * 1000
    print(f"  Total TTS Latency: {total_tts_latency:.2f} ms")
    
    # End-to-End
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    end_to_end = asr_latency + total_llm_latency + total_tts_latency
    print(f"Stage 1 (ASR):          {asr_latency:.2f} ms")
    print(f"Stage 2 (LLM):          {total_llm_latency:.2f} ms")
    print(f"  └─ First Token:       {first_token_time:.2f} ms")
    print(f"Stage 3 (TTS):          {total_tts_latency:.2f} ms")
    print(f"  └─ First Audio:       {first_audio_time:.2f} ms")
    print(f"\nEnd-to-End Latency:    {end_to_end:.2f} ms")
    print(f"Conversational Speed:  {'✅ NATURAL' if end_to_end < 1500 else '⚠️ SLOW'}")
    print("=" * 60)
    
    # Save metrics
    metrics = {
        "microphone_to_asr": f"{asr_latency:.0f}",
        "asr_to_first_llm_token": f"{first_token_time:.0f}",
        "first_llm_token_to_first_audio": f"{first_audio_time:.0f}",
        "end_to_end": f"{end_to_end:.0f}"
    }
    
    with open("latency_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    
    print("\n✅ Metrics saved to latency_metrics.json")
    return metrics

if __name__ == "__main__":
    asyncio.run(measure_latency())
EOF

python measure_latency.py
```

---

## Phase 7: Record Demo Audio & Transcript

### Create Demo Recording Script
```bash
cat > record_demo.py << 'EOF'
import asyncio
import json
from datetime import datetime
from chat.asr_service import AudioSession
from chat.llm_service import LLMService
from chat.tts_service import TTSService

async def record_demo():
    """
    Simulate a complete conversation and record transcript.
    """
    print("🎙️ Recording demo conversation...\n")
    
    # Simulated user input
    user_queries = [
        "I have a persistent headache and sensitivity to light for the past 3 days.",
        "Should I see a doctor?"
    ]
    
    transcript = {
        "timestamp": datetime.now().isoformat(),
        "conversation": []
    }
    
    llm_service = LLMService()
    tts_service = TTSService()
    conversation_history = []
    
    for i, query in enumerate(user_queries, 1):
        print(f"[Turn {i}]")
        print(f"👤 User: {query}\n")
        
        transcript["conversation"].append({
            "speaker": "user",
            "text": query,
            "timestamp": datetime.now().isoformat()
        })
        
        # Get LLM response
        llm_response = ""
        first_token_time = None
        start_time = None
        
        async for token in llm_service.stream_response(query, conversation_history):
            if start_time is None:
                start_time = datetime.now()
                first_token_time = 0
            llm_response += token
        
        print(f"🤖 Nova: {llm_response}\n")
        
        transcript["conversation"].append({
            "speaker": "assistant",
            "text": llm_response,
            "timestamp": datetime.now().isoformat()
        })
        
        # Generate TTS (we won't actually play it, just verify it works)
        async def token_gen():
            for char in llm_response:
                yield char
            yield "\n"
        
        audio_generated = False
        async for audio_chunk in tts_service.stream_tts(token_gen()):
            audio_generated = True
            break  # Just verify first chunk
        
        if audio_generated:
            print("✅ Audio generated successfully\n")
        
        await asyncio.sleep(0.1)
    
    # Save transcript
    with open("demo_transcript.json", "w") as f:
        json.dump(transcript, f, indent=2)
    
    print("\n✅ Demo transcript saved to demo_transcript.json")
    print("\n📄 Full Conversation:")
    print(json.dumps(transcript, indent=2))

if __name__ == "__main__":
    asyncio.run(record_demo())
EOF

python record_demo.py
```

---

## Phase 8: Update README with Actual Values

After collecting metrics and demo, update your README:

```bash
# Copy the latency_metrics.json and demo_transcript.json values
cat latency_metrics.json
cat demo_transcript.json
```

Then update the README.md on GitHub with:
1. Replace `[PLACEHOLDER_METRIC]` with actual values from `latency_metrics.json`
2. Add demo transcript under "## Demo" section
3. Add JarvisLabs deployment link

---

## Phase 9: Make Application Public

### Configure for Public Access
Edit `.env`:
```env
DJANGO_DEBUG=False
ALLOWED_HOSTS=*  # Or specify your JarvisLabs domain
```

### Generate Strong Secret Key
```bash
python3 << 'EOF'
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
EOF
```

Update `DJANGO_SECRET_KEY` in `.env` with this value.

### Restart Services
```bash
# Terminal 2 (vLLM)
pkill -f vllm
./start_vllm.sh &

# Terminal 3 (Django)
pkill -f daphne
daphne -b 0.0.0.0 -p 8000 VoiceAssistantApp.asgi:application
```

---

## Phase 10: Final Submission Checklist

- [ ] GitHub repo is public
- [ ] README has all sections filled:
  - [ ] "What it does" (2-3 sentences)
  - [ ] "Why I built this" (1 paragraph)
  - [ ] "How to run it" (complete with JarvisLabs steps)
  - [ ] "Architecture decisions" (each decision with rationale)
  - [ ] "What I used AI for" (specific components)
  - [ ] "What I would change with 4 more weeks"
- [ ] Latency metrics filled in (actual numbers, not placeholders)
- [ ] Demo link works: `http://<jarvislabs-ip>:8000`
- [ ] Sample audio + transcript provided
- [ ] `.env` is in `.gitignore` (no secrets in repo)
- [ ] `requirements.txt` has all dependencies
- [ ] `start_vllm.sh` is executable

---

## Quick Reference: All 3 Terminal Commands

```bash
# Terminal 1: Redis
redis-server

# Terminal 2: vLLM
cd ~/nova-voice-assistant && source venv/bin/activate && ./start_vllm.sh

# Terminal 3: Django Channels
cd ~/nova-voice-assistant && source venv/bin/activate && daphne -b 0.0.0.0 -p 8000 VoiceAssistantApp.asgi:application
```

After all services start:
- **Web Interface**: http://<jarvislabs-ip>:8000
- **vLLM API**: http://<jarvislabs-ip>:8001/v1/models

---

## Troubleshooting

**Models are slow to download:**
- Pre-download during off-peak hours
- Use larger instance (A100 80GB)

**Out of VRAM:**
- Ensure MXFP4 quantization is enabled in `start_vllm.sh`
- Reduce `max_model_len` from 4096 to 2048

**Latency too high:**
- Check GPU utilization: `nvidia-smi`
- Verify all services are running on same GPU
- Use `float16` instead of `float32`

**WebSocket connection fails:**
- Verify Redis is running: `redis-cli ping`
- Check firewall allows port 8000
- Ensure DJANGO_DEBUG=False for production

---

**Questions?** Check the GitHub repo README or email support@jarvislabs.ai
