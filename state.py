# state.py
log_store = []
game_state = "Unknown"
last_event_result = ""
last_modules_result = ""
last_raw_event_snapshot = ""
last_processed_event_snapshot = ""
last_event_timestamp = 0
last_modules_timestamp = 0

stats = {
    "hits": 0,
    "crits": 0,
    "kills": 0,
    "fires": 0,
    "ricochets": 0,
    "non_penetrations": 0,
    "ammo_explosions": 0,
    "fuel_explosions": 0,
    "unknown_events": 0
}

prev_stats = stats.copy()

# Shared flag used by both modules to signal when the statistics region is open.
statistics_open = False
