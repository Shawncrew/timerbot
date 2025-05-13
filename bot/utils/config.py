import os
import yaml
from dotenv import load_dotenv
from .logger import logger

CONFIG_FILE = "/opt/timerbot/bot/config.yaml"

def load_config():
    """Load configuration from config.yaml"""
    default_config = {
        'check_interval': 60,
        'notification_time': 60,
        'expiry_time': 60,
        'servers': {
            'server1': {
                'timerboard': None,
                'commands': None,
                'citadel_attacked': None,
                'citadel_info': None
            },
            'server2': {
                'timerboard': None,
                'commands': None,
                'citadel_attacked': None,
                'citadel_info': None
            }
        }
    }
    
    try:
        # First try the /opt/timerbot/bot/ location
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                loaded_config = yaml.safe_load(f)
                logger.info(f"Raw loaded config: {loaded_config}")
                
                # Ensure servers section exists
                if 'servers' not in loaded_config:
                    logger.error("No 'servers' section found in config")
                    loaded_config['servers'] = {}
                
                # Log the servers section
                logger.info(f"Servers section: {loaded_config.get('servers', {})}")
                
                # Add any missing server configs
                for server in default_config['servers']:
                    if server not in loaded_config['servers']:
                        loaded_config['servers'][server] = default_config['servers'][server]
                        logger.warning(f"Server '{server}' not found in config, using defaults")
                    
                    # Add any missing channel configs for each server
                    for channel in default_config['servers']['server1']:
                        if channel not in loaded_config['servers'][server]:
                            loaded_config['servers'][server][channel] = None
                            logger.warning(f"Channel '{channel}' not found in {server} config, setting to None")
                        else:
                            logger.info(f"Found channel '{channel}' in {server} with ID: {loaded_config['servers'][server][channel]}")
                
                return loaded_config
                
        # If not found, try local directory
        local_config = "config.yaml"
        if os.path.exists(local_config):
            with open(local_config, 'r') as f:
                config = yaml.safe_load(f)
                logger.info(f"Loaded configuration from {local_config}")
                
                # Same channel validation as above
                if 'servers' not in config:
                    config['servers'] = {}
                
                for server in default_config['servers']:
                    if server not in config['servers']:
                        config['servers'][server] = default_config['servers'][server]
                        logger.warning(f"Server '{server}' not found in config, using defaults")
                    
                    for channel in default_config['servers']['server1']:
                        if channel not in config['servers'][server]:
                            config['servers'][server][channel] = None
                            logger.warning(f"Channel '{channel}' not found in {server} config, setting to None")
                
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