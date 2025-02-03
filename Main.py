# main.py
import time
import sys

from utils import is_tesseract_installed, is_aces_running, is_aces_in_focus
from detection import start_detection_thread, stop_detection_thread
from server import start_server
from discord_rpc import start_discord_rpc

def main():
    # Check if Tesseract is installed
    if not is_tesseract_installed():
        print("Tesseract is not installed. Please install it and ensure it's in your PATH.")
        sys.exit(1)

    print("Waiting for aces.exe to start...")
    while not is_aces_running():
        time.sleep(5)

    print("aces.exe detected. Waiting for focus...")
    while not is_aces_in_focus():
        print("aces.exe is running but not in focus. Waiting...")
        time.sleep(2)

    print("aces.exe is in focus. Starting detection, Discord RPC and web server...")
    start_detection_thread()
    start_discord_rpc()
    start_server()

    try:
        while True:
            if not is_aces_in_focus():
                print("Game lost focus; stopping detection.")
                stop_detection_thread()
                while not is_aces_in_focus():
                    time.sleep(1)
                print("Game regained focus; restarting detection.")
                start_detection_thread()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down.")

if __name__ == "__main__":
    main()