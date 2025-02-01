# utils.py
import time
import subprocess
import psutil
from colorama import init, Fore, Style

init(autoreset=True)

from state import log_store

LEVEL_COLORS = {
    "INFO": Fore.CYAN,
    "WARN": Fore.YELLOW,
    "ERROR": Fore.RED,
    "DEBUG": Fore.MAGENTA,
}

TAG_COLORS = {
    "BATTLE": Fore.BLUE,
    "REGION": Fore.GREEN,
    "ANALYSIS": Fore.MAGENTA,
    "MODULE": Fore.CYAN,
    "PROCESS": Fore.YELLOW,
    "GEAR": Fore.LIGHTRED_EX,
    "OCR": Fore.LIGHTBLUE_EX,
    "EVENT": Fore.LIGHTMAGENTA_EX,
}

def log(message, level="INFO", tag=None):
    """
    Timestamped log that stores logs in a global list with colored output.

    Parameters:
      - message: The log message to display.
      - level: Log level string (e.g., INFO, WARN, ERROR, DEBUG).
      - tag: An optional tag to further categorize the log message (e.g., BATTLE, REGION, ANALYSIS, MODULE, PROCESS, EVENT, etc.).
    """
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

    level_color = LEVEL_COLORS.get(level.upper(), Fore.WHITE)

    if tag:
        tag_color = TAG_COLORS.get(tag.upper(), Fore.WHITE)
        formatted_header = f"[{timestamp}] [{level_color}{level}{Style.RESET_ALL}:{tag_color}{tag}{Style.RESET_ALL}]"
        plain_header = f"[{timestamp}] [{level}:{tag}]"
    else:
        formatted_header = f"[{timestamp}] [{level_color}{level}{Style.RESET_ALL}]"
        plain_header = f"[{timestamp}] [{level}]"

    formatted_message = f"{formatted_header} {message}"
    print(formatted_message)

    plain_message = f"{plain_header} {message}"
    log_store.append(plain_message)
    if len(log_store) > 1000:
        log_store.pop(0)

def fuzzy_contains(text, fragments):
    """Return True if any of the fragments is found in the text."""
    return any(fragment in text for fragment in fragments)

def is_tesseract_installed():
    """Check if Tesseract is installed and available in the PATH."""
    try:
        subprocess.run(['tesseract', '--version'],
                       stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE,
                       check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def is_aces_running():
    """Check if the aces.exe process is running."""
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and proc.info['name'].lower() == 'aces.exe':
            return True
    return False