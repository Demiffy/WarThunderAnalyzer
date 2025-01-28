import time
import threading
import subprocess
import psutil
from flask import Flask, render_template_string
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
MODULE_REGION_WIDTH = 200
MODULE_REGION_HEIGHT = 300
MODULE_OFFSET_DOWN = 20

app = Flask(__name__)

log_store = []
game_state = "Unknown"
last_event_result = ""
last_modules_result = ""

stats = {
    "hits": 0,
    "crits": 0,
    "kills": 0,
    "fires": 0,
    "ricochets": 0,
    "non_penetrations": 0,
    "ammo_explosions": 0,
    "fuel_explosions": 0,
    "unknown_events": 0
}

prev_stats = stats.copy()

def log(message, level="INFO"):
    """Timestamped log that stores logs in a global list."""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    formatted_message = f"[{timestamp}] [{level}] {message}"
    print(formatted_message)
    log_store.append(formatted_message)
    if len(log_store) > 1000:
        log_store.pop(0)

def preprocess_image_for_colors(image):
    np_image = np.array(image)
    red_channel = np_image[:, :, 0]
    green_channel = np_image[:, :, 1]
    blue_channel = np_image[:, :, 2]
    red_mask = (red_channel > 120) & (green_channel < 70) & (blue_channel < 100)
    yellow_green_mask = (red_channel > 190) & (green_channel > 180) & (blue_channel < 60)
    e4ac03_mask = (red_channel > 220) & (green_channel > 160) & (blue_channel < 50)
    mask_90ca03 = ((red_channel > 130) & (red_channel < 160) &
                   (green_channel > 190) & (green_channel < 220) &
                   (blue_channel > 0) & (blue_channel < 50))
    combined_mask = red_mask | yellow_green_mask | e4ac03_mask | mask_90ca03
    filtered_image = np.zeros_like(np_image)
    filtered_image[combined_mask] = [255, 255, 255]
    filtered_image[~combined_mask] = [0, 0, 0]
    processed_image = Image.fromarray(filtered_image).convert("L")
    return ImageOps.invert(processed_image)

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
    return ImageOps.invert(processed_image)

def fuzzy_contains(text, fragments):
    return any(fragment in text for fragment in fragments)

def analyze_text(extracted_text):
    global stats
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
        stats["fires"] += 1
    if fuzzy_contains(text, crew_fragments):
        events.append("Enemy killed, Crew knocked out")
        stats["kills"] += 1
    if fuzzy_contains(text, crit_fragments):
        events.append("Enemy Crit")
        stats["crits"] += 1
    elif fuzzy_contains(text, hit_fragments):
        events.append("Enemy Hit (Most likely not critical)")
        stats["hits"] += 1
    if fuzzy_contains(text, ricochet_fragments):
        events.append("Ricochet occurred")
        stats["ricochets"] += 1
    if fuzzy_contains(text, non_penetration_fragments):
        events.append("Non-penetration event")
        stats["non_penetrations"] += 1
    if fuzzy_contains(text, explosion_fragments):
        extended_ammo_fragments = ammo_fragments + ["amme"]
        if fuzzy_contains(text, extended_ammo_fragments) and fuzzy_contains(text, fuel_fragments):
            events.append("Enemy killed by ammunition and fuel explosion")
            stats["ammo_explosions"] += 1
            stats["fuel_explosions"] += 1
            stats["kills"] += 1
        elif fuzzy_contains(text, extended_ammo_fragments):
            events.append("Enemy killed by ammunition explosion")
            stats["ammo_explosions"] += 1
            stats["kills"] += 1
        elif fuzzy_contains(text, fuel_fragments):
            events.append("Enemy killed by fuel explosion")
            stats["fuel_explosions"] += 1
            stats["kills"] += 1
        else:
            events.append("Enemy killed by unspecified explosion")
            stats["unknown_events"] += 1

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
        "Ammo": ["ammo", "amme", "amm"],
        "Autoloader": ["auto"],
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

def detection_loop():
    global last_event_result, last_modules_result, game_state
    screen_width, screen_height = pyautogui.size()

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
            log("aces.exe not found. Pausing detection until process is available.", level="WARN")
            game_state = "Waiting for aces.exe"
            while not is_aces_running():
                time.sleep(2)
            log("aces.exe detected again. Resuming detection.", level="INFO")
            last_detection_time = time.time()

        battle_screenshot = pyautogui.screenshot().crop((battle_left, battle_top, battle_right, battle_bottom))
        battle_text = extract_battle_text_from_image(battle_screenshot).lower()

        if "to battle" in battle_text:
            last_battle_time = time.time()
            last_detection_time = time.time()
            log("Detected 'To Battle!' — assuming Main Menu.")
            game_state = "In Menu"
        else:
            if game_state not in ["In Game", "Game Not In Focus"]:
                game_state = "Unknown"

        gear_screenshot = pyautogui.screenshot().crop((gear_left, gear_top, gear_right, gear_bottom))
        gear_text = extract_gear_text_from_image(gear_screenshot).lower()

        if fuzzy_contains(gear_text, ["gear", "rpm", "spd", "km/h", "n"]):
            last_detection_time = time.time()

        if time.time() - last_detection_time > 20:
            game_state = "Game Not In Focus"
            time.sleep(1)
            continue

        current_time = time.time()
        if last_battle_time is None or (current_time - last_battle_time > 10):
            if fuzzy_contains(gear_text, ["gear", "rpm", "spd", "km/h", "n"]):
                game_state = "In Game"
                screenshot = pyautogui.screenshot().crop((region_left, region_top, region_right, region_bottom))
                extracted_text = extract_text_from_image(screenshot)
                log(f"Hit/Kill Region Text Detected:\n{extracted_text}")

                result = analyze_text(extracted_text)
                log(f"Analysis Result: {result}")
                last_event_result = result

                module_screenshot = pyautogui.screenshot().crop((module_left, module_top, module_right, module_bottom))
                modules_extracted_text = extract_modules_text_from_image(module_screenshot)
                log(f"Module Region Raw Text:\n{modules_extracted_text}")

                modules_result = analyze_modules_text(modules_extracted_text)
                log(f"Modules Analysis Result: {modules_result}")
                last_modules_result = modules_result

                # Sleep depending on detection results
                if ("No significant events detected" not in result or
                    "No significant modules detected" not in modules_result):
                    time.sleep(4)
                else:
                    time.sleep(1)
            else:
                log("Gear info not detected, skipping hit/kill detection.", level="WARN")
                game_state = "Unknown"
                time.sleep(1)
        else:
            log("Waiting due to recent 'To Battle!' detection...", level="INFO")
            time.sleep(1)

@app.route("/")
def index():
    global prev_stats
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Detection Dashboard</title>
        <meta http-equiv="refresh" content="1">
        <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
        <style>
            body { margin: 20px; }
            pre { background: #f8f9fa; padding: 15px; border-radius: 5px; }
            .log-container { max-height: 400px; overflow-y: scroll; }
            .status-box { padding: 15px; border-radius: 5px; background: #e9ecef; margin-bottom: 20px; }
            .stats-table td, .stats-table th { padding: 0.75rem; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="my-4">Detection Dashboard</h1>
            <div class="status-box">
                <h4>Game State: <span class="badge badge-primary">{{ game_state }}</span></h4>
                <h5>Latest Event Analysis:</h5>
                <pre>{{ last_event_result }}</pre>
                <h5>Latest Modules Analysis:</h5>
                <pre>{{ last_modules_result }}</pre>
            </div>
            <h3>Session Statistics</h3>
            <table class="table table-bordered stats-table">
                <thead class="thead-dark">
                    <tr>
                        <th>Metric</th>
                        <th>Count</th>
                    </tr>
                </thead>
                <tbody>
                    {% for metric, value, changed in rows %}
                    <tr {% if changed %} class="table-success" {% endif %}>
                        <td>{{ metric }}</td>
                        <td>{{ value }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            <div class="card mb-4">
                <div class="card-header">
                    <strong>Recent Logs</strong>
                </div>
                <div class="card-body log-container">
                    <pre>{{ logs }}</pre>
                </div>
            </div>
            <div class="card">
                <div class="card-header">
                    <strong>Additional Info</strong>
                </div>
                <div class="card-body">
                    <p>Snapshots TODO</p>
                </div>
            </div>
            <p class="mt-3 text-muted">Page refreshes every 1 second.</p>
        </div>
    </body>
    </html>
    """
    rows = []
    for metric, value in stats.items():
        changed = (prev_stats.get(metric) != value)
        rows.append((metric.capitalize().replace("_", " "), value, changed))
    prev_stats = stats.copy()

    recent_logs = "\n".join(log_store[-50:])
    return render_template_string(html_template,
                                  logs=recent_logs,
                                  game_state=game_state,
                                  last_event_result=last_event_result,
                                  last_modules_result=last_modules_result,
                                  rows=rows)

def is_tesseract_installed():
    try:
        result = subprocess.run(['tesseract', '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def is_aces_running():
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and proc.info['name'].lower() == 'aces.exe':
            return True
    return False

if __name__ == "__main__":
    # Check if Tesseract is installed
    if not is_tesseract_installed():
        print("Tesseract is not installed. Please install it and ensure it's in your PATH.")
        exit(1)

    print("Waiting for aces.exe to start...")
    while not is_aces_running():
        time.sleep(5)

    print("aces.exe detected. Starting detection loop and web server...")
    detection_thread = threading.Thread(target=detection_loop, daemon=True)
    detection_thread.start()
    app.run(host="0.0.0.0", port=5000, debug=False)