import time
import psutil
import win32gui
import win32process

TARGET_PROCESS = "aces.exe"

def get_foreground_process():
    """Gets the process name of the currently focused window."""
    hwnd = win32gui.GetForegroundWindow()
    if hwnd:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['pid'] == pid:
                return proc.info['name'].lower()
    return None

def is_aces_in_focus():
    """Checks if 'aces.exe' is the foreground process."""
    active_process = get_foreground_process()
    return active_process == TARGET_PROCESS.lower()

if __name__ == "__main__":
    print("Monitoring if ACES.EXE is in focus every 2 seconds...")
    try:
        while True:
            if is_aces_in_focus():
                print("ACES.EXE is in focus.")
            else:
                print("ACES.EXE is NOT in focus.")
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")