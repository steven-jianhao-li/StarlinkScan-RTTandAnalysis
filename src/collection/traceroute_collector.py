import os
import re
import platform
import subprocess
import logging
from .base_collector import BaseCollector

logger = logging.getLogger("SatelliteDetector.TracerouteCollector")

class TracerouteCollector(BaseCollector):
    """
    Collector that performs a traceroute to the target IP and records hop RTTs as metadata.
    This collector is heavier and typically scheduled to run once per task.
    """
    def probe(self):
        """
        Executes a traceroute (Windows: tracert, Unix: traceroute) and parses output.

        Returns:
            tuple: (rtt_ms, status, metadata) where rtt_ms is None and metadata contains hops.
        """
        timeout = self.config.getfloat('Traceroute', 'timeout', fallback=3.0)
        max_hops = self.config.getint('Traceroute', 'max_hops', fallback=20)
        queries = self.config.getint('Traceroute', 'queries_per_hop', fallback=3)

        system = platform.system()

        # Build command per platform
        if system == 'Windows':
            # -d: don't resolve names, -h max hops, -w timeout(ms)
            cmd = [
                'tracert', '-d',
                '-h', str(max_hops),
                '-w', str(int(timeout * 1000)),
                self.target_ip
            ]
        else:
            # -n no DNS, -m max hops, -w wait (per probe), -q queries per hop
            cmd = [
                'traceroute', '-n',
                '-m', str(max_hops),
                '-w', str(timeout),
                '-q', str(queries),
                self.target_ip
            ]

        try:
            logger.debug(f"Running traceroute: {' '.join(cmd)}")
            # Give a generous timeout: per-hop * max_hops * (queries+1)
            overall_timeout = max(10, int((timeout * max_hops * (queries + 1)) + 5))
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=overall_timeout,
                check=False
            )

            output = proc.stdout or ''
            if not output and proc.stderr:
                output = proc.stderr

            hops = self._parse_output(output, system)
            destination_reached = any(h.get('ip') == self.target_ip for h in hops)

            metadata = {
                'hops': hops,
                'destination_reached': destination_reached,
                'exit_code': proc.returncode
            }

            status = 'success' if hops else 'error'
            return None, status, metadata
        except subprocess.TimeoutExpired:
            logger.warning("Traceroute timed out before completion.")
            return None, 'timeout', {}
        except FileNotFoundError:
            logger.error("Traceroute command not found. Please ensure 'traceroute' (Linux/Mac) or 'tracert' (Windows) is available.")
            return None, 'error', {'error_message': 'traceroute/tracert not found'}
        except Exception as e:
            logger.error(f"Traceroute unexpected error: {e}")
            return None, 'error', {'error_message': str(e)}

    def _parse_output(self, text, system):
        """Parses traceroute/tracert plain text into a list of hop dicts."""
        hops = []
        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            # Skip headers/blank
            if not line:
                continue
            # Windows example: "  1     1 ms     1 ms     1 ms  192.168.0.1"
            # Linux example:   " 1  192.168.0.1  0.345 ms  0.220 ms  0.190 ms"
            m = re.match(r"^(\d+)\s+(.*)$", line)
            if not m:
                continue
            hop_no = int(m.group(1))
            rest = m.group(2)

            # Extract IP (last IPv4/IPv6 token) and RTT values
            ip = None
            rtts = []

            # Pick all occurrences of "<num> ms" (Windows may show '<1 ms')
            for ms in re.findall(r"(\d+)\s*ms", rest.replace('<', '')):
                try:
                    rtts.append(float(ms))
                except ValueError:
                    pass

            # Find IP address (prefer last IPv4/IPv6 token)
            # IPv4
            ipv4s = re.findall(r"(\d+\.\d+\.\d+\.\d+)", rest)
            # IPv6 (simple heuristic)
            ipv6s = re.findall(r"([0-9a-fA-F:]{2,})", rest)

            if ipv4s:
                ip = ipv4s[-1]
            elif ipv6s:
                # Filter out pure RTT units accidentally matched
                ip = [x for x in ipv6s if ':' in x][-1] if any(':' in x for x in ipv6s) else None

            avg_ms = sum(rtts) / len(rtts) if rtts else None
            hops.append({
                'hop': hop_no,
                'ip': ip,
                'rtts_ms': rtts,
                'avg_ms': avg_ms
            })
        return hops
