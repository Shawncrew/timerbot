import os
import yaml
from dotenv import load_dotenv
from .logger import logger

CONFIG_FILE = "/opt/timerbot/bot/config.yaml"

def load_config():
    """Load configuration from config.yaml, checking both /opt/timerbot/bot/ and local directory"""
    default_config = {
        'check_interval': 60,
        'notification_time': 60,
        'expiry_time': 60,
        'channels': {
            'timerboard': None,
            'commands': None,
            'citadel_attacked': None,
            'citadel_info': None
        }
    }
    
    try:
        # First try the /opt/timerbot/bot/ location
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                loaded_config = yaml.safe_load(f)
                logger.info(f"Raw loaded config: {loaded_config}")  # Debug line
                
                # Ensure all required keys exist
                if 'channels' not in loaded_config:
                    logger.error("No 'channels' section found in config")
                    loaded_config['channels'] = {}
                
                # Log the channels section specifically
                logger.info(f"Channels section: {loaded_config.get('channels', {})}")  # Debug line
                
                # Add any missing channel IDs with None as default
                for channel in default_config['channels']:
                    if channel not in loaded_config['channels']:
                        loaded_config['channels'][channel] = None
                        logger.warning(f"Channel '{channel}' not found in config, setting to None")
                    else:
                        logger.info(f"Found channel '{channel}' with ID: {loaded_config['channels'][channel]}")  # Debug line
                
                return loaded_config
                
        # If not found, try local directory
        local_config = "config.yaml"
        if os.path.exists(local_config):
            with open(local_config, 'r') as f:
                config = yaml.safe_load(f)
                logger.info(f"Loaded configuration from {local_config}")
                
                # Same channel validation as above
                if 'channels' not in config:
                    config['channels'] = {}
                
                for channel in default_config['channels']:
                    if channel not in config['channels']:
                        config['channels'][channel] = None
                        logger.warning(f"Channel '{channel}' not found in config, setting to None")
                
                return config
                
        # If neither exists, use defaults
        logger.error("No config.yaml found in either /opt/timerbot/bot/ or local directory")
        logger.info("Using default configuration")
        return default_config
        
    except Exception as e:
        logger.error(f"Error loading config.yaml: {e}")
        logger.info("Using default configuration")
        return default_config

def load_token():
    """Load Discord token from .env file"""
    try:
        # First try /opt/timerbot/bot/.env
        if os.path.exists('/opt/timerbot/bot/.env'):
            load_dotenv('/opt/timerbot/bot/.env')
            logger.info("Loading token from /opt/timerbot/bot/.env")
        else:
            # Try local .env file
            if os.path.exists('.env'):
                load_dotenv()
                logger.info("Loading token from local .env file")
            else:
                logger.error("No .env file found in either location")
                raise FileNotFoundError("No .env file found")

        token = os.getenv('DISCORD_TOKEN')
        if not token:
            logger.error("DISCORD_TOKEN not found in .env file")
            raise ValueError("DISCORD_TOKEN not found in .env file")
            
        return token

    except Exception as e:
        logger.error(f"Error loading Discord token: {e}")
        raise

# Load config at module level
CONFIG = load_config() 