import time
from PIL import Image
import numpy as np
import pyautogui
from scipy.ndimage import label, center_of_mass

# Define minimap region size
MINIMAP_REGION_WIDTH = 500
MINIMAP_REGION_HEIGHT = 500

# Tolerance for enemy color detection
ENEMY_TOLERANCE = 60

# Reference colors for enemy (approximate range)
ENEMY_REF_COLORS = [
    np.array([0xFA, 0x0C, 0x00]),  
    np.array([0x9E, 0x08, 0x00]),  
    np.array([0x95, 0x08, 0x01])   
]

def create_color_mask(np_image, ref_colors, tolerance):
    mask = np.zeros(np_image.shape[:2], dtype=bool)
    for ref_color in ref_colors:
        color_diff = np.abs(np_image - ref_color)
        current_mask = np.all(color_diff < tolerance, axis=-1)
        mask |= current_mask
    return mask

def detect_enemy_in_region(image):
    np_image = np.array(image)
    enemy_mask = create_color_mask(np_image, ENEMY_REF_COLORS, ENEMY_TOLERANCE)
    return enemy_mask

def find_clusters(mask, min_size=10):
    labeled_array, num_features = label(mask)
    centroids = []
    for i in range(1, num_features + 1):
        cluster_mask = labeled_array == i
        cluster_size = np.sum(cluster_mask)
        if cluster_size >= min_size:
            centroid = center_of_mass(mask, labeled_array, i)
            centroids.append(centroid)
    return centroids

if __name__ == "__main__":
    screen_width, screen_height = pyautogui.size()
    region_left = screen_width - MINIMAP_REGION_WIDTH
    region_top = screen_height - MINIMAP_REGION_HEIGHT

    # Capture minimap region
    minimap_image = pyautogui.screenshot(region=(region_left, region_top, MINIMAP_REGION_WIDTH, MINIMAP_REGION_HEIGHT))
    minimap_image_rgb = minimap_image.convert("RGB")

    # Detect enemy mask
    enemy_mask = detect_enemy_in_region(minimap_image_rgb)
    
    # Debug: Print number of pixels detected by enemy mask
    enemy_pixels = np.sum(enemy_mask)
    print(f"Enemy pixels detected: {enemy_pixels}")
    
    # Visualize enemy mask
    Image.fromarray((enemy_mask * 255).astype(np.uint8)).show(title="Enemy Mask")

    # Find enemy clusters
    enemy_centroids = find_clusters(enemy_mask, min_size=10)
    print(f"Detected enemy clusters: {len(enemy_centroids)}")

    # Mark detected enemy cluster centers on the image
    for centroid in enemy_centroids:
        if np.isnan(centroid[0]) or np.isnan(centroid[1]):
            continue
        y, x = int(centroid[0]), int(centroid[1])
        minimap_image_rgb.putpixel((x, y), (255, 0, 255))  # mark enemy centroid in magenta

    minimap_image_rgb.show(title="Minimap with Enemy Cluster Centers")
