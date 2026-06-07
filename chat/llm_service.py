import json

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("⚠️ aiohttp not installed. LLM service will not function locally.")

class LLMService:
    def __init__(self, endpoint="http://127.0.0.1:8001/v1/chat/completions"):
        self.endpoint = endpoint
        self.system_prompt = (
            "You are an empathetic, concise Healthcare Triage Assistant. "
            "Your goal is to provide purely informational health advice based on the symptoms provided. "
            "You MUST ALWAYS include a short, natural disclaimer stating you are an AI and not a doctor. "
            "You MUST explicitly analyze the symptoms and recommend the specific type of medical specialist they should consult (e.g., Dermatologist, ENT, General Practitioner). "
            "Keep your responses brief (2-4 sentences maximum) so they can be spoken quickly by a TTS engine. "
            "Do not use markdown or special formatting; speak conversationally and empathetically."
        )

    async def stream_response(self, text: str, conversation_history: list):
        """
        Appends user text to history, queries the local vLLM server,
        and yields tokens as they are generated.
        """
        conversation_history.append({"role": "user", "content": text})
        
        messages = [{"role": "system", "content": self.system_prompt}] + conversation_history
        
        payload = {
            "model": "openai/gpt-oss-20b",
            "messages": messages,
            "stream": True,
            "max_tokens": 150,  # Cap at 150 for brief TTS friendly responses
            "temperature": 0.2, # Low temperature for accurate, factual CS logic
        }

        assistant_response = ""

        async with aiohttp.ClientSession() as session:
            try:
                # Post to the local vLLM OpenAI-compatible endpoint
                async with session.post(self.endpoint, json=payload, timeout=60) as response:
                    if response.status != 200:
                        yield "I am currently unable to access my reasoning engine."
                        return

                    # Iterate over the streaming chunks
                    async for line in response.content:
                        line = line.decode('utf-8').strip()
                        if line.startswith("data: ") and line != "data: [DONE]":
                            try:
                                data = json.loads(line[6:])
                                if 'choices' in data and len(data['choices']) > 0:
                                    content = data['choices'][0].get('delta', {}).get('content', '')
                                    if content:
                                        assistant_response += content
                                        yield content
                            except json.JSONDecodeError:
                                pass
            except aiohttp.ClientError:
                yield "My reasoning engine is offline. Please start the vLLM server."

        # Save the complete response to history for context in the next turn
        if assistant_response:
            conversation_history.append({"role": "assistant", "content": assistant_response})
