import json
from pathlib import Path
from typing import Dict
from .logger import logger

# Load system -> region mapping from a JSON file
def load_system_data() -> Dict[str, str]:
    try:
        data_file = Path(__file__).parent / 'eve_systems.json'
        with open(data_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading EVE system data: {e}")
        return {}

SYSTEM_TO_REGION = load_system_data()

def get_region(system: str) -> str:
    """Get region name for a system"""
    return SYSTEM_TO_REGION.get(system.upper(), "Unknown") 