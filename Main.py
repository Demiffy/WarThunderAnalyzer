# Main.py
import time
import sys

from utils import is_tesseract_installed, is_aces_running
from detection import start_detection_thread
from server import start_server

def main():
    # Check if Tesseract is installed
    if not is_tesseract_installed():
        print("Tesseract is not installed. Please install it and ensure it's in your PATH.")
        sys.exit(1)

    print("Waiting for aces.exe to start...")
    while not is_aces_running():
        time.sleep(5)

    print("aces.exe detected. Starting detection loop and web server...")
    start_detection_thread()
    start_server()

if __name__ == "__main__":
    main()