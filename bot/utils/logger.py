import logging
from logging.handlers import RotatingFileHandler
import os

LOG_DIR = "/opt/timerbot/logs"

def setup_logger():
    """Configure and return the logger"""
    # Create log directory
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Configure logging
    logger = logging.getLogger('timerbot')
    logger.setLevel(logging.INFO)
    
    # Add rotating file handler (10 files, 10MB each)
    handler = RotatingFileHandler(
        f"{LOG_DIR}/bot.log",
        maxBytes=10_000_000,
        backupCount=10
    )
    
    # Format for log messages
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # Also log to console
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    
    return logger

# Create a global logger instance
logger = setup_logger() 