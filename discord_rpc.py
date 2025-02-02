# discord_rpc.py
import time
import threading
from pypresence import Presence
import state
from utils import log
from dotenv import load_dotenv
import os

load_dotenv()
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")

if not DISCORD_CLIENT_ID:
    log("Discord Client ID is missing! Set it in the .env file.", level="ERROR", tag="DISCORD")
    exit(1)

def discord_presence_loop():
    rpc = Presence(DISCORD_CLIENT_ID)
    try:
        rpc.connect()
    except Exception as e:
        log(f"Failed to connect to Discord RPC: {e}", level="ERROR", tag="DISCORD")
        return
    log("Connected to Discord RPC", tag="DISCORD")
    start_time = time.time()
    while True:
        try:
            current_state = state.game_state
            if current_state == "In Game":
                details = f"In-Game (Kills: {state.stats['kills']})"
            elif current_state == "In Menu":
                details = "In Main Menu"
                state.stats["kills"] = 0
                state.last_event_result = ""
            elif current_state == "Game Not In Focus":
                details = "Idle"
            elif current_state == "Unknown":
                details = "Unknown"
            else:
                details = current_state

            if current_state == "In Menu":
                event_text = "\u200b\u200b"
            else:
                if state.last_event_result and state.last_event_result.lower().strip() != "no significant events detected":
                    event_text = state.last_event_result
                else:
                    event_text = "\u200b\u200b"

            rpc.update(
                details=details,
                state=event_text,
                large_image="wtlogo",
                large_text="War Thunder",
                start=start_time
            )
        except Exception as e:
            log(f"Error updating Discord RPC: {e}", level="ERROR", tag="DISCORD")
        time.sleep(1)

def start_discord_rpc():
    threading.Thread(target=discord_presence_loop, daemon=True).start()