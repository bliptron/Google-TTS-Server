import os
import json
import logging
import base64
import requests
import io
from pathlib import Path
from pydub import AudioSegment
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv
import time
import toml
from .task_registry import task_registry, TaskCancelledError

# Configure logger
logger = logging.getLogger(__name__)

# --- Application Configuration Loading ---
CONFIG_FILE_PATH = Path(__file__).parent.parent / 'config.toml'
def _get_hardcoded_defaults():
    """Fallback defaults when config.toml is missing"""
    return {
        "server_host": "127.0.0.1"  # Safer default than 0.0.0.0
    }

def load_app_config() -> Dict:
    hardcoded_defaults = _get_hardcoded_defaults()
    try:
        with open(CONFIG_FILE_PATH, 'r') as f:
            config_data = toml.load(f)
        for key, value in hardcoded_defaults.items():
            config_data.setdefault(key, value)
        logger.info(f"Successfully loaded configuration from {CONFIG_FILE_PATH}")
        return config_data
    except FileNotFoundError:
        logger.warning(f"Config file {CONFIG_FILE_PATH} not found. Using defaults.")
        return hardcoded_defaults
    except toml.TomlDecodeError as e:
        logger.error(f"Decoding {CONFIG_FILE_PATH}: {e}. Using defaults.")
        return hardcoded_defaults

APP_CONFIG = load_app_config()

GEMINI_API_KEY_ENV_VAR = APP_CONFIG.get("gemini_api_key_env_var")
DEFAULT_TTS_MODEL_CONFIG = APP_CONFIG.get("default_tts_model")
AUDIO_SAMPLE_RATE = APP_CONFIG.get("audio_sample_rate", 24000)
MAX_CHUNK_CHARS_API_LIMIT = APP_CONFIG.get("max_chunk_chars_api_limit", 4800)
DEFAULT_TEMPERATURE_CONFIG = APP_CONFIG.get("default_temperature")
DEFAULT_CHUNK_SIZE_CHARS_CONFIG = APP_CONFIG.get("default_chunk_size_chars")
DEFAULT_API_TIMEOUT_SECONDS_CONFIG = APP_CONFIG.get("default_api_timeout_seconds")
DEFAULT_AUDIO_FORMAT_CONFIG = APP_CONFIG.get("default_audio_format")
DEFAULT_VOICE_DISPLAY_NAME_CONFIG = APP_CONFIG.get("default_voice_display_name")
SERVER_HOST_CONFIG = APP_CONFIG.get("server_host")
SERVER_PORT_CONFIG = APP_CONFIG.get("server_port")

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# --- Gemini Voices ---
_STUDIO_VOICES_RAW = [
    ("Zephyr", "Bright", "F"), ("Puck", "Upbeat", "M"), ("Charon", "Informative", "M"),
    ("Kore", "Firm", "F"), ("Fenrir", "Excitable", "M"), ("Leda", "Youthful", "F"),
    ("Orus", "Firm", "M"), ("Aoede", "Breezy", "F"), ("Callirrhoe", "Easy-going", "F"),
    ("Autonoe", "Bright", "F"), ("Enceladus", "Breathy", "M"), ("Iapetus", "Clear", "M"),
    ("Umbriel", "Easy-going", "M"), ("Algieba", "Smooth", "M"), ("Despina", "Smooth", "F"),
    ("Erinome", "Clear", "F"), ("Algenib", "Gravelly", "M"), ("Rasalgethi", "Informative", "M"),
    ("Laomedeia", "Upbeat", "F"), ("Achernar", "Soft", "F"), ("Alnilam", "Firm", "M"),
    ("Schedar", "Even", "M"), ("Gacrux", "Mature", "F"), ("Pulcherrima", "Forward", "F"),
    ("Achird", "Friendly", "M"), ("Zubenelgenubi", "Casual", "M"), ("Vindemiatrix", "Gentle", "F"),
    ("Sadachbia", "Lively", "M"), ("Sadaltager", "Knowledgeable", "M"), ("Sulafat", "Warm", "F"),
]
AVAILABLE_VOICES = []
for _api_name, _style, _gender_char in _STUDIO_VOICES_RAW:
    _gender_full = "Female" if _gender_char == "F" else "Male"
    _display_name = _api_name
    _description = f"{_gender_full} • {_style}"
    AVAILABLE_VOICES.append({
        "api_name": _api_name, "display_name": _display_name, "description": _description,
        "style": _style, "gender_char": _gender_char, "gender_full": _gender_full,
    })
DISPLAY_NAME_TO_API_NAME_MAP = {
    _v["display_name"]: _v["api_name"] for _v in AVAILABLE_VOICES
}

class APITimeoutError(Exception):
    pass

# --- Helper Functions ---
def get_gemini_api_key():
    api_key = os.environ.get(GEMINI_API_KEY_ENV_VAR) 
    if not api_key:
        raise ValueError(f"API key not found. Set {GEMINI_API_KEY_ENV_VAR} environment variable.")
    if not api_key.startswith("AIza") or len(api_key) < 35:
        logger.warning(f"API key format: {api_key[:5]}... (len: {len(api_key)})")
    return api_key

def get_available_gemini_voices():
    return [
        {"display_name": v["display_name"], "description": v["description"], "api_name": v["api_name"]}
        for v in AVAILABLE_VOICES
    ]

def _split_text_for_tts(text: str, max_length: int) -> list[str]:
    chunks = []
    remaining_text = text.strip()
    sentence_enders = ['.', '?', '!', '\n']
    while remaining_text:
        if len(remaining_text) <= max_length:
            chunks.append(remaining_text); break
        split_at = -1
        for i in range(min(len(remaining_text) - 1, max_length - 1), -1, -1):
            if remaining_text[i] in sentence_enders: split_at = i + 1; break
        if split_at == -1:
            for i in range(min(len(remaining_text) - 1, max_length - 1), -1, -1):
                if remaining_text[i] == ' ': split_at = i + 1; break
        if split_at == -1: split_at = max_length
        chunks.append(remaining_text[:split_at])
        remaining_text = remaining_text[split_at:].strip()
    return [chunk for chunk in chunks if chunk]

def _synthesize_with_gemini(text: str, voice_name: str, temperature: float, timeout_seconds_override: Optional[int]) -> bytes:
    api_key = get_gemini_api_key()
    model_name = DEFAULT_TTS_MODEL_CONFIG 
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    params = {"key": api_key}
    headers = {"Content-Type": "application/json", "User-Agent": "Gemini-TTS-Server/1.0"}
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}}
        }
    }
    logger.info(f"Sending request to Gemini: Model={model_name}, Voice={voice_name}, Temp={temperature:.1f}")
    max_retries = 3
    base_backoff_seconds = 1.0
    current_timeout = timeout_seconds_override if timeout_seconds_override and timeout_seconds_override > 0 else DEFAULT_API_TIMEOUT_SECONDS_CONFIG
    last_exception = None
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1}/{max_retries}  (timeout: {current_timeout}s)...")
            response = requests.post(url, params=params, headers=headers, json=payload, timeout=current_timeout)
            logger.info(f"Response status: {response.status_code}")
            if response.status_code == 429:
                err_detail = f"Rate limit (429)"; last_exception = requests.exceptions.RequestException(err_detail, response=response)
                if attempt < max_retries - 1:
                    time.sleep(base_backoff_seconds * (2**attempt))
                    logger.info(f"Retrying {err_detail}...")
                    continue
                else: raise last_exception
            if response.status_code >= 500:
                err_detail = f"Server error ({response.status_code})"; last_exception = requests.exceptions.RequestException(err_detail, response=response)
                if attempt < max_retries - 1:
                    time.sleep(base_backoff_seconds * (2**attempt))
                    logger.info(f"Retrying {err_detail}...")
                    continue
                else: raise last_exception
            response.raise_for_status()
            response_data = response.json()
            if "candidates" in response_data and response_data["candidates"] and \
               response_data["candidates"][0].get("content", {}).get("parts", [{}])[0].get("inlineData", {}).get("data"):
                return base64.b64decode(response_data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
            elif response_data.get("candidates",[{}])[0].get("content",{}).get("parts",[{}])[0].get("text"):
                raise ValueError(f"API returned text: '{response_data['candidates'][0]['content']['parts'][0]['text'][:200]}...'")
            raise ValueError(f"Invalid API response: {json.dumps(response_data)[:200]}...")
        except requests.exceptions.Timeout as e:
            last_exception = e
            logger.warning(f"Timeout on attempt {attempt+1}: {e}")
        except requests.exceptions.RequestException as e:
            last_exception = e
            logger.error(f"RequestException on attempt {attempt+1}: {e}")
        except ValueError as e:
            last_exception = e
            logger.error(f"ValueError on attempt {attempt+1}: {e}")
            raise
        except Exception as e:
            last_exception = e
            logger.error(f"Unexpected error on attempt {attempt+1}: {e}")
        if attempt < max_retries - 1 and isinstance(last_exception, (requests.exceptions.Timeout, requests.exceptions.RequestException)):
            if hasattr(last_exception, 'response') and last_exception.response is not None and last_exception.response.status_code == 403:
                logger.error("Permission denied (403), not retrying.")
                break
            time.sleep(base_backoff_seconds * (2**attempt)); continue
        elif attempt >= max_retries - 1: break
    if isinstance(last_exception, requests.exceptions.Timeout):
        raise APITimeoutError(f"API timed out after {max_retries} attempts. Last: {last_exception}") from last_exception
    elif last_exception: 
        raise Exception(f"API failed after {max_retries} attempts. Last: {last_exception}") from last_exception
    else: 
        raise Exception(f"API failed after {max_retries} attempts (unknown reason).")

def synthesize_speech_with_gemini(
    text: str, voice_display_name: str = DEFAULT_VOICE_DISPLAY_NAME_CONFIG, 
    audio_format: str = DEFAULT_AUDIO_FORMAT_CONFIG,
    temperature: float = DEFAULT_TEMPERATURE_CONFIG,
    chunk_size_chars: Optional[int] = None, 
    api_timeout_seconds: Optional[int] = None,
    task_id: Optional[str] = None
) -> Tuple[bytes, str]:
    final_timeout = api_timeout_seconds if api_timeout_seconds is not None else DEFAULT_API_TIMEOUT_SECONDS_CONFIG
    final_chunk_size = chunk_size_chars if chunk_size_chars is not None else DEFAULT_CHUNK_SIZE_CHARS_CONFIG
    logger.info(f"TTS task {task_id}: Voice='{voice_display_name}', Format='{audio_format}', Temp={temperature}, ChunkTarget={final_chunk_size}, Timeout={final_timeout}s")
    try:
        if task_id and task_registry.is_cancelled(task_id):
            raise TaskCancelledError()
        
        effective_chunk_size = min(final_chunk_size, MAX_CHUNK_CHARS_API_LIMIT)
        text_chunks = _split_text_for_tts(text, max_length=effective_chunk_size)
        if not text_chunks or not text_chunks[0].strip(): raise ValueError("No processable text.")
        logger.info(f"Task {task_id}: Text (len {len(text)}) split into {len(text_chunks)} chunks (target size {effective_chunk_size}).")
        
        audio_segments = []
        for i, chunk in enumerate(text_chunks):
            if task_id and task_registry.is_cancelled(task_id):
                raise TaskCancelledError()
            logger.info(f"Task {task_id}: Synthesizing chunk {i+1}/{len(text_chunks)} (len {len(chunk)})...")
            try:
                api_name = DISPLAY_NAME_TO_API_NAME_MAP.get(voice_display_name, voice_display_name)
                temp = min(max(temperature, 0.0), 2.0)
                
                # Detailed progress logging
                progress_msg = f"Task {task_id}: Processing chunk {i+1}/{len(text_chunks)} (attempt 1/3, timeout: {final_timeout}s)"
                logger.info(progress_msg)
                
                chunk_bytes = _synthesize_with_gemini(chunk, api_name, temp, final_timeout)
                if chunk_bytes:
                    audio_segments.append(AudioSegment(data=chunk_bytes, sample_width=2, frame_rate=AUDIO_SAMPLE_RATE, channels=1))
                else: raise ValueError("TTS chunk returned no data.")
            except TaskCancelledError: raise
            except Exception as e: raise Exception(f"Chunk {i+1} failed: {e}") from e
        if not audio_segments: raise ValueError("No audio segments produced.")
        
        logger.info(f"Task {task_id}: Concatenating {len(audio_segments)} audio segments.")
        combined = sum(audio_segments) if len(audio_segments) > 1 else audio_segments[0]
        buffer = io.BytesIO()
        target_fmt = audio_format.lower()
        combined.export(buffer, format=target_fmt)
        final_data = buffer.getvalue()
        mime = f"audio/{target_fmt}" 
        if target_fmt == 'flac': mime = 'audio/flac'
        logger.info(f"Task {task_id} synthesis completed ({len(final_data)} bytes)")
        return final_data, mime
    except TaskCancelledError as e:
        logger.info(f"Task {task_id} cancelled")
        raise
    except Exception as e:
        logger.error(f"Task {task_id} synthesis failed: {e}")
        raise
    finally:
        if task_id:
            task_registry.unregister(task_id)
