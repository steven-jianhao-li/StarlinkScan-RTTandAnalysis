import configparser
import os

def load_config(config_path='configs/default_config.ini'):
    """
    Loads the configuration from a .ini file.

    Args:
        config_path (str): The path to the configuration file.

    Returns:
        configparser.ConfigParser: The loaded configuration object.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")

    config = configparser.ConfigParser()
    # Specify UTF-8 encoding to handle non-ASCII characters in comments
    config.read(config_path, encoding='utf-8')
    return config

if __name__ == '__main__':
    # Example usage:
    # This allows you to run this script directly to test the config loading.
    # Note: You need to run this from the root directory of the project.
    try:
        config = load_config()
        print("Configuration loaded successfully!")
        print("Task Name:", config.get('General', 'task_name'))
        print("Worker Threads:", config.getint('General', 'worker_threads'))
        print("ICMP Enabled:", config.getboolean('ICMP', 'enabled'))
        print("DNS Query Domain:", config.get('DNS', 'query_domain'))
    except (FileNotFoundError, configparser.Error) as e:
        print(f"Error loading configuration: {e}")
