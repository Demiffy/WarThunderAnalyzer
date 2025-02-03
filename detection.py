# detection.py
import time
import threading
import pyautogui
import os

import state
from utils import log, fuzzy_contains, is_aces_running, is_aces_in_focus
from image_processing import (
    extract_text_from_image,
    extract_battle_text_from_image,
    extract_gear_text_from_image,
    extract_modules_text_from_image,
    preprocess_image_for_colors,
    preprocess_image_for_gear,
)
from analysis import analyze_text, analyze_modules_text

# Define screen regions for detection
REGION_WIDTH = 450
REGION_HEIGHT = 50
BATTLE_REGION_WIDTH = 200
BATTLE_REGION_HEIGHT = 65
GEAR_REGION_WIDTH = 250
GEAR_REGION_HEIGHT = 100
MODULE_REGION_WIDTH = 200
MODULE_REGION_HEIGHT = 300
MODULE_OFFSET_DOWN = 20

_stop_event = threading.Event()
_detection_thread = None

def detection_loop():
    screen_width, screen_height = pyautogui.size()

    # Define screen regions based on screen size
    region_left = screen_width - REGION_WIDTH
    region_top = 0

    battle_left = (screen_width - BATTLE_REGION_WIDTH) // 2
    battle_top = 0

    gear_left = 0
    gear_top = screen_height - GEAR_REGION_HEIGHT

    module_left = screen_width - MODULE_REGION_WIDTH
    module_top = REGION_HEIGHT + MODULE_OFFSET_DOWN

    # Create the screenshots folder if it does not exist
    screenshot_folder = os.path.join("static", "screenshots")
    if not os.path.exists(screenshot_folder):
        os.makedirs(screenshot_folder)

    last_battle_time = None
    last_detection_time = time.time()
    prev_state = state.game_state

    if not hasattr(detection_loop, "gear_logged"):
        detection_loop.gear_logged = False

    while not _stop_event.is_set():
        if not is_aces_in_focus():
            if state.game_state != "Game Not In Focus":
                log("aces.exe is out of focus. Pausing detection.", level="INFO", tag="DETECTION")
            state.game_state = "Game Not In Focus"
            time.sleep(2)
            continue

        if not is_aces_running():
            log("aces.exe not found. Pausing detection until process is available.", level="WARN", tag="PROCESS")
            state.game_state = "Waiting for aces.exe"
            while not is_aces_running() and not _stop_event.is_set():
                time.sleep(2)
            log("aces.exe detected again. Resuming detection.", level="INFO", tag="PROCESS")
            last_detection_time = time.time()
            continue

        battle_screenshot = pyautogui.screenshot(region=(battle_left, battle_top, BATTLE_REGION_WIDTH, BATTLE_REGION_HEIGHT))
        battle_text = extract_battle_text_from_image(battle_screenshot).lower()

        if "to battle" in battle_text:
            last_battle_time = time.time()
            last_detection_time = time.time()
            log("Detected 'To Battle!' — assuming Main Menu.", tag="BATTLE")
            state.game_state = "In Menu"
            state.stats["kills"] = 0
            state.last_event_result = ""
            detection_loop.gear_logged = False
        else:
            if state.game_state not in ["In Game", "Game Not In Focus"]:
                state.game_state = "Unknown"

        gear_screenshot = pyautogui.screenshot(region=(gear_left, gear_top, GEAR_REGION_WIDTH, GEAR_REGION_HEIGHT))
        gear_text = extract_gear_text_from_image(gear_screenshot).lower()

        keywords = ["gear", "rpm", "spd", "km/h"]
        if any(keyword in gear_text for keyword in keywords):
            last_detection_time = time.time()
            if not detection_loop.gear_logged:
                raw_gear_filename = f"gear_raw_{int(time.time())}.png"
                raw_gear_filepath = os.path.join(screenshot_folder, raw_gear_filename)
                gear_screenshot.save(raw_gear_filepath)
                raw_gear_link = f"http://localhost:5000/static/screenshots/{raw_gear_filename}"

                processed_gear = preprocess_image_for_gear(gear_screenshot)
                proc_gear_filename = f"gear_proc_{int(time.time())}.png"
                proc_gear_filepath = os.path.join(screenshot_folder, proc_gear_filename)
                processed_gear.save(proc_gear_filepath)
                proc_gear_link = f"http://localhost:5000/static/screenshots/{proc_gear_filename}"

                log(f"In-Game detected. Gear info preview (raw): {raw_gear_link}", tag="GEAR")
                log(f"In-Game detected. Gear info preview (processed): {proc_gear_link}", tag="GEAR")
                detection_loop.gear_logged = True
        else:
            log("Gear info not detected in OCR output, skipping gear logging.", level="WARN", tag="GEAR")

        if time.time() - last_detection_time > 20:
            state.game_state = "Game Not In Focus"
            time.sleep(1)
            prev_state = state.game_state
            continue

        current_time = time.time()
        if last_battle_time is None or (current_time - last_battle_time > 10):
            if fuzzy_contains(gear_text, ["gear", "rpm", "spd", "km/h", "n"]):
                state.game_state = "In Game"
                screenshot = pyautogui.screenshot(region=(region_left, region_top, REGION_WIDTH, REGION_HEIGHT))
                extracted_text = extract_text_from_image(screenshot)
                result = analyze_text(extracted_text)
                state.last_event_result = result
                state.last_event_timestamp = time.time()

                if "no significant events detected" not in result.lower():
                    raw_filename = f"event_raw_{int(time.time())}.png"
                    raw_filepath = os.path.join(screenshot_folder, raw_filename)
                    screenshot.save(raw_filepath)
                    raw_link = f"http://localhost:5000/static/screenshots/{raw_filename}"

                    processed_image = preprocess_image_for_colors(screenshot)
                    proc_filename = f"event_proc_{int(time.time())}.png"
                    proc_filepath = os.path.join(screenshot_folder, proc_filename)
                    processed_image.save(proc_filepath)
                    proc_link = f"http://localhost:5000/static/screenshots/{proc_filename}"

                    log(f"Hit/Kill Region Text Detected:\n{extracted_text}", tag="REGION")
                    log(f"Analysis Result: {result}", tag="ANALYSIS")
                    log("***** EVENT DETECTED *****", tag="EVENT")
                    log("-" * 60, tag="EVENT")
                    log(f"Raw Event Image Preview: {raw_link}", tag="EVENT")
                    log(f"Processed Event Image Preview: {proc_link}", tag="EVENT")

                    state.last_raw_event_snapshot = raw_link
                    state.last_processed_event_snapshot = proc_link
                    module_screenshot = pyautogui.screenshot(region=(module_left, module_top, MODULE_REGION_WIDTH, MODULE_REGION_HEIGHT))
                    modules_extracted_text = extract_modules_text_from_image(module_screenshot)
                    log(f"Module Region Raw Text:\n{modules_extracted_text}", tag="MODULE")
                    modules_result = analyze_modules_text(modules_extracted_text)
                    log(f"Modules Analysis Result: {modules_result}", tag="MODULE")
                    state.last_modules_result = modules_result
                    state.last_modules_timestamp = time.time()
                    time.sleep(4)
                else:
                    time.sleep(0.5)
            else:
                log("Gear info not detected, skipping hit/kill detection.", level="WARN", tag="GEAR")
                state.game_state = "Unknown"
                time.sleep(0.5)
        else:
            log("Waiting due to recent 'To Battle!' detection...", level="INFO", tag="BATTLE")
            time.sleep(0.5)

        prev_state = state.game_state

def start_detection_thread():
    """Start the detection loop in a separate daemon thread."""
    global _detection_thread
    _stop_event.clear()
    _detection_thread = threading.Thread(target=detection_loop, daemon=True)
    _detection_thread.start()

def stop_detection_thread():
    """Signal the detection thread to stop."""
    _stop_event.set()