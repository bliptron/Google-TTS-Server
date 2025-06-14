import uvicorn
import webbrowser
import os
import time
import threading
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import HOST and PORT from the tts_client where config is loaded
from app.tts_client import SERVER_HOST_CONFIG, SERVER_PORT_CONFIG

HOST = SERVER_HOST_CONFIG if SERVER_HOST_CONFIG else "127.0.0.1"
PORT = SERVER_PORT_CONFIG if SERVER_PORT_CONFIG else 8008 
APP_MODULE = "app.main:app"

def open_browser_after_delay():
    url = f"http://{HOST if HOST != '0.0.0.0' else '127.0.0.1'}:{PORT}"
    time.sleep(2.5) 
    logger.info(f"Attempting to open browser at: {url}")
    try:
        webbrowser.open(url, new=0)
    except Exception as e:
        logger.error(f"Could not open browser: {e}")

if __name__ == "__main__":
    # Heuristic to open browser only on the very first launch, not on Uvicorn reloads.
    # Uvicorn reloader spawns a new process which inherits environment variables.
    should_open_browser_flag = os.environ.get("GEMINI_TTS_SERVER_BROWSER_OPENED")
    
    if should_open_browser_flag != "true":
        logger.info("Initial server launch: Scheduling browser opening.")
        os.environ["GEMINI_TTS_SERVER_BROWSER_OPENED"] = "true" # Set flag for reloaded processes
        
        browser_thread = threading.Thread(target=open_browser_after_delay, daemon=True)
        browser_thread.start()
    else:
        logger.info("Server is reloading (GEMINI_TTS_SERVER_BROWSER_OPENED=true); browser will not be opened again.")

    logger.info(f"Starting Uvicorn server for {APP_MODULE} on http://{HOST}:{PORT} (reload enabled)")
    
    try:
        uvicorn.run(
            APP_MODULE, 
            host=HOST, 
            port=PORT, 
            reload=False, # Changed to False for stability if reloader is problematic
            workers=1 
        )
    except KeyboardInterrupt:
        logger.info("\nServer shutdown initiated by user (Ctrl+C).")
    except RuntimeError as e:
        if "signal only works in main thread" in str(e) or "Watcher only works in main thread" in str(e):
            logger.error("\n-------------------------------------------------------------------------")
            logger.error("ERROR: Uvicorn reloader failed. This can happen on some systems when")
            logger.error("       uvicorn with reload=True is launched from a script that uses threads, or other conflicts.")
            logger.error("       If issues persist, try running Uvicorn directly from the command line:")
            logger.error(f"         uvicorn {APP_MODULE} --host {HOST} --port {PORT} --reload")
            logger.error("-------------------------------------------------------------------------")
        else:
            raise # Re-raise other RuntimeErrors
    finally:
        # This cleanup might not always run if the parent process is killed before the reloaded child exits
        # or if Uvicorn handles signals in a way that bypasses this finally in the parent.
        # It's a best effort for when the initial script instance exits cleanly.
        if os.environ.get("GEMINI_TTS_SERVER_BROWSER_OPENED") == "true" and should_open_browser_flag != "true":
             # Only attempt to delete if this instance was the one that set it (i.e., the first run)
             # However, child processes inherit it, so deleting it here might make the next *manual* start open browser again.
             # For simplicity, perhaps leave it set. The check `should_open_browser_flag != "true"` handles the logic.
             pass 
        logger.info("Server script finished.")
