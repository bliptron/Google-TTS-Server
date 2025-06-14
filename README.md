# Gemini TTS Server (Beta)

⚠️ **Warning**: This project is currently in beta testing phase. APIs may change without notice.

# Gemini TTS Server

![Python](https://img.shields.io/badge/python-3.10%E2%80%933.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)
[![Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A FastAPI server for Google Gemini Text-to-Speech with a modern web interface.

---

## Features

- Text-to-speech conversion using Google Gemini API
- Web-based interface for text input and voice selection
- Adjustable synthesis parameters (temperature, chunk size, timeout)
- Support for multiple audio formats (WAV, MP3, FLAC)
- Real-time task cancellation
- Modern, responsive UI
- Configuration via `config.toml` file

---

## Demo

<!-- Replace with your own screenshot or GIF -->
![Gemini TTS Server Demo](static/demo-screenshot.png)

---

## System Requirements

- Tested with Python 3.10, 3.11, and 3.12 - Note: Python 3.13+ is not supported due to audioop deprecation
- 4GB RAM minimum
- 100MB disk space
- Google Gemini API Key
- Stable internet connection

---

## Installation Guide

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/google-tts-server.git
cd google-tts-server
```

### 2. Set Up Virtual Environment (Recommended)
```bash
# Windows:
python -m venv venv
venv\Scripts\activate

# Mac/Linux:
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configuration Setup

#### Environment Variables
Create `.env` file:
```bash
cp .env.example .env  # If example exists
# Or create manually:
echo "GEMINI_API_KEY=your_api_key_here" > .env
```

#### Server Configuration
Edit `config.toml`:
```toml
[server]
host = "127.0.0.1"  # Change to "0.0.0.0" for network access
port = 8008         # Use any available port

[tts]
default_model = "gemini-2.5-pro-preview-tts"
default_voice = "Fenrir"
default_format = "wav"
```

### 5. Verify Installation
```bash
python -c "import uvicorn, fastapi; print('Dependencies OK')"
```

### 6. Start the Server
```bash
python server.py
```

### 7. Access the Web Interface
Open in your browser:
[http://localhost:8008](http://localhost:8008)

> 💡 **Tip**: Use `--reload` flag during development:
> `python server.py --reload`

---

## Usage

- Enter your text, select a voice and parameters, and click **Synthesize**.
- Download or play the generated audio directly from the web interface.
- Cancel long-running tasks in real time.

---

## API Reference

### Authentication
No authentication required for local development. For production, consider adding API key authentication.

### Rate Limits
- Default: 60 requests/minute
- Adjust in `config.toml`:
```toml
[rate_limits]
api_calls_per_minute = 60
```

### Endpoints

#### `POST /api/synthesize`
Convert text to speech audio.

**Request:**
```json
{
  "text": "Hello world",
  "voice_name": "Fenrir",
  "audio_format": "mp3",
  "temperature": 1.0,
  "task_id": "optional-uuid"
}
```

**Success Response:**
- Status: 200 OK
- Headers: `Content-Type: audio/mp3`
- Body: Binary audio data

**Error Responses:**
- 400: Invalid input parameters
- 429: Rate limit exceeded
- 499: Task cancelled
- 500: Server error

---

#### `GET /api/voices`
List available voices.

**Response:**
```json
{
  "voices": [
    {
      "display_name": "Fenrir",
      "description": "Male • Excitable",
      "api_name": "Fenrir"
    }
  ],
  "default_voice": "Fenrir"
}
```

---

#### `POST /api/cancel_task/{task_id}`
Cancel a running synthesis task.

**Response:**
```json
{
  "message": "Cancellation request processed",
  "task_id": "your-task-id"
}
```

---

## Development

### Running Tests
```bash
pytest tests/
```

### Code Formatting
```bash
black .
```

### Linting
```bash
flake8 app/
```

### Debugging
Enable debug mode:
```bash
python server.py --debug
```

---

## Troubleshooting Guide

### Common Issues

#### No Audio Output
1. Verify API key in `.env` is valid
2. Check server logs for errors
3. Test with simple text: `curl -X POST http://localhost:8008/api/synthesize -H "Content-Type: application/json" -d '{"text":"test"}'`

#### Port Conflicts
```bash
# Find process using port 8008:
sudo lsof -i :8008
# Kill process:
kill -9 <PID>
```

#### API Errors
| Code | Meaning | Solution |
|------|---------|----------|
| 403 | Invalid API key | Check `.env` file |
| 429 | Rate limited | Wait or increase limits |
| 500 | Server error | Check logs |

---

## Project Structure

```
.
├── app/                 # Application code
│   ├── main.py          # FastAPI routes
│   ├── tts_client.py    # Gemini API client
│   ├── task_registry.py # Task management
│   ├── static/          # Web assets
│   │   ├── css/
│   │   ├── js/
│   │   └── index.html
├── tests/               # Test cases
├── config.toml          # Configuration
├── requirements.txt     # Dependencies
├── server.py            # Entry point
└── README.md            # Documentation
```

---

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/your-feature`)
3. Commit changes (`git commit -am 'Add some feature'`)
4. Push to branch (`git push origin feature/your-feature`)
5. Open Pull Request

---

## License
MIT License - See [LICENSE](LICENSE) for details.

---

## Acknowledgments
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [pydub](https://github.com/jiaaro/pydub) - Audio processing
- [Google Gemini](https://ai.google.dev/) - TTS API
