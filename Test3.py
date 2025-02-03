import sys
import math
import time
import pyautogui
import cv2
import numpy as np
from PIL import Image, ImageTk
import tkinter as tk

# ===== Fixed Configurations =====
configs = {
    170: {"region_width": 400, "region_height": 400, "offset_x": 20, "offset_y": 20},
    200: {"region_width": 430, "region_height": 430, "offset_x": 14, "offset_y": 14},
    225: {"region_width": 460, "region_height": 460, "offset_x": 12,  "offset_y": 12}
}
GRID_COUNT = 7

# Tolerances for color detection
player_tolerance = 10
ping_tolerance = 5

# ===== Color Definitions =====
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

# --- Ping (target yellow) Colors ---
ping_colors = [
    np.array([7, 209, 209]),
    np.array([7, 213, 213]),
    np.array([7, 207, 207]),
    np.array([6, 187, 187]),
    np.array([7, 202, 202])
]

# ===== Helper Functions =====
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
    Find contours from mask and return the center and radius of the minimum enclosing circle
    covering only the significant points. Discard small isolated contours.
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

# ===== Tkinter Overlay Window =====
class OverlayWindow(tk.Tk):
    def __init__(self, grid_size_m, config):
        super().__init__()
        self.grid_size_m = grid_size_m

        self.region_width = config["region_width"]
        self.region_height = config["region_height"]
        self.offset_x = config["offset_x"]
        self.offset_y = config["offset_y"]

        self.title("Minimap Overlay")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.9)

        self.label = tk.Label(self)
        self.label.pack()

        self.geometry(f"{self.region_width}x{self.region_height}+50+50")
        self.update_overlay()

    def update_overlay(self):
        screen_width, screen_height = pyautogui.size()
        region_left = screen_width - self.region_width - self.offset_x
        region_top = screen_height - self.region_height - self.offset_y
        minimap_image = pyautogui.screenshot(region=(region_left, region_top, self.region_width, self.region_height))
        minimap_np = np.array(minimap_image)
        minimap_bgr = cv2.cvtColor(minimap_np, cv2.COLOR_RGB2BGR)

        for i in range(1, GRID_COUNT):
            x = int(i * (self.region_width / GRID_COUNT))
            cv2.line(minimap_bgr, (x, 0), (x, self.region_height), (0, 255, 0), 2)
        for j in range(1, GRID_COUNT):
            y = int(j * (self.region_height / GRID_COUNT))
            cv2.line(minimap_bgr, (0, y), (self.region_width, y), (0, 255, 0), 2)

        # --- Detect Player (Red) ---
        player_mask = create_mask(minimap_bgr, player_colors, player_tolerance)
        player_center, player_radius = get_min_enclosing_circle(player_mask)
        if player_center is not None:
            cv2.circle(minimap_bgr, player_center, player_radius, (0, 0, 255), thickness=-1)

        # --- Detect Ping (Yellow) ---
        ping_mask = create_mask(minimap_bgr, ping_colors, ping_tolerance)
        ping_center, ping_radius = get_min_enclosing_circle(ping_mask)
        if ping_center is not None:
            cv2.circle(minimap_bgr, ping_center, ping_radius, (0, 255, 255), thickness=-1)

        if player_center is not None and ping_center is not None:
            cv2.line(minimap_bgr, player_center, ping_center, (255, 255, 255), 2)
            dx = ping_center[0] - player_center[0]
            dy = ping_center[1] - player_center[1]
            pixel_distance = math.hypot(dx, dy)
            cell_pixel_size = self.region_width / GRID_COUNT
            distance_in_cells = pixel_distance / cell_pixel_size
            range_meters = distance_in_cells * self.grid_size_m

            text = f"Range: {range_meters:.2f} m"
            details = f"Pixels: {pixel_distance:.1f}, Cells: {distance_in_cells:.2f}"
            cv2.putText(minimap_bgr, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.putText(minimap_bgr, details, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        minimap_rgb = cv2.cvtColor(minimap_bgr, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(minimap_rgb)
        tk_image = ImageTk.PhotoImage(image=pil_image)
        self.label.configure(image=tk_image)
        self.label.image = tk_image

        self.after(100, self.update_overlay)

if __name__ == "__main__":
    configs = {
        170: {"region_width": 400, "region_height": 400, "offset_x": 20, "offset_y": 20},
        200: {"region_width": 430, "region_height": 430, "offset_x": 14, "offset_y": 14},
        220: {"region_width": 450, "region_height": 450, "offset_x": 8,  "offset_y": 8}
    }

    grid_size_m = float(input("Enter the real-world size (in meters) of one grid cell (supported: 170, 200, 220): "))

    if grid_size_m in configs:
        config = configs[grid_size_m]
    else:
        print(f"Grid size {grid_size_m} m not specifically configured. Defaulting to 200 m settings.")
        config = configs[200]
        grid_size_m = 200.0

    app = OverlayWindow(grid_size_m, config)
    app.mainloop()