import os
import math
import time
import threading
import pyautogui
import cv2
import numpy as np
from PIL import Image, ImageTk
import pytesseract
from flask import Flask, render_template_string, jsonify, request

# ===== Map Configurations =====
map_configs = {
    "Frozen Pass": {
        "grid_region": (1473, 637, 432, 432),
        "grid_size_m": 180,
        "cell_block": 61,
        "offset": (1, -3)
    },
    "Battle of Hürtgen Forest": {
        "grid_region": (1473, 637, 432, 432),
        "grid_size_m": 225,
        "cell_block": 62,
        "offset": (-1, -5)
    },
    "Poland": {
        "grid_region": (1473, 637, 432, 432),
        "grid_size_m": 350,
        "cell_block": 56,
        "offset": (0, 0)
    }
}

# ===== OCR Region for Map Name =====
ocr_region = (900, 380, 500, 30)

# ===== Grid Settings =====
LINE_THICKNESS = 1

# ===== Color Detection Settings =====
GRID_COUNT = 7
player_tolerance = 10
ping_tolerance = 5

player_colors = [
    np.array([44, 187, 229]),
    np.array([15, 83, 105]),
    np.array([50, 199, 244]),
    np.array([92, 211, 247]),
    np.array([38, 158, 194]),
    np.array([72, 189, 223]),
    np.array([66, 189, 226]),
    np.array([51, 200, 244]),
    np.array([38, 162, 199]),
    np.array([38, 160, 197]),
    np.array([115, 218, 248])
]

ping_colors = [
    np.array([7, 209, 209]),
    np.array([7, 213, 213]),
    np.array([7, 207, 207]),
    np.array([6, 187, 187]),
    np.array([7, 202, 202])
]

# ===== Global Variables =====
current_map = None
valid_map_detected = False
latest_ocr_filename = None
latest_grid_filename = None
grid_offset_x = 0
grid_offset_y = 0

# ===== Directories for Screenshots =====
DIR_OCR = os.path.join("static", "screenshots", "ocr")
DIR_GRID = os.path.join("static", "screenshots", "grid")
os.makedirs(DIR_OCR, exist_ok=True)
os.makedirs(DIR_GRID, exist_ok=True)

# ===== Helper Functions =====
def ocr_map_name(region):
    """Capture the specified region and use OCR to extract the map name."""
    ocr_img = pyautogui.screenshot(region=region)
    ocr_gray = ocr_img.convert("L")
    text = pytesseract.image_to_string(ocr_gray, lang='eng')
    return text.strip()

def create_mask(image, colors, tol):
    """Create a binary mask where pixels are within tol of any given color."""
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    for color in colors:
        diff = np.abs(image.astype(np.int16) - color)
        current_mask = np.all(diff < tol, axis=-1)
        mask = cv2.bitwise_or(mask, (current_mask.astype(np.uint8) * 255))
    return mask

def get_min_enclosing_circle(mask):
    """
    Find contours from the mask and return the center and radius of the minimum enclosing circle
    covering the significant points.
    """
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, None
    areas = [cv2.contourArea(cnt) for cnt in contours]
    max_area = max(areas)
    significant_contours = [cnt for cnt in contours if cv2.contourArea(cnt) >= 0.5 * max_area]
    if not significant_contours:
        significant_contours = contours
    all_points = np.vstack(significant_contours)
    center, radius = cv2.minEnclosingCircle(all_points)
    return (int(center[0]), int(center[1])), int(radius)

def cleanup_directory_by_count(directory, max_files=10):
    """Ensure that the number of files in 'directory' does not exceed max_files."""
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

def draw_infinite_grid(img, cell_period, offset_x, offset_y):
    """
    Draw an infinite grid over the image.
    Grid lines are drawn every 'cell_period' pixels (cell block size, including grid line).
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

# ===== Capture Loop Thread =====
def capture_loop(config, grid_region, grid_size_m):
    global latest_ocr_filename, latest_grid_filename, valid_map_detected
    grid_left, grid_top, grid_width, grid_height = grid_region
    cell_block = config.get("cell_block", 61)
    while True:
        timestamp = int(time.time())
        if not valid_map_detected:
            ocr_img = pyautogui.screenshot(region=ocr_region)
            ocr_np = np.array(ocr_img)
            ocr_bgr = cv2.cvtColor(ocr_np, cv2.COLOR_RGB2BGR)
            ocr_filename = f"ocr_{timestamp}.png"
            ocr_filepath = os.path.join(DIR_OCR, ocr_filename)
            cv2.imwrite(ocr_filepath, ocr_bgr)
            latest_ocr_filename = f"screenshots/ocr/{ocr_filename}"
        grid_img = pyautogui.screenshot(region=(grid_left, grid_top, grid_width, grid_height))
        grid_np = np.array(grid_img)
        grid_bgr = cv2.cvtColor(grid_np, cv2.COLOR_RGB2BGR)
        grid_bgr = draw_infinite_grid(grid_bgr, cell_block, grid_offset_x, grid_offset_y)
        grid_filename = f"grid_{timestamp}.png"
        grid_filepath = os.path.join(DIR_GRID, grid_filename)
        cv2.imwrite(grid_filepath, grid_bgr)
        latest_grid_filename = f"screenshots/grid/{grid_filename}"
        
        cleanup_directory_by_count(DIR_OCR, max_files=10)
        cleanup_directory_by_count(DIR_GRID, max_files=10)
        
        print(f"Saved OCR screenshot: {latest_ocr_filename if not valid_map_detected else 'OCR halted'}, Grid screenshot: {grid_filename}")
        time.sleep(2)

# ===== Flask Web Server =====
app = Flask(__name__, static_url_path='/static', static_folder='static')

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Debug Screenshots & Grid Adjustment</title>
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
                if(data.ocr) {
                    document.getElementById('ocr_img').src = '/static/' + data.ocr + '?t=' + new Date().getTime();
                }
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
    <h1>Debug Screenshots & Grid Adjustment</h1>
    <p id="current_map">Current map: None</p>
    <h2>OCR Region</h2>
    {% if ocr %}
      <img id="ocr_img" class="screenshot" src="/static/{{ ocr }}" alt="OCR Screenshot">
    {% else %}
      <p>No OCR screenshot available.</p>
    {% endif %}
    <h2>Grid Region</h2>
    {% if grid %}
      <img id="grid_img" class="screenshot" src="/static/{{ grid }}" alt="Grid Screenshot">
    {% else %}
      <p>No Grid screenshot available.</p>
    {% endif %}
    <h2>Adjust Grid Offsets</h2>
    <p id="offset_line">Current grid offset: (0, 0)</p>
    <button onclick="adjustOffset('x', 1)">Increase Offset X</button>
    <button onclick="adjustOffset('x', -1)">Decrease Offset X</button>
    <button onclick="adjustOffset('y', 1)">Increase Offset Y</button>
    <button onclick="adjustOffset('y', -1)">Decrease Offset Y</button>
    <br>
    <h2>Change Map</h2>
    <select id="map_select">
        {% for map in maps %}
            <option value="{{ map }}">{{ map }}</option>
        {% endfor %}
    </select>
    <button onclick="changeMap()">Set Map</button>
    <br>
    <button onclick="bypassOCR()">Bypass OCR and Default to Frozen Pass</button>
    <br><br>
    <h3>Final Offset String (copy this into your map config):</h3>
    <p id="final_offset">offset: (0, 0)</p>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, ocr=latest_ocr_filename, grid=latest_grid_filename, maps=list(map_configs.keys()))

@app.route("/latest")
def latest():
    return jsonify({
        "ocr": latest_ocr_filename,
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
    global current_map, valid_map_detected, grid_offset_x, grid_offset_y
    map_name = request.args.get("map", "").strip()
    if map_name in map_configs:
        current_map = map_name
        valid_map_detected = True
        default_offset = map_configs[map_name].get("offset", (0, 0))
        grid_offset_x, grid_offset_y = default_offset
        message = f"Map changed to {map_name}. Default offset set to {default_offset}."
    else:
        message = f"Map '{map_name}' not found."
    return jsonify({"message": message})

@app.route("/bypass")
def bypass():
    global current_map, valid_map_detected
    current_map = "Frozen Pass"
    valid_map_detected = True
    return jsonify({"message": "Bypassed OCR. Defaulted to Frozen Pass."})

# ===== OCR Detection Loop =====
def ocr_detection_loop():
    global current_map, valid_map_detected
    while not valid_map_detected:
        print("Running OCR to detect map name...")
        map_text = ocr_map_name(ocr_region)
        print("OCR Result:", map_text)
        for map_name in map_configs.keys():
            if map_name.lower() in map_text.lower():
                current_map = map_name
                valid_map_detected = True
                print(f"Detected map: {current_map}")
                break
        if not valid_map_detected:
            print("Map name not recognized. Retrying in 2 seconds...")
            time.sleep(2)

# ===== Main Program =====
def main():
    global current_map, valid_map_detected, grid_offset_x, grid_offset_y
    ocr_thread = threading.Thread(target=ocr_detection_loop, daemon=True)
    ocr_thread.start()
    
    default_config = map_configs["Frozen Pass"]
    grid_region = default_config["grid_region"]
    grid_size_m = default_config["grid_size_m"]
    
    grid_offset_x, grid_offset_y = default_config.get("offset", (0, 0))

    time.sleep(5)
    if not valid_map_detected:
        print("No valid map detected by OCR; defaulting to Frozen Pass.")
        current_map = "Frozen Pass"
        valid_map_detected = True
        config = default_config
    else:
        config = map_configs[current_map]
    print(f"Using grid region: {config['grid_region']} and grid cell size: {config['grid_size_m']} m")
    
    capture_thread = threading.Thread(target=capture_loop, args=(config, config["grid_region"], config["grid_size_m"]), daemon=True)
    capture_thread.start()

    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    main()