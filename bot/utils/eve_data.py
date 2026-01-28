import json
from pathlib import Path
from typing import Dict
from .logger import logger

# Load system -> region mapping from a JSON file
def load_system_data() -> Dict[str, str]:
    try:
        # Use absolute path based on the data directory
        data_file = Path('/opt/timerbot/data/eve_systems.json')
        if not data_file.exists():
            # Fallback to the utils directory
            data_file = Path(__file__).parent / 'eve_systems.json'
        
        with open(data_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading EVE system data: {e}")
        return {}

SYSTEM_TO_REGION = load_system_data()

def get_region(system: str) -> str:
    """Get region name for a system (case-insensitive lookup)"""
    if not system:
        return "Unknown"
    # Try exact match first (for performance)
    if system in SYSTEM_TO_REGION:
        return SYSTEM_TO_REGION[system]
    # Try uppercase match
    if system.upper() in SYSTEM_TO_REGION:
        return SYSTEM_TO_REGION[system.upper()]
    # Try case-insensitive lookup
    system_upper = system.upper()
    for key, value in SYSTEM_TO_REGION.items():
        if key.upper() == system_upper:
            return value
    return "Unknown" 