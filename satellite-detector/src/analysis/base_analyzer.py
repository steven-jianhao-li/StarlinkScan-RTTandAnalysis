import pandas as pd
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("SatelliteDetector.BaseAnalyzer")

class BaseAnalyzer(ABC):
    """
    Abstract base class for all data analyzers.
    """
    def __init__(self, task_dir):
        """
        Initializes the base analyzer.

        Args:
            task_dir (str): The path to the task output directory.
        """
        self.task_dir = task_dir
        self.data_file = f"{task_dir}/raw_data.jsonl"
        self.df = None

    def load_data(self):
        """
        Loads data from the raw_data.jsonl file into a pandas DataFrame.
        """
        try:
            logger.info(f"Loading data from {self.data_file}")
            self.df = pd.read_json(self.data_file, lines=True)
            # Convert timestamp to datetime objects
            self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
            logger.info(f"Successfully loaded {len(self.df)} records.")
        except FileNotFoundError:
            logger.error(f"Data file not found: {self.data_file}")
            self.df = pd.DataFrame()
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            self.df = pd.DataFrame()

    @abstractmethod
    def analyze(self):
        """
        Performs the data analysis. Must be implemented by subclasses.
        """
        pass

    def run(self):
        """
        Runs the full analysis pipeline.
        """
        self.load_data()
        if not self.df.empty:
            self.analyze()
        else:
            logger.warning("DataFrame is empty. Skipping analysis.")
