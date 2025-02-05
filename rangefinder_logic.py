# rangefinder_logic.py
import os
import math
import time
import threading
import re
import pyautogui
import cv2
import numpy as np
import pytesseract
from flask import Flask, render_template_string, jsonify, request
import state
from utils import is_aces_in_focus, log
import json

# Global grid region
GRID_REGION = (1473, 635, 432, 432)  # (left, top, width, height)

# Load map configurations from JSON file.
CONFIGS_PATH = os.path.join(os.path.dirname(__file__), "map_configs.json")
with open(CONFIGS_PATH, "r") as f:
    map_configs = json.load(f)

# OCR regions
OCR_REGION = (900, 380, 500, 30)
OCR_REGION2 = (1707, 1037, 200, 30)

# Global variables
current_map = None
valid_map_detected = False
active_config = None
latest_grid_filename = None
latest_ocr2_filename = None
latest_ocr2_processed_filename = None
grid_offset_x = 0
grid_offset_y = 0
latest_ocr_text = ""
latest_cell_size_m = None

# Directories for saving screenshots
DIR_GRID = os.path.join("static", "screenshots", "grid")
DIR_OCR2 = os.path.join("static", "screenshots", "ocr2")
os.makedirs(DIR_GRID, exist_ok=True)
os.makedirs(DIR_OCR2, exist_ok=True)

# Flags
capture_paused = False
ocr_paused = False
config_logged = False
cell_size_locked = False

# Custom Tesseract configuration
TESS_CONFIG = '--psm 7 -c tessedit_char_whitelist=0123456789.'

# ----- Helper Functions -----
def cleanup_directory_by_count(directory, max_files=10):
    files = [os.path.join(directory, f) for f in os.listdir(directory)
             if os.path.isfile(os.path.join(directory, f))]
    if len(files) <= max_files:
        return
    files.sort(key=lambda f: os.path.getmtime(f))
    for f in files[:-max_files]:
        try:
            os.remove(f)
        except Exception as e:
            log(f"Error deleting {f}: {e}", level="ERROR", tag="RANGE")

def ocr_map_name(region):
    """Capture the specified region and extract the map name using OCR."""
    ocr_img = pyautogui.screenshot(region=region)
    ocr_gray = ocr_img.convert("L")
    text = pytesseract.image_to_string(ocr_gray, lang='eng')
    return text.strip()

def draw_infinite_grid(img, cell_period, offset_x, offset_y):
    """
    Draw an infinite grid over the image.
    Grid lines are drawn every 'cell_period' pixels.
    The grid is shifted by the provided offsets.
    Lines are drawn with a thickness of 1.
    """
    h, w = img.shape[:2]
    n_min = math.floor((-offset_x) / cell_period)
    n_max = math.ceil((w - offset_x) / cell_period)
    for n in range(n_min, n_max + 1):
        x = int(n * cell_period + offset_x)
        cv2.line(img, (x, 0), (x, h), (0, 255, 0), 1)
    m_min = math.floor((-offset_y) / cell_period)
    m_max = math.ceil((h - offset_y) / cell_period)
    for m in range(m_min, m_max + 1):
        y = int(m * cell_period + offset_y)
        cv2.line(img, (0, y), (w, y), (0, 255, 0), 1)
    return img

# ----- Capture Loop -----
def capture_loop():
    global latest_grid_filename, latest_ocr2_filename, latest_ocr2_processed_filename
    global grid_offset_x, grid_offset_y, active_config, current_map
    global capture_paused, config_logged, latest_ocr_text, latest_cell_size_m, cell_size_locked
    while True:
        if not is_aces_in_focus():
            if not capture_paused:
                log("Game out of focus; pausing grid capture...", level="INFO", tag="RANGE")
                capture_paused = True
            time.sleep(1)
            continue
        else:
            if capture_paused:
                log("Game in focus; resuming grid capture.", level="INFO", tag="RANGE")
                capture_paused = False
                config_logged = False

        if state.statistics_open:
            if not capture_paused:
                log("Statistics open; pausing grid capture...", level="INFO", tag="RANGE")
                capture_paused = True
            time.sleep(1)
            continue
        else:
            if capture_paused and not state.statistics_open and is_aces_in_focus():
                log("Statistics closed; resuming grid capture.", level="INFO", tag="RANGE")
                capture_paused = False

        if active_config is None:
            log("No active configuration set; waiting for valid map via OCR or manual selection...", level="INFO", tag="RANGE")
            time.sleep(2)
            continue

        if not config_logged:
            log(f"[{current_map}] Using cell_period: {active_config.get('cell_block', 56)} with offsets ({grid_offset_x}, {grid_offset_y})",
                level="INFO", tag="RANGE")
            config_logged = True

        # Capture grid region and draw grid
        grid_left, grid_top, grid_width, grid_height = GRID_REGION
        cell_period = active_config.get("cell_block", 56)
        timestamp = int(time.time())
        grid_img = pyautogui.screenshot(region=(grid_left, grid_top, grid_width, grid_height))
        grid_np = np.array(grid_img)
        grid_bgr = cv2.cvtColor(grid_np, cv2.COLOR_RGB2BGR)
        grid_bgr = draw_infinite_grid(grid_bgr, cell_period, grid_offset_x, grid_offset_y)
        grid_filename = f"grid_{timestamp}.png"
        grid_filepath = os.path.join(DIR_GRID, grid_filename)
        cv2.imwrite(grid_filepath, grid_bgr)
        latest_grid_filename = f"screenshots/grid/{grid_filename}"
        cleanup_directory_by_count(DIR_GRID, max_files=10)

        # --- OCR region capture for cell size and preview images ---
        if not cell_size_locked:
            try:
                new_ocr_img = pyautogui.screenshot(region=OCR_REGION2)
                ocr2_filename = f"ocr2_{timestamp}.png"
                ocr2_filepath = os.path.join(DIR_OCR2, ocr2_filename)
                new_ocr_img.save(ocr2_filepath)
                latest_ocr2_filename = f"screenshots/ocr2/{ocr2_filename}"

                ocr_bgr = np.array(new_ocr_img)
                mask = cv2.inRange(ocr_bgr, (0, 0, 0), (50, 50, 50))
                processed = cv2.bitwise_not(mask)

                processed_filename = f"ocr2_processed_{timestamp}.png"
                processed_filepath = os.path.join(DIR_OCR2, processed_filename)
                cv2.imwrite(processed_filepath, processed)
                latest_ocr2_processed_filename = f"screenshots/ocr2/{processed_filename}"

                ocr_result = pytesseract.image_to_string(processed, lang='eng', config=TESS_CONFIG).strip()
                latest_ocr_text = ocr_result
                match = re.search(r'(\d+(\.\d+)?)', ocr_result)
                if match:
                    value = float(match.group(1))
                    if value >= 100:
                        latest_cell_size_m = value
                        cell_size_locked = True
                        log(f"Detected solid cell size: {latest_cell_size_m} m (locked)", level="INFO", tag="OCR2")
                    else:
                        log(f"Detected cell size ({value} m) is below threshold", level="WARN", tag="OCR2")
                else:
                    log(f"No valid cell size found in OCR region: '{ocr_result}'", level="WARN", tag="OCR2")
            except Exception as e:
                log(f"Error in new OCR region capture: {e}", level="ERROR", tag="OCR2")

        time.sleep(2)

# ----- Flask Web Server for Rangefinder -----
app = Flask(__name__, static_url_path='/static', static_folder='static')

RANGEFINDER_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Rangefinder Grid Adjustment</title>
    <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootswatch/4.5.2/darkly/bootstrap.min.css">
    <style>
        body { margin: 20px; background-color: #2b2b2b; color: #ddd; }
        .screenshot { max-width: 90%; border: 2px solid #555; }
        button, select { padding: 10px 20px; font-size: 16px; margin: 5px; }
        #offset_line, #final_offset, #current_map, #ocr_text, #cell_size { font-size: 18px; margin: 10px; }
    </style>
    <script>
        function fetchLatest() {
            fetch('/latest')
            .then(response => response.json())
            .then(data => {
                if(data.grid) {
                    document.getElementById('grid_img').src = '/static/' + data.grid + '?t=' + new Date().getTime();
                }
                if(data.ocr2_image) {
                    document.getElementById('ocr2_img').src = '/static/' + data.ocr2_image + '?t=' + new Date().getTime();
                }
                if(data.ocr2_processed_image) {
                    document.getElementById('ocr2_processed_img').src = '/static/' + data.ocr2_processed_image + '?t=' + new Date().getTime();
                }
                document.getElementById('offset_line').innerText = "Current grid offset: (" + data.offset_x + ", " + data.offset_y + ")";
                document.getElementById('final_offset').innerText = "offset: (" + data.offset_x + ", " + data.offset_y + ")";
                document.getElementById('current_map').innerText = "Current map: " + data.current_map;
                document.getElementById('ocr_text').innerText = "OCR Region2 Text: " + data.ocr_text;
                document.getElementById('cell_size').innerText = "Detected cell size (m): " + (data.cell_size !== null ? data.cell_size : "N/A");
            })
            .catch(err => console.error("Error fetching latest:", err));
        }
        function adjustOffset(axis, delta) {
            fetch('/adjust_offset?axis=' + axis + '&delta=' + delta)
            .then(response => response.json())
            .then(data => { alert(data.message); fetchLatest(); })
            .catch(err => console.error("Error adjusting offset:", err));
        }
        function changeMap() {
            let mapName = document.getElementById('map_select').value;
            fetch('/set_map?map=' + encodeURIComponent(mapName))
            .then(response => response.json())
            .then(data => { alert(data.message); fetchLatest(); })
            .catch(err => console.error("Error changing map:", err));
        }
        function bypassOCR() {
            fetch('/bypass')
            .then(response => response.json())
            .then(data => { alert(data.message); fetchLatest(); })
            .catch(err => console.error("Error bypassing OCR:", err));
        }
        setInterval(fetchLatest, 1000);
        window.onload = fetchLatest;
    </script>
</head>
<body>
    <div class="container">
        <h1 class="my-4">Rangefinder Grid Adjustment</h1>
        <p id="current_map">Current map: {{ current_map }}</p>
        <h2>Grid Region</h2>
        <img id="grid_img" class="screenshot" src="/static/{{ grid }}" alt="Grid Screenshot">
        <h2>OCR Region2 Original Preview</h2>
        <img id="ocr2_img" class="screenshot" src="/static/{{ ocr2_image }}" alt="OCR2 Region Screenshot">
        <h2>OCR Region2 Processed Preview</h2>
        <img id="ocr2_processed_img" class="screenshot" src="/static/{{ ocr2_processed_image }}" alt="OCR2 Processed Screenshot">
        <p id="ocr_text">OCR Region2 Text: </p>
        <p id="cell_size">Detected cell size (m): N/A</p>
        <h2>Adjust Grid Offsets</h2>
        <p id="offset_line">Current grid offset: (0, 0)</p>
        <button onclick="adjustOffset('x', 1)">Increase Offset X</button>
        <button onclick="adjustOffset('x', -1)">Decrease Offset X</button>
        <button onclick="adjustOffset('y', 1)">Increase Offset Y</button>
        <button onclick="adjustOffset('y', -1)">Decrease Offset Y</button>
        <h2>Change Map</h2>
        <select id="map_select">
            {% for map in maps %}
                <option value="{{ map }}" {% if map == current_map %}selected{% endif %}>{{ map }}</option>
            {% endfor %}
        </select>
        <button onclick="changeMap()">Set Map</button>
        <br>
        <button onclick="bypassOCR()">Bypass OCR and Default to Frozen Pass</button>
        <br><br>
        <h3>Final Offset String (copy this into your map config):</h3>
        <p id="final_offset">offset: (0, 0)</p>
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(RANGEFINDER_HTML,
                                  grid=latest_grid_filename if latest_grid_filename else "",
                                  ocr2_image=latest_ocr2_filename if latest_ocr2_filename else "",
                                  ocr2_processed_image=latest_ocr2_processed_filename if latest_ocr2_processed_filename else "",
                                  maps=list(map_configs.keys()),
                                  current_map=current_map if current_map else "None")

@app.route("/latest")
def latest():
    return jsonify({
        "grid": latest_grid_filename,
        "ocr2_image": latest_ocr2_filename,
        "ocr2_processed_image": latest_ocr2_processed_filename,
        "offset_x": grid_offset_x,
        "offset_y": grid_offset_y,
        "current_map": current_map if current_map else "None",
        "ocr_text": latest_ocr_text,
        "cell_size": latest_cell_size_m
    })

@app.route("/adjust_offset")
def adjust_offset():
    global grid_offset_x, grid_offset_y
    try:
        axis = request.args.get("axis", "").lower()
        delta = int(request.args.get("delta", 0))
        if axis == "x":
            grid_offset_x += delta
        elif axis == "y":
            grid_offset_y += delta
        message = f"Grid offsets updated: ({grid_offset_x}, {grid_offset_y})"
    except Exception as e:
        message = f"Error updating offsets: {e}"
    return jsonify({"message": message})

@app.route("/set_map")
def set_map():
    global current_map, grid_offset_x, grid_offset_y, active_config, valid_map_detected
    map_name = request.args.get("map", "").strip()
    if map_name in map_configs:
        current_map = map_name
        active_config = map_configs[map_name]
        grid_offset_x, grid_offset_y = active_config.get("offset", (0, 0))
        valid_map_detected = True
        message = (f"Map changed to {map_name}. New settings: grid_region: {GRID_REGION}, "
                   f"cell_block: {active_config['cell_block']}, "
                   f"offset: {active_config['offset']}.")
    else:
        message = f"Map '{map_name}' not found."
    return jsonify({"message": message})

@app.route("/bypass")
def bypass():
    global current_map, valid_map_detected, active_config, grid_offset_x, grid_offset_y
    current_map = "Frozen Pass"
    valid_map_detected = True
    active_config = map_configs["Frozen Pass"]
    grid_offset_x, grid_offset_y = active_config.get("offset", (0, 0))
    return jsonify({"message": "Bypassed OCR. Defaulted to Frozen Pass."})

def ocr_detection_loop():
    global current_map, valid_map_detected, active_config, grid_offset_x, grid_offset_y, ocr_paused, cell_size_locked
    while True:
        if state.statistics_open:
            log("Statistics open; pausing minimap name detection.", level="INFO", tag="OCR")
            time.sleep(2)
            continue
        if state.main_menu_open:
            log("Main Menu detected; pausing minimap name detection.", level="INFO", tag="OCR")
            time.sleep(2)
            continue

        if state.game_state == "In Menu":
            if valid_map_detected:
                log("To Battle text detected; clearing active configuration.", level="INFO", tag="RANGE")
                valid_map_detected = False
                active_config = None
                current_map = None
                cell_size_locked = False
            if not ocr_paused:
                ocr_paused = True
            time.sleep(2)
            continue
        else:
            if ocr_paused:
                log("Game in focus; resuming OCR detection.", level="INFO", tag="OCR")
                ocr_paused = False

        if is_aces_in_focus():
            log("Game in focus; running OCR to detect map name...", level="INFO", tag="OCR")
            map_text = ocr_map_name(OCR_REGION)
            log(f"OCR Result: {map_text}", level="DEBUG", tag="OCR")
            for map_name in map_configs.keys():
                if map_name.lower() in map_text.lower():
                    current_map = map_name
                    valid_map_detected = True
                    active_config = map_configs[map_name]
                    grid_offset_x, grid_offset_y = active_config.get("offset", (0, 0))
                    log(f"Detected map: {current_map}", level="INFO", tag="OCR")
                    break
            if not valid_map_detected:
                log("Map name not recognized. Retrying in 2 seconds...", level="WARN", tag="OCR")
        time.sleep(2)

def start_rangefinder():
    ocr_thread = threading.Thread(target=ocr_detection_loop, daemon=True)
    ocr_thread.start()
    time.sleep(5)
    global current_map, valid_map_detected, active_config, grid_offset_x, grid_offset_y
    if not valid_map_detected:
        log("No valid map detected by OCR; waiting indefinitely for a valid map.", level="WARN", tag="RANGE")
    else:
        log(f"Using settings for {current_map}: cell_block: {active_config['cell_block']}", level="INFO", tag="RANGE")
    capture_thread = threading.Thread(target=capture_loop, daemon=True)
    capture_thread.start()
    app.run(host="0.0.0.0", port=5001, debug=False)

if __name__ == "__main__":
    start_rangefinder()