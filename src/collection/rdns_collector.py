import time
import logging
import dns.resolver
import dns.reversename
from .base_collector import BaseCollector

logger = logging.getLogger("SatelliteDetector.RDNSCollector")

class RdnsCollector(BaseCollector):
    """
    Collector to perform reverse DNS (PTR) lookup for the target IP.
    This is metadata-oriented; no RTT value is returned to avoid polluting RTT stats.
    """
    def probe(self):
        """
        Executes a reverse DNS (PTR) query for the target IP using system resolver.

        Returns:
            tuple: (rtt_ms, status, metadata)
        """
        timeout = self.config.getfloat('RDNS', 'timeout', fallback=3.0)
        resolver = dns.resolver.Resolver(configure=True)
        # total lifetime for a query
        resolver.lifetime = timeout

        name = dns.reversename.from_address(self.target_ip)
        metadata = {"ptr_name": None, "query_time_ms": None}

        try:
            start = time.perf_counter()
            answer = resolver.resolve(name, 'PTR', lifetime=timeout)
            end = time.perf_counter()
            ptrs = [str(r.target).rstrip('.') for r in answer]
            metadata["ptr_name"] = ptrs
            metadata["query_time_ms"] = (end - start) * 1000
            logger.debug(f"RDNS PTR for {self.target_ip}: {ptrs}")
            # Return None RTT (metadata only)
            return None, "success", metadata
        except dns.resolver.NXDOMAIN:
            logger.info(f"RDNS: No PTR record for {self.target_ip}")
            metadata["ptr_name"] = []
            return None, "success", metadata
        except dns.exception.Timeout:
            logger.warning(f"RDNS query for {self.target_ip} timed out after {timeout}s.")
            return None, "timeout", metadata
        except Exception as e:
            logger.error(f"RDNS unexpected error for {self.target_ip}: {e}")
            return None, "error", {"error_message": str(e)}
