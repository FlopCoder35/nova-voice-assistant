#!/usr/bin/env python3
"""
Latency Measurement Script for Nova Voice Assistant
Measures end-to-end and per-stage latency for submission
Run on JarvisLabs after all services are started
"""
import asyncio
import time
import sys
import os
import json
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

async def measure_latency():
    """Measure end-to-end and per-stage latency."""
    
    print("\n" + "="*70)
    print(" NOVA VOICE ASSISTANT - LATENCY MEASUREMENT TEST")
    print("="*70)
    
    try:
        # Import services
        from chat.asr_service import AudioSession
        from chat.llm_service import LLMService
        from chat.tts_service import TTSService
        import numpy as np
    except ImportError as e:
        print(f"❌ Error: Could not import required modules: {e}")
        print("   Make sure you're running from the project root with venv activated")
        return None
    
    metrics = {}
    
    # ========== STAGE 1: ASR ==========
    print("\n[Stage 1/3] ASR (Speech-to-Text Latency)")
    print("-" * 70)
    
    try:
        asr_service = AudioSession()
        
        # Create sample audio (1 second silence at 16kHz, 16-bit PCM)
        sample_rate = 16000
        duration = 1
        silence_samples = np.zeros(sample_rate * duration, dtype=np.int16)
        
        print("  • Pushing 1 second of audio to ASR...")
        start_asr = time.time()
        asr_service.push_chunk(silence_samples.tobytes())
        
        print("  • Waiting for transcription...")
        asr_text = ""
        async for transcribed_text in asr_service.transcribe_stream():
            asr_text = transcribed_text
            break  # Take first result
        
        asr_latency_ms = (time.time() - start_asr) * 1000
        metrics['microphone_to_asr'] = f"{asr_latency_ms:.0f}"
        
        print(f"  ✅ ASR Latency: {asr_latency_ms:.2f} ms")
        print(f"     Transcribed: '{asr_text}'")
        
    except Exception as e:
        print(f"  ❌ ASR Error: {e}")
        return None
    
    # ========== STAGE 2: LLM ==========
    print("\n[Stage 2/3] LLM (Reasoning Latency)")
    print("-" * 70)
    
    try:
        llm_service = LLMService()
        conversation_history = []
        
        test_query = "What is a healthcare triage?"
        print(f"  • Query: '{test_query}'")
        print("  • Streaming LLM tokens...")
        
        start_llm = time.time()
        first_token_time = None
        token_count = 0
        llm_response = ""
        
        async for token in llm_service.stream_response(test_query, conversation_history):
            token_count += 1
            llm_response += token
            
            if first_token_time is None:
                first_token_time = (time.time() - start_llm) * 1000
                print(f"  ✅ Time to First Token: {first_token_time:.2f} ms")
        
        total_llm_latency = (time.time() - start_llm) * 1000
        metrics['asr_to_first_llm_token'] = f"{first_token_time:.0f}"
        
        print(f"  ✅ Total LLM Processing: {total_llm_latency:.2f} ms")
        print(f"     Tokens: {token_count}")
        print(f"     Response: '{llm_response[:80]}...'")
        
    except Exception as e:
        print(f"  ❌ LLM Error: {e}")
        print("     Make sure vLLM server is running (./start_vllm.sh)")
        return None
    
    # ========== STAGE 3: TTS ==========
    print("\n[Stage 3/3] TTS (Text-to-Speech Latency)")
    print("-" * 70)
    
    try:
        tts_service = TTSService()
        
        print(f"  • Input text: '{llm_response[:60]}...'")
        print("  • Generating TTS audio...")
        
        async def token_generator():
            """Generator to yield tokens from LLM response"""
            for char in llm_response:
                yield char
            yield "\n"  # Signal end
        
        start_tts = time.time()
        first_audio_chunk_time = None
        chunk_count = 0
        total_audio_bytes = 0
        
        async for audio_chunk in tts_service.stream_tts(token_generator()):
            chunk_count += 1
            total_audio_bytes += len(audio_chunk)
            
            if first_audio_chunk_time is None:
                first_audio_chunk_time = (time.time() - start_tts) * 1000
                print(f"  ✅ Time to First Audio Chunk: {first_audio_chunk_time:.2f} ms")
        
        total_tts_latency = (time.time() - start_tts) * 1000
        metrics['first_llm_token_to_first_audio'] = f"{first_audio_chunk_time:.0f}"
        
        duration_seconds = total_audio_bytes / (24000 * 2)  # 24kHz, 16-bit stereo
        print(f"  ✅ Total TTS Generation: {total_tts_latency:.2f} ms")
        print(f"     Audio Chunks: {chunk_count}")
        print(f"     Total Bytes: {total_audio_bytes:,}")
        print(f"     Duration: {duration_seconds:.2f}s")
        
    except Exception as e:
        print(f"  ❌ TTS Error: {e}")
        return None
    
    # ========== SUMMARY ==========
    print("\n" + "="*70)
    print(" LATENCY SUMMARY")
    print("="*70)
    
    end_to_end = (asr_latency_ms + total_llm_latency + total_tts_latency)
    metrics['end_to_end'] = f"{end_to_end:.0f}"
    
    print(f"\n┌─ Stage 1: Microphone to ASR")
    print(f"│  {asr_latency_ms:>6.2f} ms")
    print(f"├─ Stage 2: ASR to First LLM Token")
    print(f"│  {first_token_time:>6.2f} ms")
    print(f"├─ Stage 3: First LLM Token to First Audio")
    print(f"│  {first_audio_chunk_time:>6.2f} ms")
    print(f"└─ Total: End-to-End Latency")
    print(f"   {end_to_end:>6.2f} ms")
    
    # Quality assessment
    print("\n" + "-"*70)
    if end_to_end < 800:
        quality = "🟢 EXCELLENT (Natural conversation)"
    elif end_to_end < 1200:
        quality = "🟡 GOOD (Acceptable latency)"
    elif end_to_end < 2000:
        quality = "🟠 FAIR (Noticeable but manageable)"
    else:
        quality = "🔴 POOR (Jarring latency)"
    
    print(f"Conversational Quality: {quality}")
    print("-"*70)
    
    # Save metrics to JSON
    metrics_file = Path(__file__).parent / "latency_metrics.json"
    with open(metrics_file, 'w') as f:
        json.dump(metrics, f, indent=2)
    
    print(f"\n✅ Metrics saved to: {metrics_file}")
    print("\nUpdate README.md with these values:")
    print(f"  Microphone to ASR: {metrics['microphone_to_asr']} ms")
    print(f"  ASR to First LLM Token: {metrics['asr_to_first_llm_token']} ms")
    print(f"  First Token to First Audio: {metrics['first_llm_token_to_first_audio']} ms")
    print(f"  End-to-End: {metrics['end_to_end']} ms")
    
    print("\n" + "="*70 + "\n")
    return metrics

if __name__ == "__main__":
    print("\n⏳ Starting latency measurement... (this may take 1-2 minutes)\n")
    asyncio.run(measure_latency())
