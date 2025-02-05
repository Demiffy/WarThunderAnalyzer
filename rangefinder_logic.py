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
import mss
import mss.tools

# Global grid region
GRID_REGION = (1473, 635, 432, 432)  # (left, top, width, height)

# Load map configurations from JSON file.
CONFIGS_PATH = os.path.join(os.path.dirname(__file__), "map_configs.json")
with open(CONFIGS_PATH, "r") as f:
    map_configs = json.load(f)

# OCR regions
OCR_REGION = (900, 380, 500, 30)

# Global variables
current_map = None
valid_map_detected = False
active_config = None
latest_grid_filename = None
latest_minimap_ocr_image = "screenshots/minimap_ocr/tracked_target.png"
grid_offset_x = 0
grid_offset_y = 0
latest_ocr_text = ""
latest_cell_size_m = None

# Directories for saving screenshots
DIR_GRID = os.path.join("static", "screenshots", "grid")
DIR_MINIMAP_OCR = os.path.join("static", "screenshots", "minimap_ocr")
os.makedirs(DIR_GRID, exist_ok=True)
os.makedirs(DIR_MINIMAP_OCR, exist_ok=True)

# Flags
capture_paused = False
ocr_paused = False
config_logged = False

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
    ocr_img = pyautogui.screenshot(region=region)
    ocr_gray = ocr_img.convert("L")
    text = pytesseract.image_to_string(ocr_gray, lang='eng')
    return text.strip()

def draw_infinite_grid(img, cell_period, offset_x, offset_y):
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
    global latest_grid_filename, grid_offset_x, grid_offset_y, active_config, current_map, latest_cell_size_m

    sct = mss.mss()

    while True:
        if not is_aces_in_focus():
            if not capture_paused:
                log("Game out of focus; pausing grid capture...", level="INFO", tag="RANGE")
            time.sleep(0.5)
            continue

        if state.statistics_open:
            time.sleep(0.5)
            continue

        if state.game_state == "In Menu":
            valid_map_detected = False
            active_config = None
            current_map = None
            time.sleep(0.5)
            continue

        if active_config is None:
            log("No active configuration set; waiting for valid map via OCR or manual selection...", level="INFO", tag="RANGE")
            time.sleep(0.5)
            continue

        # Capture grid region.
        grid_left, grid_top, grid_width, grid_height = GRID_REGION
        monitor = {"left": grid_left, "top": grid_top, "width": grid_width, "height": grid_height}
        timestamp = int(time.time())
        try:
            sct_img = sct.grab(monitor)
            grid_np = np.array(sct_img)
            grid_bgr = cv2.cvtColor(grid_np, cv2.COLOR_BGRA2BGR)
        except Exception as e:
            log(f"Error capturing grid region: {e}", level="ERROR", tag="RANGE")
            time.sleep(0.5)
            continue

        grid_bgr = draw_infinite_grid(grid_bgr, active_config.get("cell_block", 56), grid_offset_x, grid_offset_y)
        grid_filename = f"grid_{timestamp}.png"
        grid_filepath = os.path.join(DIR_GRID, grid_filename)
        cv2.imwrite(grid_filepath, grid_bgr)
        latest_grid_filename = f"screenshots/grid/{grid_filename}"
        cleanup_directory_by_count(DIR_GRID, max_files=10)

        if "cell_size_m" in active_config:
            latest_cell_size_m = active_config["cell_size_m"]

        time.sleep(0.5)

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
        .screenshot { width: 100%; border: 2px solid #555; }
        .img-container { padding: 10px; }
        .control-container { margin-top: 20px; }
        button, select { padding: 10px 20px; font-size: 16px; margin: 5px; }
        #offset_line, #final_offset, #current_map, #ocr_text, #cell_size { font-size: 18px; margin: 10px 0; }
    </style>
    <script>
        function fetchLatest() {
            fetch('/latest')
            .then(response => response.json())
            .then(data => {
                if(data.grid) {
                    document.getElementById('grid_img').src = '/static/' + data.grid + '?t=' + new Date().getTime();
                }
                // Reference the output image from Minimap_player.py.
                document.getElementById('minimap_ocr_processed_img').src = '/static/' + "screenshots/minimap_ocr/tracked_target.png" + '?t=' + new Date().getTime();
                document.getElementById('offset_line').innerText = "Current grid offset: (" + data.offset_x + ", " + data.offset_y + ")";
                document.getElementById('current_map').innerText = "Current map: " + data.current_map;
                document.getElementById('ocr_text').innerText = "Minimap OCR Text: " + data.ocr_text;
                document.getElementById('cell_size').innerText = "Cell size (m): " + (data.cell_size !== null ? data.cell_size : "N/A");
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
    <div class="container-fluid">
        <h1 class="my-4 text-center">Rangefinder Grid Adjustment</h1>
        <div class="row">
            <div class="col-md-4 img-container">
                <h3>Grid Region</h3>
                <img id="grid_img" class="screenshot" src="/static/{{ grid }}" alt="Grid Screenshot">
            </div>
            <div class="col-md-4 img-container">
                <h3>Minimap Target Output</h3>
                <img id="minimap_ocr_processed_img" class="screenshot" src="/static/{{ minimap_ocr_processed_image }}" alt="Minimap OCR Processed Screenshot">
            </div>
        </div>
        <div class="row control-container">
            <div class="col-md-6">
                <p id="current_map">Current map: {{ current_map }}</p>
                <p id="ocr_text">Minimap OCR Text: </p>
                <p id="cell_size">Cell size (m): N/A</p>
            </div>
            <div class="col-md-6">
                <p id="offset_line">Current grid offset: (0, 0)</p>
            </div>
        </div>
        <div class="row control-container">
            <div class="col-md-12 text-center">
                <button onclick="adjustOffset('x', 1)">Increase Offset X</button>
                <button onclick="adjustOffset('x', -1)">Decrease Offset X</button>
                <button onclick="adjustOffset('y', 1)">Increase Offset Y</button>
                <button onclick="adjustOffset('y', -1)">Decrease Offset Y</button>
            </div>
        </div>
        <div class="row control-container">
            <div class="col-md-6 text-center">
                <select id="map_select" class="form-control">
                    {% for map in maps %}
                        <option value="{{ map }}" {% if map == current_map %}selected{% endif %}>{{ map }}</option>
                    {% endfor %}
                </select>
                <br>
                <button onclick="changeMap()">Set Map</button>
            </div>
            <div class="col-md-6 text-center">
                <button onclick="bypassOCR()">Bypass OCR and Default to Frozen Pass</button>
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(RANGEFINDER_HTML,
                                  grid=latest_grid_filename if latest_grid_filename else "",
                                  minimap_ocr_original_image=latest_minimap_ocr_original if latest_minimap_ocr_original else "",
                                  minimap_ocr_processed_image=latest_minimap_ocr_processed if latest_minimap_ocr_processed else "",
                                  maps=list(map_configs.keys()),
                                  current_map=current_map if current_map else "None")

@app.route("/latest")
def latest():
    return jsonify({
        "grid": latest_grid_filename,
        "minimap_ocr_original_image": latest_minimap_ocr_original,
        "minimap_ocr_processed_image": latest_minimap_ocr_processed,
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
    global current_map, grid_offset_x, grid_offset_y, active_config, valid_map_detected, latest_cell_size_m
    map_name = request.args.get("map", "").strip()
    if map_name in map_configs:
        current_map = map_name
        active_config = map_configs[map_name]
        grid_offset_x, grid_offset_y = active_config.get("offset", (0, 0))
        valid_map_detected = True
        if "cell_size_m" in active_config:
            latest_cell_size_m = active_config["cell_size_m"]
        message = (f"Map changed to {map_name}. New settings: grid_region: {GRID_REGION}, "
                   f"cell_block: {active_config['cell_block']}, "
                   f"offset: {active_config['offset']}, cell_size_m: {latest_cell_size_m}.")
    else:
        message = f"Map '{map_name}' not found."
    return jsonify({"message": message})

@app.route("/bypass")
def bypass():
    global current_map, valid_map_detected, active_config, grid_offset_x, grid_offset_y, latest_cell_size_m
    current_map = "Frozen Pass"
    valid_map_detected = True
    active_config = map_configs["Frozen Pass"]
    grid_offset_x, grid_offset_y = active_config.get("offset", (0, 0))
    if "cell_size_m" in active_config:
        latest_cell_size_m = active_config["cell_size_m"]
    return jsonify({"message": "Bypassed OCR. Defaulted to Frozen Pass."})

def ocr_detection_loop():
    global current_map, valid_map_detected, active_config, grid_offset_x, grid_offset_y, ocr_paused, latest_ocr_text
    global latest_minimap_ocr_original, latest_minimap_ocr_processed
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
                log("In Menu: clearing active configuration.", level="INFO", tag="RANGE")
                valid_map_detected = False
                active_config = None
                current_map = None
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
            timestamp = int(time.time())
            try:
                minimap_ocr_img = pyautogui.screenshot(region=OCR_REGION)
                minimap_ocr_original_filename = f"minimap_ocr_original_{timestamp}.png"
                minimap_ocr_original_filepath = os.path.join(DIR_MINIMAP_OCR, minimap_ocr_original_filename)
                minimap_ocr_img.save(minimap_ocr_original_filepath)
                latest_minimap_ocr_original = f"screenshots/minimap_ocr/{minimap_ocr_original_filename}"

                minimap_np = np.array(minimap_ocr_img)
                target = np.array([230, 206, 120], dtype=np.uint8)
                tolerance = 60
                diff = cv2.absdiff(minimap_np, target)
                distance = np.linalg.norm(diff, axis=2)
                processed = np.where(distance < tolerance, 0, 255).astype(np.uint8)
                if len(processed.shape) == 3:
                    processed = cv2.cvtColor(processed, cv2.COLOR_RGB2GRAY)
                minimap_ocr_processed_filename = f"minimap_ocr_processed_{timestamp}.png"
                minimap_ocr_processed_filepath = os.path.join(DIR_MINIMAP_OCR, minimap_ocr_processed_filename)
                cv2.imwrite(minimap_ocr_processed_filepath, processed)
                latest_minimap_ocr_processed = f"screenshots/minimap_ocr/{minimap_ocr_processed_filename}"

                map_text = pytesseract.image_to_string(processed, lang='eng').strip()
                latest_ocr_text = map_text
            except Exception as e:
                log(f"Error capturing minimap OCR images: {e}", level="ERROR", tag="OCR")
                map_text = ""
            log(f"OCR Result (from processed image): {map_text}", level="DEBUG", tag="OCR")
            for map_name in sorted(map_configs.keys(), key=lambda x: -len(x)):
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