# analysis.py
from utils import fuzzy_contains
from state import stats

def analyze_text(extracted_text):
    """Analyze the extracted text for hit/kill events and update stats."""
    text = extracted_text.lower()
    events = []

    fire_fragments = ["fire"]
    crew_fragments = ["cre", "kno", "out"]
    crit_fragments = ["crit"]
    hit_fragments = ["hit"]
    ricochet_fragments = ["rico", "rochet"]
    non_penetration_fragments = ["non", "-", "penetrat"]
    explosion_fragments = ["explod"]
    extended_ammo_fragments = ["ammo", "amme", "amm"]
    fuel_fragments = ["fuel"]

    if fuzzy_contains(text, fire_fragments):
        events.append("Enemy set on fire")
        stats["fires"] += 1
    if fuzzy_contains(text, crew_fragments):
        events.append("Enemy Crew knocked out")
        stats["kills"] += 1
    if fuzzy_contains(text, crit_fragments):
        events.append("Enemy Critical Hit")
        stats["crits"] += 1
    elif fuzzy_contains(text, hit_fragments):
        events.append("Enemy Hit")
        stats["hits"] += 1
    if fuzzy_contains(text, ricochet_fragments):
        events.append("Ricochet")
        stats["ricochets"] += 1
    if fuzzy_contains(text, non_penetration_fragments):
        events.append("Non-penetration")
        stats["non_penetrations"] += 1
    if fuzzy_contains(text, explosion_fragments):
        if fuzzy_contains(text, extended_ammo_fragments) and fuzzy_contains(text, fuel_fragments):
            events.append("Enemy killed by ammunition and fuel explosion")
            stats["ammo_explosions"] += 1
            stats["fuel_explosions"] += 1
            stats["kills"] += 1
        elif fuzzy_contains(text, extended_ammo_fragments):
            events.append("Enemy killed by ammunition explosion")
            stats["ammo_explosions"] += 1
            stats["kills"] += 1
        elif fuzzy_contains(text, fuel_fragments):
            events.append("Enemy killed by fuel explosion")
            stats["fuel_explosions"] += 1
            stats["kills"] += 1
        else:
            events.append("Enemy killed by unspecified explosion")
            stats["unknown_events"] += 1

    if not events:
        events.append("No significant events detected")
    return "; ".join(events)

def analyze_modules_text(extracted_text):
    """Analyze the extracted text for modules and return a summary string."""
    text = extracted_text.lower()
    modules_detected = []
    module_fragments = {
        "Track": ["track", "tra"],
        "Cannon barrel": ["barrel", "barr"],
        "Horizontal turret drive": ["hor", "horizontal", "tal"],
        "Vertical turret drive": ["ver", "vertical", "cal"],
        "Driver": ["driver", "driv"],
        "Gunner": ["gunner", "ner"],
        "Commander": ["comm", "ander"],
        "Loader": ["loader", "load"],
        "Machine gunner": ["mach", "ine"],
        "Cannon breech": ["breech", "ee", "ech"],
        "Fuel tank": ["fuel", "tank"],
        "Engine": ["engin", "eng"],
        "Transmission": ["transmiss", "trans"],
        "Radiator": ["radiat", "rad"],
        "Ammo": ["ammo"],
        "Autoloader": ["auto"],
    }
    for module, fragments in module_fragments.items():
        if module == "Ammo":
            if any(fuzzy_contains(text, [frag]) for frag in fragments):
                modules_detected.append(module)
        else:
            if all(fuzzy_contains(text, [frag]) for frag in fragments):
                modules_detected.append(module)
    if not modules_detected:
        modules_detected.append("No significant modules detected")
    return "; ".join(modules_detected)
