import pathlib
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from .task_registry import TaskCancelledError, task_registry

# Import from tts_client
from .tts_client import (
    get_available_gemini_voices,
    synthesize_speech_with_gemini,
    DEFAULT_TEMPERATURE_CONFIG,
    DEFAULT_API_TIMEOUT_SECONDS_CONFIG,
    DEFAULT_VOICE_DISPLAY_NAME_CONFIG,
    DEFAULT_CHUNK_SIZE_CHARS_CONFIG,
    APP_CONFIG
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Gemini TTS Server",
    description="FastAPI server for Google Gemini Text-to-Speech",
    version="1.0.0"
)

# Define base path for templates and static files
BASE_DIR = pathlib.Path(__file__).parent.resolve()

# Mount static files (CSS, JS)
# The path "static" here refers to a directory named "static" at the same level as this main.py file
STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

class SynthesizeRequest(BaseModel):
    task_id: str # Added: Unique ID for this synthesis task
    text: str
    voice_name: str
    audio_format: str 
    temperature: float = DEFAULT_TEMPERATURE_CONFIG
    style_prompt: Optional[str] = None 
    chunk_size_chars: int 
    api_timeout_seconds: Optional[int] = DEFAULT_API_TIMEOUT_SECONDS_CONFIG

@app.post("/api/cancel_task/{task_id}")
async def cancel_task(task_id: str):
    """Handles task cancellation requests."""
    logger.info(f"Received cancellation request for task_id: {task_id}")
    try:
        task_registry.cancel(task_id)
        return {"message": "Cancellation request processed", "task_id": task_id}
    except Exception as e:
        logger.error(f"Error cancelling task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to process cancellation request.")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serves the main HTML page."""
    return HTMLResponse(content=open(STATIC_DIR / "index.html").read())

@app.get("/api/config")
async def get_config():
    """
    Returns selected configuration values for the frontend.
    """
    return JSONResponse({
        "default_theme": APP_CONFIG.get("default_theme", "dark"),
        "default_style_prompt": APP_CONFIG.get("default_style_prompt", "Read aloud in a warm and friendly tone:"),
        "default_audio_format": APP_CONFIG.get("default_audio_format", "wav"),
        "default_temperature": APP_CONFIG.get("default_temperature", 1.0),
        "default_chunk_size_chars": APP_CONFIG.get("default_chunk_size_chars", 1500),
        "default_api_timeout_seconds": APP_CONFIG.get("default_api_timeout_seconds", 60),
        "default_voice_display_name": APP_CONFIG.get("default_voice_display_name", "Fenrir"),
        "default_max_text_chars": APP_CONFIG.get("default_max_text_chars", 20000),
        # Add more as needed
    })

@app.get("/api/voices")
async def list_voices_endpoint():
    """Lists all available Google TTS voices."""
    try:
        voices = get_available_gemini_voices()
        if not voices:
            raise HTTPException(status_code=404, detail="No voices found or error fetching voices.")
        return {
            "voices": voices,
            "default_voice": DEFAULT_VOICE_DISPLAY_NAME_CONFIG
        }
    except Exception as e:
        logger.error(f"Error in /api/voices: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error fetching voices: {str(e)}")

@app.post("/api/synthesize")
async def synthesize_speech_endpoint(request_data: SynthesizeRequest):
    """Synthesizes text to speech and returns audio stream."""
    if not request_data.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    # Register task with cancellation system
    if request_data.task_id:
        task_registry.register(request_data.task_id)
    if not request_data.voice_name:
        raise HTTPException(status_code=400, detail="Voice name must be provided.")
    
    if request_data.audio_format.lower() not in ["mp3", "wav", "flac"]:
        raise HTTPException(status_code=400, detail="Invalid audio format. Must be 'mp3', 'wav', or 'flac'.")

    try:
        final_text_to_synthesize = request_data.text
        if request_data.style_prompt and request_data.style_prompt.strip():
            # Prepend style prompt to the main text
            final_text_to_synthesize = f"{request_data.style_prompt.strip()} {request_data.text}"
            logger.info(f"Using style prompt: '{request_data.style_prompt.strip()}'")
        
        logger.info(f"Synthesize request: Combined Text='{final_text_to_synthesize[:100]}...', Voice='{request_data.voice_name}', Format='{request_data.audio_format}', Temp='{request_data.temperature}'")
        audio_content, mime_type = synthesize_speech_with_gemini(
            text=final_text_to_synthesize,
            voice_display_name=request_data.voice_name,
            audio_format=request_data.audio_format.lower(),
            temperature=request_data.temperature,
            chunk_size_chars=request_data.chunk_size_chars,
            api_timeout_seconds=request_data.api_timeout_seconds,
            task_id=request_data.task_id
        )

        if audio_content is None and not task_registry.is_cancelled(request_data.task_id):
            logger.warning("Synthesis resulted in no audio content")
            raise HTTPException(status_code=500, detail="Speech synthesis failed to produce audio.")
        
        logger.info(f"Synthesis successful. Returning audio data of type {mime_type}")
        headers = {
            'Content-Disposition': 'inline',
            'Content-Type': mime_type,
            'Cache-Control': 'no-cache',
            'Access-Control-Expose-Headers': 'Content-Disposition'
        }
        return Response(
            content=audio_content,
            media_type=mime_type,
            headers=headers
        )

    except TaskCancelledError as e:
        logger.info(f"Task cancellation processed: {str(e)}")
        raise HTTPException(status_code=499, detail=str(e))
        
    except Exception as e:
        logger.error(f"Error in /api/synthesize: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
        
    finally:
        # Ensure task is unregistered
        if request_data.task_id:
            task_registry.unregister(request_data.task_id)

