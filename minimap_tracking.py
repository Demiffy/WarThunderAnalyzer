import os
import time
import numpy as np
import cv2
import mss
import mss.tools
import state
from utils import is_aces_in_focus, log

REGION = (1473, 635, 432, 432)

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

# Tracking parameters for player detection
prev_center = None
prev_count = 0
stable_count = 0
stable_threshold = 3
distance_threshold = 20
min_count_threshold = 2

OUTPUT_IMAGE_PATH = os.path.join("static", "screenshots", "minimap_ocr", "tracked_target.png")
_last_pause_msg = None

def write_placeholder():
    placeholder = np.zeros((REGION[3], REGION[2], 3), dtype=np.uint8)
    placeholder = overlay_text(placeholder, "Tracking paused", color=(0, 0, 255), position=(10, 30))
    cv2.imwrite(OUTPUT_IMAGE_PATH, placeholder)
    log("Wrote placeholder image (Tracking paused).", level="INFO", tag="MINIMAP")

def start_minimap_player():
    global prev_center, prev_count, stable_count, _last_pause_msg
    with mss.mss() as sct:
        monitor = {"left": REGION[0], "top": REGION[1], "width": REGION[2], "height": REGION[3]}
        while True:
            pause_condition = (not is_aces_in_focus()) or state.statistics_open or state.main_menu_open or (state.game_state == "In Menu")
            if pause_condition:
                msg = f"Pausing minimap tracking. Focus={is_aces_in_focus()}, stats={state.statistics_open}, game_state={state.game_state}"
                if _last_pause_msg != msg:
                    log(msg, level="INFO", tag="MINIMAP")
                    _last_pause_msg = msg
                write_placeholder()
                time.sleep(1)
                continue
            else:
                _last_pause_msg = None

            sct_img = sct.grab(monitor)
            img = cv2.cvtColor(np.array(sct_img), cv2.COLOR_BGRA2BGR)
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
                    log(f"Initial detection: center {center} with count {count}", level="INFO", tag="MINIMAP")
                else:
                    dist = np.linalg.norm(np.array(center) - np.array(prev_center))
                    if dist > distance_threshold:
                        if count > 1.5 * prev_count:
                            stable_count += 1
                            if stable_count >= stable_threshold:
                                prev_center = center
                                prev_count = count
                                stable_count = 0
                                log(f"Updated tracked center to {center} with count {count}", level="INFO", tag="MINIMAP")
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

            # Process ping
            def process_ping(image):
                out = image.copy()
                h, w, _ = image.shape
                reshaped = image.reshape(-1, 3)
                ping_mask = np.zeros((reshaped.shape[0],), dtype=bool)
                for target in ping_target_colors:
                    diff = reshaped.astype(np.int16) - target.astype(np.int16)
                    dist = np.linalg.norm(diff, axis=1)
                    ping_mask |= (dist < tolerance)
                return out, ping_mask

            ping_target_colors = [hex_to_bgr(x) for x in ping_hex_colors]
            _, ping_mask = process_ping(img)
            ping_center, ping_radius, ping_count = get_enclosing_circle(ping_mask, img.shape)
            if ping_count > 0:
                output_img = draw_filled_circle(output_img, ping_center, ping_radius, color=(0, 255, 255))
                if center is not None and ping_center is not None:
                    cv2.line(output_img, ping_center, center, (255, 255, 255), 2)
                log(f"Ping detected: {ping_count} pixels; circle at {ping_center} with radius {ping_radius}", level="INFO", tag="MINIMAP")
            cv2.imwrite(OUTPUT_IMAGE_PATH, output_img)
            time.sleep(0.1)

if __name__ == "__main__":
    start_minimap_player()