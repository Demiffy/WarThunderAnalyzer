import sys
import threading
import signal
from concurrent.futures import ThreadPoolExecutor

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

shutdown_event = threading.Event()

def initialize_services():
    log("Starting services: detection, Discord RPC, rangefinder, minimap tracking, web server...", level="INFO", tag="PROCESS")

    start_detection_thread()
    start_discord_rpc()

    rangefinder_thread = threading.Thread(target=rangefinder_logic.start_rangefinder, daemon=True)
    rangefinder_thread.start()

    # Start web server
    start_server()

    return rangefinder_thread


def cleanup():
    log("Shutting down all services...", level="INFO", tag="PROCESS")
    shutdown_event.set()
    stop_detection_thread()
    log("All services stopped.", level="INFO", tag="PROCESS")


def signal_handler(sig, frame):
    log("Termination signal received. Cleaning up...", level="INFO", tag="PROCESS")
    cleanup()
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    check_resolution()

    if not is_tesseract_installed():
        log("Tesseract is not installed. Please install it and ensure it's in your PATH.", level="ERROR", tag="PROCESS")
        sys.exit(1)

    wait_for_aces()

    rangefinder_thread = initialize_services()

    try:
        handle_focus_loss(stop_detection_thread, start_detection_thread)
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    main()