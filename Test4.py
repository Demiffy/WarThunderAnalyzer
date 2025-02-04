import os
import math
import time
import threading
import pyautogui
import cv2
import numpy as np
import pytesseract
from flask import Flask, render_template_string, jsonify, request

# Global grid region
GRID_REGION = (1473, 637, 432, 432)  # (left, top, width, height)

# Map configurations
map_configs = {
    "Poland": {
        "grid_size_m": 350,
        "cell_block": 56,   # 54 interior + 2 border = 56 pixels
        "offset": (1, -3)
    },
    "Frozen Pass": {
        "grid_size_m": 150,
        "cell_block": 61,   # 59 interior + 2 border = 61 pixels
        "offset": (1, -3)
    }
}

# OCR region for map name detection
OCR_REGION = (900, 380, 500, 30)

# Global variables
current_map = None
valid_map_detected = False
active_config = None
latest_grid_filename = None
grid_offset_x = 0
grid_offset_y = 0

# Directories for screenshots
DIR_GRID = os.path.join("static", "screenshots", "grid")
os.makedirs(DIR_GRID, exist_ok=True)

# ===== Helper Functions =====
def cleanup_directory_by_count(directory, max_files=10):
    files = [os.path.join(directory, f) for f in os.listdir(directory) 
             if os.path.isfile(os.path.join(directory, f))]
    if len(files) <= max_files:
        return
    files.sort(key=lambda f: os.path.getmtime(f))
    for f in files[:-max_files]:
        try:
            os.remove(f)
            print(f"Deleted old file: {os.path.basename(f)}")
        except Exception as e:
            print(f"Error deleting {f}: {e}")

def ocr_map_name(region):
    """Capture the region and extract the map name using OCR."""
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

# ===== Capture Loop =====
def capture_loop():
    global latest_grid_filename, grid_offset_x, grid_offset_y, active_config, current_map
    while True:
        config = active_config
        grid_left, grid_top, grid_width, grid_height = GRID_REGION
        cell_period = config.get("cell_block", 56)
        print(f"[{current_map}] Using cell_period: {cell_period} with offsets ({grid_offset_x}, {grid_offset_y})")
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
        print(f"Saved Grid screenshot: {grid_filename}")
        time.sleep(2)

# ===== OCR Detection Loop =====
def ocr_detection_loop():
    global current_map, valid_map_detected, active_config, grid_offset_x, grid_offset_y
    while not valid_map_detected:
        print("Running OCR to detect map name...")
        map_text = ocr_map_name(OCR_REGION)
        print("OCR Result:", map_text)
        for map_name in map_configs.keys():
            if map_name.lower() in map_text.lower():
                current_map = map_name
                valid_map_detected = True
                active_config = map_configs[map_name]
                grid_offset_x, grid_offset_y = active_config.get("offset", (0, 0))
                print(f"Detected map: {current_map}")
                break
        if not valid_map_detected:
            print("Map name not recognized. Retrying in 2 seconds...")
            time.sleep(2)

# ===== Flask Web Server =====
app = Flask(__name__, static_url_path='/static', static_folder='static')

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Grid Adjustment</title>
    <style>
      body { background-color: #222; color: #eee; font-family: sans-serif; text-align: center; }
      h1 { margin-top: 20px; }
      .screenshot { display: block; margin: 20px auto; max-width: 90%; border: 2px solid #555; }
      button, select { padding: 10px 20px; font-size: 16px; margin: 5px; }
      #offset_line, #final_offset, #current_map { font-size: 18px; margin: 10px; }
    </style>
    <script>
        function fetchLatest() {
            fetch('/latest')
            .then(response => response.json())
            .then(data => {
                if(data.grid) {
                    document.getElementById('grid_img').src = '/static/' + data.grid + '?t=' + new Date().getTime();
                }
                document.getElementById('offset_line').innerText = "Current grid offset: (" + data.offset_x + ", " + data.offset_y + ")";
                document.getElementById('final_offset').innerText = "offset: (" + data.offset_x + ", " + data.offset_y + ")";
                document.getElementById('current_map').innerText = "Current map: " + data.current_map;
            })
            .catch(error => console.error('Error fetching latest:', error));
        }
        function adjustOffset(axis, delta) {
            fetch('/adjust_offset?axis=' + axis + '&delta=' + delta)
            .then(response => response.json())
            .then(data => {
                alert(data.message);
                fetchLatest();
            })
            .catch(error => console.error('Error adjusting offset:', error));
        }
        function changeMap() {
            let mapName = document.getElementById('map_select').value;
            fetch('/set_map?map=' + encodeURIComponent(mapName))
            .then(response => response.json())
            .then(data => {
                alert(data.message);
                fetchLatest();
            })
            .catch(error => console.error('Error changing map:', error));
        }
        function bypassOCR() {
            fetch('/bypass')
            .then(response => response.json())
            .then(data => {
                alert(data.message);
                fetchLatest();
            })
            .catch(error => console.error('Error bypassing OCR:', error));
        }
        setInterval(fetchLatest, 1000);
        window.onload = fetchLatest;
    </script>
</head>
<body>
    <h1>Grid Adjustment</h1>
    <p id="current_map">Current map: {{ current_map }}</p>
    <h2>Grid Region</h2>
    <img id="grid_img" class="screenshot" src="/static/{{ grid }}" alt="Grid Screenshot">
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
    <br><br>
    <button onclick="bypassOCR()">Bypass OCR and Default to Frozen Pass</button>
    <br><br>
    <h3>Final Offset String (copy this into your map config):</h3>
    <p id="final_offset">offset: (0, 0)</p>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE,
                                  grid=latest_grid_filename if latest_grid_filename else "",
                                  maps=list(map_configs.keys()),
                                  current_map=current_map if current_map else "None")

@app.route("/latest")
def latest():
    return jsonify({
        "grid": latest_grid_filename,
        "offset_x": grid_offset_x,
        "offset_y": grid_offset_y,
        "current_map": current_map if current_map else "None"
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
    global current_map, grid_offset_x, grid_offset_y, active_config
    map_name = request.args.get("map", "").strip()
    if map_name in map_configs:
        current_map = map_name
        active_config = map_configs[map_name]
        grid_offset_x, grid_offset_y = active_config.get("offset", (0, 0))
        message = (f"Map changed to {map_name}. New settings: grid_region: {GRID_REGION}, "
                   f"grid_size_m: {active_config['grid_size_m']}, cell_block: {active_config['cell_block']}, "
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
    global current_map, valid_map_detected, active_config, grid_offset_x, grid_offset_y
    while not valid_map_detected:
        print("Running OCR to detect map name...")
        map_text = ocr_map_name(OCR_REGION)
        print("OCR Result:", map_text)
        for map_name in map_configs.keys():
            if map_name.lower() in map_text.lower():
                current_map = map_name
                valid_map_detected = True
                active_config = map_configs[map_name]
                grid_offset_x, grid_offset_y = active_config.get("offset", (0, 0))
                print(f"Detected map: {current_map}")
                break
        if not valid_map_detected:
            print("Map name not recognized. Retrying in 2 seconds...")
            time.sleep(2)

def main():
    global current_map, active_config, grid_offset_x, grid_offset_y
    ocr_thread = threading.Thread(target=ocr_detection_loop, daemon=True)
    ocr_thread.start()
    time.sleep(5)
    if not current_map:
        current_map = "Frozen Pass"
        valid_map_detected = True
        active_config = map_configs[current_map]
        grid_offset_x, grid_offset_y = active_config.get("offset", (0, 0))
        print("No valid map detected by OCR; defaulting to Frozen Pass.")
    print(f"Using settings for {current_map}: grid_region: {GRID_REGION}, grid_size_m: {active_config['grid_size_m']}, cell_block: {active_config['cell_block']}")
    capture_thread = threading.Thread(target=capture_loop, daemon=True)
    capture_thread.start()
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    main()