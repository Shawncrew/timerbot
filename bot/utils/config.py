import os
import yaml
from dotenv import load_dotenv
from .logger import logger

CONFIG_FILE = "/opt/timerbot/bot/config.yaml"

def load_config():
    """Load configuration from config.yaml, checking both /opt/timerbot/bot/ and local directory"""
    try:
        # First try the /opt/timerbot/bot/ location
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = yaml.safe_load(f)
                logger.info(f"Loaded configuration from {CONFIG_FILE}")
                return config
                
        # If not found, try local directory
        local_config = "config.yaml"
        if os.path.exists(local_config):
            with open(local_config, 'r') as f:
                config = yaml.safe_load(f)
                logger.info(f"Loaded configuration from {local_config}")
                return config
                
        # If neither exists, use defaults
        logger.error("No config.yaml found in either /opt/timerbot/bot/ or local directory")
        logger.info("Using default configuration")
        return {
            'check_interval': 60,
            'notification_time': 60,
            'expiry_time': 60,
            'channels': {
                'timerboard': None,
                'commands': None
            }
        }
    except Exception as e:
        logger.error(f"Error loading config.yaml: {e}")
        logger.info("Using default configuration")
        return {
            'check_interval': 60,
            'notification_time': 60,
            'expiry_time': 60,
            'channels': {
                'timerboard': None,
                'commands': None
            }
        }

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