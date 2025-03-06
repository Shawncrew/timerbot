import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path

# Create logger
logger = logging.getLogger('timerbot')
logger.setLevel(logging.INFO)

# Only add handlers if none exist
if not logger.handlers:
    # Create formatters
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', 
                                datefmt='%Y-%m-%d %H:%M:%S')

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Create file handler
    log_dir = Path('/opt/timerbot/logs')
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / 'timerbot.log',
        maxBytes=1024*1024,  # 1MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

# Prevent propagation to root logger
logger.propagate = False 