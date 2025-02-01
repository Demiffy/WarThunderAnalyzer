# detection.py
import time
import threading
import pyautogui

import state
from utils import log, fuzzy_contains, is_aces_running
from image_processing import (
    extract_text_from_image,
    extract_battle_text_from_image,
    extract_gear_text_from_image,
    extract_modules_text_from_image
)
from analysis import analyze_text, analyze_modules_text

# Define region sizes and offsets
REGION_WIDTH = 450
REGION_HEIGHT = 250
BATTLE_REGION_WIDTH = 200
BATTLE_REGION_HEIGHT = 65
GEAR_REGION_WIDTH = 250
GEAR_REGION_HEIGHT = 100
MODULE_REGION_WIDTH = 200
MODULE_REGION_HEIGHT = 300
MODULE_OFFSET_DOWN = 20

def detection_loop():
    screen_width, screen_height = pyautogui.size()

    # Define screen regions based on screen size
    region_left = screen_width - REGION_WIDTH
    region_top = 0
    region_right = screen_width
    region_bottom = REGION_HEIGHT

    battle_left = (screen_width - BATTLE_REGION_WIDTH) // 2
    battle_top = 0
    battle_right = battle_left + BATTLE_REGION_WIDTH
    battle_bottom = BATTLE_REGION_HEIGHT

    gear_left = 0
    gear_right = GEAR_REGION_WIDTH
    gear_top = screen_height - GEAR_REGION_HEIGHT
    gear_bottom = screen_height

    module_right = screen_width
    module_left = module_right - MODULE_REGION_WIDTH
    module_top = region_bottom + MODULE_OFFSET_DOWN
    module_bottom = module_top + MODULE_REGION_HEIGHT

    last_battle_time = None
    last_detection_time = time.time()

    while True:
        if not is_aces_running():
            log("aces.exe not found. Pausing detection until process is available.",
                level="WARN", tag="PROCESS")
            state.game_state = "Waiting for aces.exe"
            while not is_aces_running():
                time.sleep(2)
            log("aces.exe detected again. Resuming detection.", level="INFO", tag="PROCESS")
            last_detection_time = time.time()

        # Process battle region
        battle_screenshot = pyautogui.screenshot().crop(
            (battle_left, battle_top, battle_right, battle_bottom)
        )
        battle_text = extract_battle_text_from_image(battle_screenshot).lower()

        if "to battle" in battle_text:
            last_battle_time = time.time()
            last_detection_time = time.time()
            log("Detected 'To Battle!' — assuming Main Menu.", tag="BATTLE")
            state.game_state = "In Menu"
        else:
            if state.game_state not in ["In Game", "Game Not In Focus"]:
                state.game_state = "Unknown"

        # Process gear region
        gear_screenshot = pyautogui.screenshot().crop(
            (gear_left, gear_top, gear_right, gear_bottom)
        )
        gear_text = extract_gear_text_from_image(gear_screenshot).lower()

        if fuzzy_contains(gear_text, ["gear", "rpm", "spd", "km/h", "n"]):
            last_detection_time = time.time()

        if time.time() - last_detection_time > 20:
            state.game_state = "Game Not In Focus"
            time.sleep(1)
            continue

        current_time = time.time()
        if last_battle_time is None or (current_time - last_battle_time > 10):
            if fuzzy_contains(gear_text, ["gear", "rpm", "spd", "km/h", "n"]):
                state.game_state = "In Game"
                screenshot = pyautogui.screenshot().crop(
                    (region_left, region_top, region_right, region_bottom)
                )
                extracted_text = extract_text_from_image(screenshot)
                log(f"Hit/Kill Region Text Detected:\n{extracted_text}", tag="REGION")

                result = analyze_text(extracted_text)
                log(f"Analysis Result: {result}", tag="ANALYSIS")
                state.last_event_result = result

                # If a significant event occurred, add extra decoration.
                if "no significant events detected" not in result.lower():
                    log("***** EVENT DETECTED *****", tag="EVENT")
                    log("-" * 60, tag="EVENT")

                module_screenshot = pyautogui.screenshot().crop(
                    (module_left, module_top, module_right, module_bottom)
                )
                modules_extracted_text = extract_modules_text_from_image(module_screenshot)
                log(f"Module Region Raw Text:\n{modules_extracted_text}", tag="MODULE")

                modules_result = analyze_modules_text(modules_extracted_text)
                log(f"Modules Analysis Result: {modules_result}", tag="MODULE")
                state.last_modules_result = modules_result

                # Sleep longer if significant events were detected
                if ("no significant events detected" not in result.lower() or
                    "no significant modules detected" not in modules_result.lower()):
                    time.sleep(4)
                else:
                    time.sleep(1)
            else:
                log("Gear info not detected, skipping hit/kill detection.", level="WARN", tag="GEAR")
                state.game_state = "Unknown"
                time.sleep(1)
        else:
            log("Waiting due to recent 'To Battle!' detection...", level="INFO", tag="BATTLE")
            time.sleep(1)

def start_detection_thread():
    """Start the detection loop in a separate daemon thread."""
    detection_thread = threading.Thread(target=detection_loop, daemon=True)
    detection_thread.start()