# image_processing.py
import numpy as np
from PIL import Image, ImageOps
import pytesseract
from pytesseract import TesseractError

from utils import log

def preprocess_image_for_colors(image):
    """
    Process the image for the hit/kill region using masking and inversion.
    (This is your original color filtering method.)
    """
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
    """
    Process the modules region using masking and inversion.
    """
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

def preprocess_image_for_gear(image):
    """
    Process the gear region image by simply converting it to grayscale.
    No masking, thresholding, or inversion is applied.
    This ensures that the gear region is processed "raw" (aside from grayscale conversion).
    """
    return image.convert("L")

def extract_text_from_image(image):
    """Extract text from the hit/kill region after processing for colors."""
    processed_image = preprocess_image_for_colors(image)
    try:
        custom_config = r'--oem 3 --psm 6'
        return pytesseract.image_to_string(processed_image, lang='eng', config=custom_config)
    except TesseractError as e:
        log(f"Tesseract error in color region: {e}", level="ERROR", tag="OCR")
        return ""

def extract_battle_text_from_image(image):
    """Extract text from the battle region without additional processing."""
    try:
        custom_config = r'--oem 3 --psm 6'
        return pytesseract.image_to_string(image, lang='eng', config=custom_config)
    except TesseractError as e:
        log(f"Tesseract error in battle region: {e}", level="ERROR", tag="OCR")
        return ""

def extract_gear_text_from_image(image):
    """
    Extract text from the gear region.
    This function uses the gear-specific preprocessing, which simply converts the image to grayscale.
    """
    processed_image = preprocess_image_for_gear(image)
    try:
        custom_config = r'--oem 3 --psm 6'
        return pytesseract.image_to_string(processed_image, lang='eng', config=custom_config)
    except TesseractError as e:
        log(f"Tesseract error in gear region: {e}", level="ERROR", tag="OCR")
        return ""

def extract_modules_text_from_image(image):
    """Extract text from the modules region after processing for modules."""
    processed_image = preprocess_image_for_modules(image)
    try:
        custom_config = r'--oem 3 --psm 6'
        return pytesseract.image_to_string(processed_image, lang='eng', config=custom_config)
    except TesseractError as e:
        log(f"Tesseract error in modules region: {e}", level="ERROR", tag="OCR")
        return ""