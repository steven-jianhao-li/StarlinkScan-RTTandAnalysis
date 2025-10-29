import logging
from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger("SatelliteDetector.Collector")

class BaseCollector(ABC):
    """
    Abstract base class for all probe collectors.
    """
    def __init__(self, target_ip, config, output_queue):
        """
        Initializes the base collector.

        Args:
            target_ip (str): The target IP address to probe.
            config (configparser.ConfigParser): The application configuration.
            output_queue (multiprocessing.Queue): The queue to put results into.
        """
        self.target_ip = target_ip
        self.config = config
        self.output_queue = output_queue
        self.probe_type = self.__class__.__name__.replace('Collector', '').lower()

    @abstractmethod
    def probe(self):
        """
        Executes a single probe action.
        This method must be implemented by subclasses.

        Returns:
            tuple: A tuple containing (rtt_ms, status, metadata).
                   - rtt_ms (float or None): The round-trip time in milliseconds.
                   - status (str): 'success', 'timeout', or 'error'.
                   - metadata (dict): Any additional probe-specific information.
        """
        pass

    def run_probe(self):
        """
        A wrapper for the probe() method that handles exceptions,
        formats the result, and puts it into the output queue.
        """
        try:
            rtt_ms, status, metadata = self.probe()
            timestamp = datetime.utcnow().isoformat()

            result = {
                "timestamp": timestamp,
                "target_ip": self.target_ip,
                "probe_type": self.probe_type,
                "rtt_ms": rtt_ms,
                "status": status,
                "metadata": metadata
            }
            
            if self.output_queue:
                self.output_queue.put(result)
                logger.debug(f"Successfully queued result for {self.target_ip} via {self.probe_type}")

        except Exception as e:
            logger.error(f"Exception in {self.probe_type} probe for {self.target_ip}: {e}", exc_info=True)
            # Optionally, you could put an error result in the queue
            error_result = {
                "timestamp": datetime.utcnow().isoformat(),
                "target_ip": self.target_ip,
                "probe_type": self.probe_type,
                "rtt_ms": None,
                "status": "error",
                "metadata": {"error_message": str(e)}
            }
            if self.output_queue:
                self.output_queue.put(error_result)
