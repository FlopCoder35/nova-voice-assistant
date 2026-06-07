#!/usr/bin/env python3
"""
Demo Recording Script for Nova Voice Assistant
Records a sample conversation for submission
Run on JarvisLabs after all services are started
"""
import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

async def record_demo():
    """Record a sample healthcare triage conversation."""
    
    print("\n" + "="*70)
    print(" NOVA VOICE ASSISTANT - DEMO RECORDING")
    print("="*70)
    
    try:
        from chat.llm_service import LLMService
    except ImportError as e:
        print(f"❌ Error: Could not import LLMService: {e}")
        print("   Make sure you're running from the project root with venv activated")
        return None
    
    # Sample healthcare queries for demonstration
    demo_queries = [
        "I have had a severe headache and fever for the past 2 days. What should I do?",
        "Should I see a doctor immediately or can I wait?",
        "What type of doctor should I see for this?"
    ]
    
    llm_service = LLMService()
    conversation_history = []
    transcript = {
        "title": "Nova Voice Assistant - Healthcare Triage Demo",
        "timestamp": datetime.now().isoformat(),
        "use_case": "Healthcare Triage Assistant",
        "turns": []
    }
    
    print("\n📋 Recording Sample Conversation:\n")
    print("-" * 70)
    
    for turn_num, user_query in enumerate(demo_queries, 1):
        print(f"\n[Turn {turn_num}]")
        print(f"👤 User: {user_query}\n")
        
        transcript["turns"].append({
            "turn": turn_num,
            "speaker": "user",
            "text": user_query,
            "timestamp": datetime.now().isoformat()
        })
        
        # Get LLM response
        print("🤖 Nova: ", end="", flush=True)
        
        assistant_response = ""
        async for token in llm_service.stream_response(user_query, conversation_history):
            assistant_response += token
            print(token, end="", flush=True)
        
        print("\n")  # Newline after response
        
        transcript["turns"].append({
            "turn": turn_num,
            "speaker": "assistant",
            "text": assistant_response,
            "timestamp": datetime.now().isoformat()
        })
        
        await asyncio.sleep(0.5)  # Brief pause between turns
    
    # Save transcript
    transcript_file = Path(__file__).parent / "demo_transcript.json"
    with open(transcript_file, 'w') as f:
        json.dump(transcript, f, indent=2)
    
    # Print formatted transcript
    print("\n" + "="*70)
    print(" DEMO TRANSCRIPT")
    print("="*70 + "\n")
    
    for turn in transcript["turns"]:
        speaker = "👤 User" if turn["speaker"] == "user" else "🤖 Assistant"
        print(f"{speaker}:")
        print(f"  {turn['text']}\n")
    
    print("-" * 70)
    print(f"\n✅ Demo recorded and saved to: {transcript_file}\n")
    print("📝 For submission README, copy this conversation into:")
    print("   ## Sample Conversation\n")
    print("   ### Input Audio:")
    print('   "I have had a severe headache and fever for the past 2 days. What should I do?"\n')
    print("   ### Expected Output:")
    
    # Show the assistant's first response as sample output
    if transcript["turns"]:
        for turn in transcript["turns"]:
            if turn["speaker"] == "assistant" and turn["turn"] == 1:
                print(f'   "{turn["text"]}"')
                break
    
    print("\n" + "="*70 + "\n")
    return transcript

if __name__ == "__main__":
    print("\n⏳ Recording demo conversation... (this may take 1-2 minutes)\n")
    asyncio.run(record_demo())
