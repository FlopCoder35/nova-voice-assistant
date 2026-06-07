import asyncio

try:
    import numpy as np
    import torch
    from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("⚠️ ASR ML libraries not installed. ASR will not function locally.")

class VoxtralASRModelLoader:
    """
    Singleton pattern to load the 4B model only once into GPU memory.
    Ensures multiple WebSocket connections share the same underlying model.
    """
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, model_id="mistralai/Voxtral-Mini-4B-Realtime"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading ASR Model '{model_id}' on {self.device}...")
        
        self.processor = AutoProcessor.from_pretrained(model_id)
        
        # Load in float16 to save GPU VRAM and maximize inference speed
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_id, 
            torch_dtype=dtype,
            low_cpu_mem_usage=True
        ).to(self.device)
        self.model.eval()
        print("ASR Model loaded successfully.")

class AudioSession:
    """
    Manages the audio buffer and streaming transcription for a single connection.
    """
    def __init__(self):
        self.asr_engine = VoxtralASRModelLoader.get_instance()
        self.sample_rate = 16000
        self.audio_buffer = np.array([], dtype=np.float32)
        
        # Optimize for minimal latency: Trigger inference when we have exactly 100ms of new audio
        self.process_threshold_samples = int(self.sample_rate * 0.1) 
        
        # Maintain history up to 2.5 seconds for context
        self.context_window_samples = int(self.sample_rate * 2.5)

    def push_chunk(self, pcm_bytes: bytes):
        """
        Accepts binary audio chunks (16kHz, 16-bit PCM), converts and stores them.
        """
        chunk_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        chunk_float32 = chunk_int16.astype(np.float32) / 32768.0
        
        self.audio_buffer = np.concatenate((self.audio_buffer, chunk_float32))
        
        # Slide the window if we exceed context size to avoid infinite memory growth
        if len(self.audio_buffer) > self.context_window_samples:
            self.audio_buffer = self.audio_buffer[-self.context_window_samples:]

    async def transcribe_stream(self):
        """
        Async generator that yields transcribed text iteratively.
        """
        last_processed_length = 0
        
        while True:
            current_length = len(self.audio_buffer)
            new_audio_length = current_length - last_processed_length
            
            if new_audio_length >= self.process_threshold_samples:
                # We have enough new audio to run a forward pass
                audio_to_process = self.audio_buffer.copy()
                last_processed_length = len(audio_to_process)
                
                # Execute heavy GPU inference in a background thread to keep event loop free
                text = await asyncio.to_thread(self._infer, audio_to_process)
                
                if text and text.strip():
                    yield text
            else:
                # Brief sleep to yield control to event loop
                await asyncio.sleep(0.02)

    def _infer(self, audio_array):
        """
        Synchronous inference method.
        """
        inputs = self.asr_engine.processor(
            audio_array, 
            sampling_rate=self.sample_rate, 
            return_tensors="pt"
        )
        dtype = torch.float16 if self.asr_engine.device == "cuda" else torch.float32
        input_features = inputs.input_features.to(self.asr_engine.device, dtype=dtype)

        with torch.no_grad():
            predicted_ids = self.asr_engine.model.generate(
                input_features,
                max_new_tokens=48,
                num_beams=1,      # Greedy search for absolute lowest latency
                do_sample=False,  # Deterministic
                use_cache=True    # Accelerate decoding
            )
        
        transcription = self.asr_engine.processor.batch_decode(
            predicted_ids, skip_special_tokens=True
        )[0]
        return transcription
