import logging
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

    # File handler: use plain FileHandler on Windows to avoid PermissionError during
    # RotatingFileHandler.rotate() (file is locked by process)
    log_dir = Path('/opt/timerbot/logs')
    if not log_dir.exists():
        log_dir = Path(__file__).resolve().parent.parent.parent / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / 'timerbot.log'
    if sys.platform == 'win32':
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
    else:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=1024 * 1024,  # 1MB
            backupCount=5
        )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

# Prevent propagation to root logger
logger.propagate = False 