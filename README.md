# WarThunderAnalyzer

WarThunderAnalyzer is a Python-based tool designed to analyze in-game events in War Thunder. It uses OCR (Optical Character Recognition) to detect and log specific in-game events, track session statistics, and provide a web-based dashboard for real-time updates.

## Features

- **Real-Time Detection**:
  - Detects and logs hits, critical hits, kills, ricochets, fires, and explosions in real time.
  - Identifies specific module damage (e.g., tracks, engine, fuel tank).
  - Detects the in-game map name automatically using OCR.

- **Statistics Tracking**:
  - Tracks hits, crits, kills, fires, ricochets, non-penetrations, ammo explosions, and fuel explosions.
  - Statistics are updated dynamically and displayed on the web interface.

- **Game State Detection**:
  - Recognizes whether the player is in the main menu, in-game, or in an unknown state.
  - Automatically pauses detection when War Thunder is out of focus and resumes when it is refocused.

- **Web-Based Dashboard**:
  - Displays game state, recent logs, and session statistics in a clean, responsive interface.
  - Highlights statistic changes in real time.
  - Includes a **rangefinder grid adjustment tool** for accurate distance estimation.

- **Logging**:
  - Logs all detected events with timestamps for easy debugging and session review.
  - Limits redundant logging to avoid excessive console clutter.

## Rangefinder Grid Features

- **Automatic Map Recognition**:
  - Uses OCR to detect the in-game map name once the "To Battle!" text disappears.
  - Waits indefinitely until a valid map name is detected.

- **Grid Overlay**:
  - Captures the minimap grid area and overlays an infinite grid.
  - Supports multiple maps with configurable grid size and offsets.
  - Allows fine-tuning of grid alignment via a web-based UI.

- **Focus Handling**:
  - Pauses grid updates when the game is out of focus and resumes upon refocus.

## Requirements

- Python 3.7+
- Libraries:
  - Flask
  - Pillow
  - pytesseract
  - pyautogui
  - numpy
  - OpenCV

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Demiffy/WarThunderAnalyzer.git
   cd WarThunderAnalyzer
   ```

2. Install required Python packages:
   ```bash
   pip install flask pillow pytesseract pyautogui numpy opencv-python
   ```

3. Install Tesseract OCR:
   - **Windows**: Download and install Tesseract from [tesseract-ocr](https://github.com/tesseract-ocr/tesseract).
   - **Linux**: Install via package manager:
     ```bash
     sudo apt install tesseract-ocr
     ```
   - **MacOS**: Install via Homebrew:
     ```bash
     brew install tesseract
     ```

4. Verify Tesseract installation:
   ```bash
   tesseract --version
   ```

## Usage

1. Run the Python script:
  ```bash
  python main.py
   ```
   
2. Open your browser and navigate to:
  ```
  http://localhost:5000
  ```

 3. Open another browser tab and navigate to in order to see Rangefinder adjustment UI:
   ```
   http://localhost:5001
   ```

4. View real-time updates, logs, and statistics in the web interface.

## How It Works

1. **Region Detection**:
   - The tool captures specific screen regions for detecting "To Battle!" (menu state), gear and speed indicators (game state), and in-game events.

2. **Event Detection**:
   - Uses OCR via Tesseract to extract text from the captured regions.
   - Analyzes extracted text to identify events such as kills, hits, and explosions.

3. **Statistics Update**:
   - Tracks occurrences of each event type in the current session.
   - Updates and highlights statistic changes in the web dashboard.

4. **Web Dashboard**:
   - Built using Flask, the dashboard refreshes automatically every second.
   - Displays the current game state, detailed statistics, and a log of recent events.
   - Allows adjusting the rangefinder grid offsets for more accurate distance estimation.

5. **Grid Capture & Rangefinder**:
   - Automatically detects the map name using OCR.
   - Waits until a valid map name is detected before initializing grid settings.
   - Provides a web UI to adjust grid alignment and offsets.

## Screenshots

    - TBA

## Limitations

- The accuracy of OCR depends on the in-game font, resolution, and Tesseract configuration.
- Requires War Thunder to run in a windowed or borderless fullscreen mode for proper region detection.
- The tool may need adjustments for non-default UI settings or resolutions.
- The rangefinder grid requires known map configurations to work correctly.

## Future Improvements

- Add more map configurations.
- Improve OCR accuracy with better preprocessing techniques.

---
