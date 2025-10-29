import dns.message
import dns.query
import dns.rdatatype
import time
import logging
from .base_collector import BaseCollector

logger = logging.getLogger("SatelliteDetector.DNSCollector")

class DnsCollector(BaseCollector):
    """
    Collector for DNS query RTT measurements.
    """
    def probe(self):
        """
        Executes a single DNS query to the target IP and measures the RTT.

        Returns:
            tuple: (rtt_ms, status, metadata)
        """
        domain = self.config.get('DNS', 'query_domain', fallback='google.com')
        qtype_str = self.config.get('DNS', 'query_type', fallback='A')
        timeout = self.config.getfloat('DNS', 'timeout', fallback=3.0)
        
        qtype = dns.rdatatype.from_text(qtype_str)
        request = dns.message.make_query(domain, qtype)
        
        metadata = {
            "query_domain": domain,
            "query_type": qtype_str
        }

        try:
            start_time = time.perf_counter()
            # Use UDP for standard queries, sending the query specifically to the target IP
            response = dns.query.udp(request, self.target_ip, timeout=timeout)
            end_time = time.perf_counter()

            if response:
                rtt_ms = (end_time - start_time) * 1000
                logger.debug(f"DNS probe to {self.target_ip} for {domain} [{qtype_str}] success: {rtt_ms:.2f} ms.")
                return rtt_ms, "success", metadata
            else:
                # This case is unlikely with dns.query.udp as it usually raises an exception on failure
                logger.warning(f"DNS probe to {self.target_ip} for {domain} returned no response.")
                return None, "error", {"error_message": "No response"}

        except dns.exception.Timeout:
            logger.warning(f"DNS probe to {self.target_ip} timed out after {timeout}s.")
            return None, "timeout", metadata
        except Exception as e:
            logger.error(f"An unexpected error occurred during DNS probe to {self.target_ip}: {e}")
            return None, "error", {"error_message": str(e)}
