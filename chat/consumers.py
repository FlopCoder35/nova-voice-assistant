import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from .asr_service import AudioSession
from .llm_service import LLMService
from .tts_service import TTSService

class AudioConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        print("WebSocket connection accepted.")
        
        # Initialize instances for this specific session
        self.audio_session = AudioSession()
        self.llm_service = LLMService()
        self.tts_service = TTSService()
        self.conversation_history = []
        
        # Concurrency Queues to decouple the pipeline stages
        self.asr_to_llm_queue = asyncio.Queue()
        self.llm_to_tts_queue = asyncio.Queue()
        
        # Launch independent, non-blocking pipeline workers
        self.pipeline_tasks = [
            asyncio.create_task(self.asr_worker()),
            asyncio.create_task(self.llm_worker()),
            asyncio.create_task(self.tts_worker())
        ]

    async def disconnect(self, close_code):
        # Clean up tasks on disconnect
        for task in self.pipeline_tasks:
            task.cancel()
        print(f"WebSocket disconnected with code: {close_code}")

    async def receive(self, text_data=None, bytes_data=None):
        """
        Ingest continuous binary chunks from the frontend directly into the ASR buffer.
        """
        if bytes_data:
            self.audio_session.push_chunk(bytes_data)
        elif text_data:
            print(f"Received text data: {text_data}")

    async def asr_worker(self):
        """
        Stage 1: Constantly polls the ASR generator. 
        When text is transcribed, it passes it to the frontend and queues it for the LLM.
        """
        try:
            async for text in self.audio_session.transcribe_stream():
                # Emit to frontend
                await self.send(text_data=json.dumps({
                    'status': 'transcription',
                    'message': text
                }))
                # Pipe into Stage 2 (LLM)
                await self.asr_to_llm_queue.put(text)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"ASR Worker Error: {e}")

    async def llm_worker(self):
        """
        Stage 2: Waits for transcribed sentences, queries the LLM, 
        and streams tokens into the TTS queue concurrently.
        """
        try:
            while True:
                # Wait for the next transcribed utterance
                text = await self.asr_to_llm_queue.get()
                
                await self.send(text_data=json.dumps({
                    'status': 'llm_start',
                    'message': ''
                }))
                
                # Stream the LLM response asynchronously
                async for token in self.llm_service.stream_response(text, self.conversation_history):
                    # Broadcast to UI
                    await self.send(text_data=json.dumps({
                        'status': 'llm_token',
                        'message': token
                    }))
                    # Pipe into Stage 3 (TTS)
                    await self.llm_to_tts_queue.put(token)
                
                await self.send(text_data=json.dumps({
                    'status': 'llm_end',
                    'message': ''
                }))
                
                # Push a None value to signal the end of the LLM's response
                await self.llm_to_tts_queue.put(None)
                self.asr_to_llm_queue.task_done()
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"LLM Worker Error: {e}")

    async def tts_worker(self):
        """
        Stage 3: Consumes tokens from the LLM, buffers them until sentence boundaries,
        generates TTS audio natively, and streams binary PCM bytes back to the frontend.
        """
        try:
            # We adapt the queue into an async generator required by the TTS service
            async def queue_to_generator():
                while True:
                    token = await self.llm_to_tts_queue.get()
                    if token is None:
                        # Force flush the final TTS sentence by injecting a newline
                        yield "\n"
                    else:
                        yield token
                    self.llm_to_tts_queue.task_done()

            # The stream_tts method intercepts complete sentences and yields audio bytes
            async for audio_chunk in self.tts_service.stream_tts(queue_to_generator()):
                # Stream the binary 24kHz PCM directly to the browser
                await self.send(bytes_data=audio_chunk)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"TTS Worker Error: {e}")
