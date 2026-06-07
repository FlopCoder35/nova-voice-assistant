import re
import asyncio

try:
    import torch
    import numpy as np
    from transformers import VitsModel, AutoTokenizer
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("⚠️ TTS ML libraries not installed. TTS will not function locally.")

class VoxtralTTSModelLoader:
    """
    Singleton pattern for loading the TTS model into GPU VRAM once.
    """
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, model_id="kakao-enterprise/vits-ljs"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading TTS Model '{model_id}' on {self.device}...")
        
        # Load the TTS Model
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.model = VitsModel.from_pretrained(model_id).to(self.device)
        self.model.eval()
        print("TTS Model loaded successfully.")

class TTSService:
    def __init__(self):
        self.tts_engine = VoxtralTTSModelLoader.get_instance()
        self.target_sample_rate = 24000
        self.model_sample_rate = self.tts_engine.model.config.sampling_rate
        
        # Regex for splitting at sentence boundaries: (. ! ?) followed by space or newline
        self.sentence_pattern = re.compile(r'(?<=[.!?])[\s\n]+')

    async def stream_tts(self, llm_token_async_generator):
        """
        Consumes LLM tokens asynchronously, chunks them into sentences,
        and yields 24kHz 16-bit PCM binary audio for each complete sentence natively.
        """
        buffer = ""
        
        async for token in llm_token_async_generator:
            buffer += token
            
            # Check for sentence boundaries. We chunk the generation at punctuation
            # to ensure we yield audio immediately without waiting for the full LLM completion.
            if any(punct in buffer for punct in ['. ', '? ', '! ', '\n']):
                parts = self.sentence_pattern.split(buffer, maxsplit=1)
                
                if len(parts) > 1:
                    sentence = parts[0].strip()
                    buffer = parts[1] 
                    
                    if sentence:
                        # Offload native generation to background thread to prevent blocking the WS
                        audio_bytes = await asyncio.to_thread(self._generate_audio, sentence)
                        if audio_bytes:
                            yield audio_bytes

        # Process any trailing text when the LLM generator finally exhausts
        if buffer.strip():
            audio_bytes = await asyncio.to_thread(self._generate_audio, buffer.strip())
            if audio_bytes:
                yield audio_bytes

    def _generate_audio(self, text: str) -> bytes:
        """
        Synchronous inference method generating 24kHz 16-bit PCM.
        """
        inputs = self.tts_engine.tokenizer(text, return_tensors="pt").to(self.tts_engine.device)
        
        with torch.no_grad():
            output = self.tts_engine.model(**inputs).waveform
        
        # Extract audio waveform from the GPU tensor
        audio_float32 = output.cpu().numpy().squeeze()
        
        # Resample to 24kHz if the native model is different (e.g. VITS is often 22050Hz)
        if self.model_sample_rate != self.target_sample_rate:
            duration = len(audio_float32) / self.model_sample_rate
            new_length = int(duration * self.target_sample_rate)
            audio_float32 = np.interp(
                np.linspace(0.0, 1.0, new_length),
                np.linspace(0.0, 1.0, len(audio_float32)),
                audio_float32
            )

        # Normalize and convert float32 [-1.0, 1.0] to 16-bit PCM
        audio_float32 = np.clip(audio_float32, -1.0, 1.0)
        audio_int16 = (audio_float32 * 32767).astype(np.int16)
        
        return audio_int16.tobytes()
