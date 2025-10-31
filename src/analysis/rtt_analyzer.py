"""
Deprecated module. Kept for backward compatibility.
Please import PairRTTAnalyzer from src.analysis.pair_rtt_analyzer instead.
"""

from src.analysis.pair_rtt_analyzer import PairRTTAnalyzer as RTTAnalyzer

__all__ = ["RTTAnalyzer", "PairRTTAnalyzer"]
