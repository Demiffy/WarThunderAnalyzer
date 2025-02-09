import sys
import threading

from utils import (
    is_tesseract_installed,
    check_resolution,
    wait_for_aces,
    handle_focus_loss,
    log
)
from detection import start_detection_thread, stop_detection_thread
from server import start_server
from discord_rpc import start_discord_rpc
import rangefinder_logic

def main():
    check_resolution()

    if not is_tesseract_installed():
        log("Tesseract is not installed. Please install it and ensure it's in your PATH.", level="ERROR", tag="PROCESS")
        sys.exit(1)

    wait_for_aces()

    log("Starting detection, Discord RPC, rangefinder, minimap tracking, and web server...", level="INFO", tag="PROCESS")
    start_detection_thread()
    start_discord_rpc()

    rangefinder_thread = threading.Thread(target=rangefinder_logic.start_rangefinder, daemon=True)
    rangefinder_thread.start()

    start_server()

    try:
        handle_focus_loss(stop_detection_thread, start_detection_thread)
    except KeyboardInterrupt:
        log("Shutting down.", level="INFO", tag="PROCESS")
        sys.exit(0)

if __name__ == "__main__":
    main()