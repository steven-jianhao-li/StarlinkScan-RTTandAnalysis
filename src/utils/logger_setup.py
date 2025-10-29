import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger(log_dir, log_level='INFO', log_format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'):
    """
    Sets up the logger for the application.

    Args:
        log_dir (str): The directory where the log file will be stored.
        log_level (str): The logging level (e.g., 'INFO', 'DEBUG').
        log_format (str): The format for the log messages.

    Returns:
        logging.Logger: The configured logger object.
    """
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, 'task.log')

    logger = logging.getLogger("SatelliteDetector")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Prevent adding multiple handlers if the function is called more than once
    if logger.hasHandlers():
        logger.handlers.clear()

    # Create a console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(console_handler)

    # Create a rotating file handler
    file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
    file_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(file_handler)

    return logger

if __name__ == '__main__':
    # Example usage:
    # This allows you to run this script directly to test the logger setup.
    # Note: You need to run this from the root directory of the project.
    
    # Create a dummy log directory for testing
    test_log_dir = 'data/output/test_log_dir'
    
    try:
        logger = setup_logger(test_log_dir, log_level='DEBUG')
        logger.debug("This is a debug message.")
        logger.info("This is an info message.")
        logger.warning("This is a warning message.")
        logger.error("This is an error message.")
        logger.critical("This is a critical message.")
        print(f"Logger setup complete. Log file created at: {os.path.join(test_log_dir, 'task.log')}")
    except Exception as e:
        print(f"Error setting up logger: {e}")
