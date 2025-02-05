import os
import time
import math
import json
import threading
import re
import pyautogui
import cv2
import numpy as np
import pytesseract
from flask import Flask, render_template_string, jsonify, request
import mss
import mss.tools
import state
from utils import is_aces_in_focus, log

# -----------------------------------------------------------
# Global Regions and Configurations
# -----------------------------------------------------------

GRID_REGION = (1473, 635, 432, 432)  # (left, top, width, height)
OCR_REGION = (900, 380, 500, 30)

# Load map configurations from JSON file.
CONFIGS_PATH = os.path.join(os.path.dirname(__file__), "map_configs.json")
with open(CONFIGS_PATH, "r") as f:
    map_configs = json.load(f)

# Directories for saving screenshots
DIR_GRID = os.path.join("static", "screenshots", "grid")
DIR_MINIMAP_OCR = os.path.join("static", "screenshots", "minimap_ocr")
os.makedirs(DIR_GRID, exist_ok=True)
os.makedirs(DIR_MINIMAP_OCR, exist_ok=True)

# Global variables for rangefinder logic
current_map = None
valid_map_detected = False
active_config = None
latest_grid_filename = None

OUTPUT_IMAGE_PATH = "static/screenshots/minimap_ocr/tracked_target.png"
grid_offset_x = 0
grid_offset_y = 0
latest_ocr_text = ""
latest_cell_size_m = None

# Flags
capture_paused = False
ocr_paused = False
config_logged = False

# Custom Tesseract configuration
TESS_CONFIG = '--psm 7 -c tessedit_char_whitelist=0123456789.'

# -----------------------------------------------------------
# Minimap Tracking Functions (Player & Ping Detection)
# -----------------------------------------------------------

# Player colors
hex_colors = [
    "f2c52f", "caa21f", "f4c832", "f8d970", "c6a228",
    "8f7520", "f1ca46", "f3d15d", "f4c730", "f0c42f",
    "f2c530", "c39f26", "93781d", "6d5a15",
    "9b7c18", "f7d35a", "f6d050", "f7d563", "e0b628",
    "f5c830", "f5c937", "b59019"
]

# Ping colors
ping_hex_colors = [
    "d8d807", "d6d607", "d0d007", "d1d107", "c8c807", "adad06", "b9b906", "bebe06"
]

def hex_to_bgr(hex_str):
    r = int(hex_str[0:2], 16)
    g = int(hex_str[2:4], 16)
    b = int(hex_str[4:6], 16)
    return np.array([b, g, r], dtype=np.uint8)

target_colors = [hex_to_bgr(h) for h in hex_colors]
ping_target_colors = [hex_to_bgr(h) for h in ping_hex_colors]

tolerance = 4
max_radius = 10

def process_image(image):
    """Process image for player detection; return image copy and a binary mask."""
    output = image.copy()
    h, w, _ = image.shape
    reshaped = image.reshape(-1, 3)
    mask = np.zeros((reshaped.shape[0],), dtype=bool)
    for target in target_colors:
        diff = reshaped.astype(np.int16) - target.astype(np.int16)
        dist = np.linalg.norm(diff, axis=1)
        mask |= (dist < tolerance)
    output.reshape(-1, 3)[mask] = [0, 0, 255]
    return output, mask

def process_ping(image):
    """Process image for ping detection; return image copy and binary mask."""
    output = image.copy()
    h, w, _ = image.shape
    reshaped = image.reshape(-1, 3)
    ping_mask = np.zeros((reshaped.shape[0],), dtype=bool)
    for target in ping_target_colors:
        diff = reshaped.astype(np.int16) - target.astype(np.int16)
        dist = np.linalg.norm(diff, axis=1)
        ping_mask |= (dist < tolerance)
    return output, ping_mask

def get_enclosing_circle(mask, image_shape):
    """Return center, radius, and count of detected pixels using cv2.minEnclosingCircle."""
    h, w = image_shape[:2]
    mask_2d = mask.reshape(h, w).astype(np.uint8)
    points = cv2.findNonZero(mask_2d)
    if points is not None:
        center, radius = cv2.minEnclosingCircle(points)
        center = (int(center[0]), int(center[1]))
        radius = int(radius)
        if radius > max_radius:
            radius = max_radius
        count = points.shape[0]
        return center, radius, count
    else:
        return None, None, 0

def draw_filled_circle(image, center, radius, color=(0, 0, 255)):
    output = image.copy()
    if center is not None and radius is not None:
        cv2.circle(output, center, radius, color, -1)
    return output

def overlay_text(image, text, color=(255, 255, 255), position=(10, 30)):
    output = image.copy()
    cv2.putText(output, text, position, cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
    return output

# Tracking parameters for minimap detection
prev_center = None
prev_count = 0
stable_count = 0
stable_threshold = 3
distance_threshold = 20
min_count_threshold = 2

# A variable for storing the most recent pause message (to avoid log spam)
_last_pause_msg = None

def write_placeholder():
    """Write a placeholder image when tracking is paused."""
    placeholder = np.zeros((GRID_REGION[3], GRID_REGION[2], 3), dtype=np.uint8)
    placeholder = overlay_text(placeholder, "Tracking paused", color=(0, 0, 255), position=(10, 30))
    cv2.imwrite(OUTPUT_IMAGE_PATH, placeholder)
    log("Wrote placeholder image (Tracking paused).", level="INFO", tag="COMBINED")

# -----------------------------------------------------------
# Combined Capture Loop (Tracking + Grid Overlay)
# -----------------------------------------------------------
def combined_loop():
    """
    Capture the region, perform player/ping detection, overlay tracking markers,
    then draw grid lines (from the active map configuration) onto the image.
    Save the final combined image to OUTPUT_IMAGE_PATH.
    """
    global prev_center, prev_count, stable_count, _last_pause_msg
    global grid_offset_x, grid_offset_y, active_config, current_map, valid_map_detected

    with mss.mss() as sct:
        monitor = {"left": GRID_REGION[0], "top": GRID_REGION[1], "width": GRID_REGION[2], "height": GRID_REGION[3]}
        while True:
            if (not is_aces_in_focus()) or state.statistics_open or state.main_menu_open or (state.game_state == "In Menu"):
                msg = f"Pausing combined tracking. Focus={is_aces_in_focus()}, stats={state.statistics_open}, game_state={state.game_state}"
                if _last_pause_msg != msg:
                    log(msg, level="INFO", tag="COMBINED")
                    _last_pause_msg = msg
                write_placeholder()
                time.sleep(1)
                continue
            else:
                _last_pause_msg = None

            sct_img = sct.grab(monitor)
            img = cv2.cvtColor(np.array(sct_img), cv2.COLOR_BGRA2BGR)

            # --- Player Detection ---
            processed_img, mask = process_image(img)
            center, radius, count = get_enclosing_circle(mask, img.shape)
            if count > 0:
                msg = f"Target seen: {count} pixels"
                text_color = (255, 255, 255)
            else:
                msg = "No target pixels"
                text_color = (0, 0, 255)

            if count < min_count_threshold:
                prev_center = None
                prev_count = 0
                stable_count = 0

            if center is not None:
                if prev_center is None:
                    prev_center = center
                    prev_count = count
                    stable_count = 1
                    log(f"Initial detection: center {center} with count {count}", level="INFO", tag="COMBINED")
                else:
                    dist = np.linalg.norm(np.array(center) - np.array(prev_center))
                    if dist > distance_threshold:
                        if count > 1.5 * prev_count:
                            stable_count += 1
                            if stable_count >= stable_threshold:
                                prev_center = center
                                prev_count = count
                                stable_count = 0
                                log(f"Updated tracked center to {center} with count {count}", level="INFO", tag="COMBINED")
                        else:
                            center = prev_center
                            radius = int(prev_count / 10)
                            stable_count = 0
                    else:
                        prev_center = center
                        prev_count = count
                        stable_count = 0
            else:
                prev_center = None
                prev_count = 0
                stable_count = 0

            circled_img = draw_filled_circle(processed_img, center, radius)
            output_img = overlay_text(circled_img, msg, color=text_color, position=(10, 30))

            # --- Ping Detection ---
            def process_ping_local(image):
                out = image.copy()
                h, w, _ = image.shape
                reshaped = image.reshape(-1, 3)
                ping_mask = np.zeros((reshaped.shape[0],), dtype=bool)
                for target in ping_target_colors:
                    diff = reshaped.astype(np.int16) - target.astype(np.int16)
                    dist = np.linalg.norm(diff, axis=1)
                    ping_mask |= (dist < tolerance)
                return out, ping_mask

            _, ping_mask = process_ping_local(img)
            ping_center, ping_radius, ping_count = get_enclosing_circle(ping_mask, img.shape)
            if ping_count > 0:
                output_img = draw_filled_circle(output_img, ping_center, ping_radius, color=(0, 255, 255))
                if center is not None and ping_center is not None:
                    cv2.line(output_img, ping_center, center, (255, 255, 255), 2)
                    dx = ping_center[0] - center[0]
                    dy = ping_center[1] - center[1]
                    pixel_distance = math.sqrt(dx * dx + dy * dy)
                    active_map = getattr(state, "current_map", None)
                    if active_map not in map_configs:
                        active_map = "Frozen Pass"
                    config = map_configs[active_map]
                    conversion_factor = config["cell_size_m"] / config["cell_block"]
                    range_m = pixel_distance * conversion_factor
                    range_text = f"Range: {range_m:.2f} m"
                    cv2.putText(output_img, range_text, (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    log(f"Calculated range: {range_text} (Pixel distance: {pixel_distance:.2f}, Conversion factor: {conversion_factor:.4f})",
                        level="INFO", tag="COMBINED")

            if active_config is not None:
                output_img = draw_infinite_grid(output_img, active_config.get("cell_block", 56), grid_offset_x, grid_offset_y)

            cv2.imwrite(OUTPUT_IMAGE_PATH, output_img)
            time.sleep(0.1)

# -----------------------------------------------------------
# Rangefinder OCR and Flask Web Server
# -----------------------------------------------------------
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

def ocr_detection_loop():
    """
    Continuously capture the OCR region to detect the current map name.
    If a map name is recognized, update the active configuration and grid offsets.
    """
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
                tol = 60
                diff = cv2.absdiff(minimap_np, target)
                distance = np.linalg.norm(diff, axis=2)
                processed = np.where(distance < tol, 0, 255).astype(np.uint8)
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

# -----------------------------------------------------------
# Flask Web Server for Rangefinder Interface
# -----------------------------------------------------------
app = Flask(__name__, static_url_path='/static', static_folder='static')

RANGEFINDER_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Rangefinder Dashboard</title>
    <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootswatch/4.5.2/darkly/bootstrap.min.css">
    <style>
        body { margin: 20px; background-color: #2b2b2b; color: #ddd; }
        .screenshot { width: 50%; border: 2px solid #555; margin-bottom: 20px; }
        .info-panel { margin-top: 20px; }
        .info-panel p { font-size: 18px; margin: 5px 0; }
        .control-panel { margin-top: 20px; }
    </style>
    <script>
        function fetchLatest() {
            fetch('/latest')
            .then(response => response.json())
            .then(data => {
                if(data.grid) {
                    document.getElementById('combined_img').src = data.grid + '?t=' + new Date().getTime();
                }
                document.getElementById('current_map').innerText = "Current Map: " + data.current_map;
                document.getElementById('ocr_text').innerText = "OCR Text: " + data.ocr_text;
                document.getElementById('cell_size').innerText = "Cell Size (m): " + (data.cell_size !== null ? data.cell_size : "N/A");
                document.getElementById('offset_line').innerText = "Grid Offset: (" + data.offset_x + ", " + data.offset_y + ")";
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
        <h1 class="text-center my-4">Rangefinder Dashboard</h1>
        <div class="row">
            <div class="col-md-12">
                <img id="combined_img" class="screenshot" src="{{ grid }}" alt="Combined Output">
            </div>
        </div>
        <div class="row info-panel">
            <div class="col-md-3">
                <p id="current_map">Current Map: None</p>
            </div>
            <div class="col-md-3">
                <p id="ocr_text">OCR Text: </p>
            </div>
            <div class="col-md-3">
                <p id="cell_size">Cell Size (m): N/A</p>
            </div>
            <div class="col-md-3">
                <p id="offset_line">Grid Offset: (0, 0)</p>
            </div>
        </div>
        <div class="row control-panel">
            <div class="col-md-6">
                <div class="btn-group" role="group">
                    <button type="button" class="btn btn-primary" onclick="adjustOffset('x', 1)">Offset X +</button>
                    <button type="button" class="btn btn-primary" onclick="adjustOffset('x', -1)">Offset X -</button>
                    <button type="button" class="btn btn-primary" onclick="adjustOffset('y', 1)">Offset Y +</button>
                    <button type="button" class="btn btn-primary" onclick="adjustOffset('y', -1)">Offset Y -</button>
                </div>
            </div>
            <div class="col-md-6">
                <div class="input-group">
                    <select id="map_select" class="custom-select">
                        {% for map in maps %}
                            <option value="{{ map }}" {% if map == current_map %}selected{% endif %}>{{ map }}</option>
                        {% endfor %}
                    </select>
                    <div class="input-group-append">
                        <button class="btn btn-secondary" type="button" onclick="changeMap()">Set Map</button>
                    </div>
                </div>
                <br>
                <button class="btn btn-warning" onclick="bypassOCR()">Bypass OCR (Default Frozen Pass)</button>
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(RANGEFINDER_HTML,
                                  grid=OUTPUT_IMAGE_PATH,
                                  maps=list(map_configs.keys()),
                                  current_map=current_map if current_map else "None")

@app.route("/latest")
def latest():
    return jsonify({
        "grid": OUTPUT_IMAGE_PATH,
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

def start_rangefinder():
    ocr_thread = threading.Thread(target=ocr_detection_loop, daemon=True)
    ocr_thread.start()
    time.sleep(5)
    combined_thread = threading.Thread(target=combined_loop, daemon=True)
    combined_thread.start()
    app.run(host="0.0.0.0", port=5001, debug=False)

# -----------------------------------------------------------
# Main Entry Point: Start Combined Tracking and Rangefinder
# -----------------------------------------------------------
if __name__ == "__main__":
    start_rangefinder()