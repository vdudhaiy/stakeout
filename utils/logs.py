'''
Set up logging for the repo. This module configures a logger that writes logs to both a file and the console, with log levels and formats defined. It also ensures that the logs directory exists before attempting to write log files.
'''
import logging
import os


def setup_logger():
    # Create logs directory if needed
    LOG_DIR = os.getenv("LOG_DIR", "logs/")
    os.makedirs(LOG_DIR, exist_ok=True)

    # Configure logger
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(os.path.join(LOG_DIR, "pipeline.log")),
            logging.StreamHandler()  # Also log to console
        ]
    )

    logger = logging.getLogger()
    return logger