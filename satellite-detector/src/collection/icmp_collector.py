import ping3
import logging
from .base_collector import BaseCollector

logger = logging.getLogger("SatelliteDetector.ICMPCollector")

class IcmpCollector(BaseCollector):
    """
    Collector for ICMP RTT measurements using ping.
    """
    def probe(self):
        """
        Executes a single ICMP ping to the target IP.

        Returns:
            tuple: (rtt_ms, status, metadata)
        """
        timeout = self.config.getint('ICMP', 'timeout', fallback=2)
        packet_size = self.config.getint('ICMP', 'packet_size', fallback=56)
        
        try:
            rtt = ping3.ping(self.target_ip, unit='ms', timeout=timeout, size=packet_size)
            
            if rtt is False:
                # Destination Unreachable or other ICMP error
                logger.warning(f"ICMP probe to {self.target_ip} failed (Destination Unreachable).")
                return None, "error", {"error_message": "Destination Unreachable"}
            elif rtt is None:
                # Timeout
                logger.warning(f"ICMP probe to {self.target_ip} timed out after {timeout}s.")
                return None, "timeout", {}
            else:
                # Success
                logger.debug(f"ICMP probe to {self.target_ip} success: {rtt:.2f} ms.")
                return rtt, "success", {}

        except PermissionError:
            logger.error(
                f"Permission denied for ICMP probe to {self.target_ip}. "
                "Raw sockets often require root/administrator privileges."
            )
            # This is a fatal error for this collector, so we return an error status.
            # The main loop will catch the exception from run_probe.
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred during ICMP probe to {self.target_ip}: {e}")
            return None, "error", {"error_message": str(e)}
