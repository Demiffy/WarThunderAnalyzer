import time
from PIL import Image, ImageOps
import numpy as np
import pytesseract
from pytesseract import TesseractError
import pyautogui

# Define region sizes and offsets
REGION_WIDTH = 450
REGION_HEIGHT = 250

BATTLE_REGION_WIDTH = 200
BATTLE_REGION_HEIGHT = 65

GEAR_REGION_WIDTH = 250
GEAR_REGION_HEIGHT = 100

# Adjustable constants for module region
MODULE_REGION_WIDTH = 200
MODULE_REGION_HEIGHT = 300
MODULE_OFFSET_DOWN = 20

def log(message, level="INFO"):
    """Prints a timestamped log message with a specified level."""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {message}")

def preprocess_image_for_colors(image):
    np_image = np.array(image)
    red_channel = np_image[:, :, 0]
    green_channel = np_image[:, :, 1]
    blue_channel = np_image[:, :, 2]

    red_mask = (red_channel > 120) & (green_channel < 70) & (blue_channel < 100)
    yellow_green_mask = (red_channel > 190) & (green_channel > 180) & (blue_channel < 60)
    e4ac03_mask = (red_channel > 220) & (green_channel > 160) & (blue_channel < 50)
    mask_90ca03 = (
        (red_channel > 130) & (red_channel < 160) &
        (green_channel > 190) & (green_channel < 220) &
        (blue_channel > 0) & (blue_channel < 50)
    )

    combined_mask = red_mask | yellow_green_mask | e4ac03_mask | mask_90ca03
    filtered_image = np.zeros_like(np_image)
    filtered_image[combined_mask] = [255, 255, 255]
    filtered_image[~combined_mask] = [0, 0, 0]

    processed_image = Image.fromarray(filtered_image).convert("L")
    processed_image = ImageOps.invert(processed_image)
    return processed_image

def preprocess_image_for_modules(image):
    np_image = np.array(image)
    red_channel = np_image[:, :, 0]
    green_channel = np_image[:, :, 1]
    blue_channel = np_image[:, :, 2]

    red_only_mask = (red_channel > 180) & (green_channel < 80) & (blue_channel < 80)
    filtered_image = np.zeros_like(np_image)
    filtered_image[red_only_mask] = [255, 255, 255]
    filtered_image[~red_only_mask] = [0, 0, 0]

    processed_image = Image.fromarray(filtered_image).convert("L")
    processed_image = ImageOps.invert(processed_image)
    return processed_image

def fuzzy_contains(text, fragments):
    return any(fragment in text for fragment in fragments)

def analyze_text(extracted_text):
    text = extracted_text.lower()
    events = []

    fire_fragments = ["fire"]
    crew_fragments = ["cre", "kno", "out"]
    crit_fragments = ["crit"]
    hit_fragments = ["hit"]
    ricochet_fragments = ["rico", "rochet"]
    non_penetration_fragments = ["non", "-", "penetrat"]
    explosion_fragments = ["explod"]
    ammo_fragments = ["ammun"]
    fuel_fragments = ["fuel"]

    if fuzzy_contains(text, fire_fragments):
        events.append("Enemy set on fire")
    if fuzzy_contains(text, crew_fragments):
        events.append("Enemy killed, Crew knocked out")
    if fuzzy_contains(text, crit_fragments):
        events.append("Enemy Crit")
    elif fuzzy_contains(text, hit_fragments):
        events.append("Enemy Hit (Most likely not critical)")
    if fuzzy_contains(text, ricochet_fragments):
        events.append("Ricochet occurred")
    if fuzzy_contains(text, non_penetration_fragments):
        events.append("Non-penetration event")
    if fuzzy_contains(text, explosion_fragments):
        extended_ammo_fragments = ammo_fragments + ["amme"]
        if fuzzy_contains(text, extended_ammo_fragments) and fuzzy_contains(text, fuel_fragments):
            events.append("Enemy killed by ammunition and fuel explosion")
        elif fuzzy_contains(text, extended_ammo_fragments):
            events.append("Enemy killed by ammunition explosion")
        elif fuzzy_contains(text, fuel_fragments):
            events.append("Enemy killed by fuel explosion")
        else:
            events.append("Enemy killed by unspecified explosion")

    if not events:
        events.append("No significant events detected")

    return "; ".join(events)

def analyze_modules_text(extracted_text):
    text = extracted_text.lower()
    modules_detected = []

    module_fragments = {
        "Track": ["track", "tra"],
        "Cannon barrel": ["barrel", "barr"],
        "Horizontal turret drive": ["hor", "horizontal", "tal"],
        "Vertical turret drive": ["ver", "vertical", "cal"],
        "Driver": ["driver", "driv"],
        "Gunner": ["gunner","ner"],
        "Commander": ["comm", "ander"],
        "Loader": ["loader", "load"],
        "Machine gunner": ["mach", "ine"],
        "Cannon breech": ["breech", "ee", "ech"],
        "Fuel tank": ["fuel", "tank"],
        "Engine": ["engin", "eng"],
        "Transmission": ["transmiss", "trans"],
        "Radiator": ["radiat", "rad"],
        "Ammo": ["ammo", "amme", "amm"]
    }

    for module, fragments in module_fragments.items():
        if all(fuzzy_contains(text, [frag]) for frag in fragments):
            modules_detected.append(module)

    if not modules_detected:
        modules_detected.append("No significant modules detected")

    return "; ".join(modules_detected)

def extract_text_from_image(image):
    processed_image = preprocess_image_for_colors(image)
    try:
        custom_config = r'--oem 3 --psm 6'
        return pytesseract.image_to_string(processed_image, lang='eng', config=custom_config)
    except TesseractError as e:
        log(f"Tesseract error in color region: {e}", level="ERROR")
        return ""

def extract_battle_text_from_image(image):
    try:
        custom_config = r'--oem 3 --psm 6'
        return pytesseract.image_to_string(image, lang='eng', config=custom_config)
    except TesseractError as e:
        log(f"Tesseract error in battle region: {e}", level="ERROR")
        return ""

def extract_gear_text_from_image(image):
    try:
        custom_config = r'--oem 3 --psm 6'
        return pytesseract.image_to_string(image, lang='eng', config=custom_config)
    except TesseractError as e:
        log(f"Tesseract error in gear region: {e}", level="ERROR")
        return ""

def extract_modules_text_from_image(image):
    processed_image = preprocess_image_for_modules(image)
    try:
        custom_config = r'--oem 3 --psm 6'
        return pytesseract.image_to_string(processed_image, lang='eng', config=custom_config)
    except TesseractError as e:
        log(f"Tesseract error in modules region: {e}", level="ERROR")
        return ""

if __name__ == "__main__":
    screen_width, screen_height = pyautogui.size()

    # Coordinates for various regions
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

    # Display startup snapshots for module region
    #initial_module_screenshot = pyautogui.screenshot().crop(
     #   (module_left, module_top, module_right, module_bottom)
    #)
    #log("Displaying initial raw snapshot of the module region.")
    #initial_module_screenshot.show(title="Initial Module Region Snapshot")

    #processed_module_image = preprocess_image_for_modules(initial_module_screenshot)
    #log("Displaying processed snapshot of the module region.")
    #processed_module_image.show(title="Processed Module Region Snapshot")

    last_battle_time = None

    while True:
        battle_screenshot = pyautogui.screenshot().crop((battle_left, battle_top, battle_right, battle_bottom))
        battle_text = extract_battle_text_from_image(battle_screenshot).lower()

        if "to battle" in battle_text:
            last_battle_time = time.time()
            log("Detected 'To Battle!' — pausing hit/kill detection.")

        current_time = time.time()
        if last_battle_time is None or (current_time - last_battle_time > 10):
            gear_screenshot = pyautogui.screenshot().crop((gear_left, gear_top, gear_right, gear_bottom))
            gear_text = extract_gear_text_from_image(gear_screenshot).lower()

            if fuzzy_contains(gear_text, ["gear", "rpm", "spd", "km/h", "n"]):
                screenshot = pyautogui.screenshot().crop((region_left, region_top, region_right, region_bottom))
                extracted_text = extract_text_from_image(screenshot)
                log(f"Hit/Kill Region Text Detected:\n{extracted_text}")

                result = analyze_text(extracted_text)
                log(f"Analysis Result: {result}")

                module_screenshot = pyautogui.screenshot().crop((module_left, module_top, module_right, module_bottom))
                modules_extracted_text = extract_modules_text_from_image(module_screenshot)
                log(f"Module Region Raw Text:\n{modules_extracted_text}")

                modules_result = analyze_modules_text(modules_extracted_text)
                log(f"Modules Analysis Result: {modules_result}")

                if ("No significant events detected" not in result or
                    "No significant modules detected" not in modules_result):
                    time.sleep(4)
                else:
                    time.sleep(1)
            else:
                log("Gear info not detected, skipping hit/kill detection.", level="WARN")
                time.sleep(1)
        else:
            log("Waiting due to recent 'To Battle!' detection...", level="INFO")
            time.sleep(1)
