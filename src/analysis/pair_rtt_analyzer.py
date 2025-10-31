import os
import sys
import logging
import pandas as pd
from scipy import stats

# Ensure the src directory is in the Python path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
sys.path.append(PROJECT_ROOT)

from src.analysis.base_analyzer import BaseAnalyzer
from src.analysis.plot_utils import (
    plot_rtt_timeseries,
    plot_rtt_distribution,
    plot_rtt_boxplot,
    plot_rtt_histogram,
)
from src.utils.logger_setup import setup_logger

logger = logging.getLogger("SatelliteDetector.PairRTTAnalyzer")


class PairRTTAnalyzer(BaseAnalyzer):
    """
    Performs RTT analysis for the classic two-point scenario (e.g., ground vs satellite),
    including statistics, packet loss, and visualizations.
    """

    def __init__(self, task_dir, analyses: list[str] | None = None):
        super().__init__(task_dir)
        # 支持的分析项：timeseries,kde,hist,box,ks,summary,loss
        self.analyses = analyses or ['timeseries','kde','hist','box','ks','summary','loss']

    def _do(self, key: str) -> bool:
        return key in self.analyses or 'all' in self.analyses

    def analyze(self):
        """
        The main analysis pipeline for RTT data.
        """
        logger.info("Starting RTT analysis (pair mode)...")

        # Only successful RTT entries with numeric values
        success_df = self.df[(self.df['status'] == 'success') & (self.df['rtt_ms'].notnull())].copy()
        if success_df.empty:
            logger.warning("No successful probes found. Cannot perform RTT analysis.")
            return

        # --- Analysis ---
        if self._do('loss'):
            self.calculate_packet_loss()
        if self._do('summary'):
            self.calculate_descriptive_stats(success_df)
        if self._do('ks'):
            self.perform_ks_test(success_df)

        # --- Visualization ---
        plot_dir = os.path.join(self.task_dir, 'plots')
        # Combined
        if self._do('timeseries'):
            plot_rtt_timeseries(success_df, plot_dir, filename_prefix='combined')
        if self._do('kde'):
            plot_rtt_distribution(success_df, plot_dir, filename_prefix='combined')
        if self._do('hist'):
            plot_rtt_histogram(success_df, plot_dir, filename_prefix='combined', bins=50, kde=False)
        if self._do('box'):
            plot_rtt_boxplot(success_df, plot_dir, filename_prefix='combined')
        # Per-type
        icmp_df = success_df[success_df['probe_type'] == 'icmp']
        if not icmp_df.empty:
            if self._do('timeseries'):
                plot_rtt_timeseries(icmp_df, plot_dir, filename_prefix='icmp')
            if self._do('kde'):
                plot_rtt_distribution(icmp_df, plot_dir, filename_prefix='icmp')
            if self._do('hist'):
                plot_rtt_histogram(icmp_df, plot_dir, filename_prefix='icmp', bins=50, kde=False)
            if self._do('box'):
                plot_rtt_boxplot(icmp_df, plot_dir, filename_prefix='icmp')
        dns_df = success_df[success_df['probe_type'] == 'dns']
        if not dns_df.empty:
            if self._do('timeseries'):
                plot_rtt_timeseries(dns_df, plot_dir, filename_prefix='dns')
            if self._do('kde'):
                plot_rtt_distribution(dns_df, plot_dir, filename_prefix='dns')
            if self._do('hist'):
                plot_rtt_histogram(dns_df, plot_dir, filename_prefix='dns', bins=50, kde=False)
            if self._do('box'):
                plot_rtt_boxplot(dns_df, plot_dir, filename_prefix='dns')

        # --- Export analysis artifacts ---
        pkt_loss_records = []
        for target, group in self.df.groupby('target_ip'):
            total_probes = len(group)
            non_success = len(group[group['status'] != 'success'])
            loss_pct = (non_success / total_probes) * 100 if total_probes else 0.0
            pkt_loss_records.append({
                'target_ip': target,
                'total_probes': total_probes,
                'non_success': non_success,
                'packet_loss_percent': round(loss_pct, 3)
            })

        import pandas as _pd
        pd_pkt = _pd.DataFrame(pkt_loss_records)
        pd_pkt.to_csv(os.path.join(self.task_dir, 'packet_loss.csv'), index=False)

        stats_df = success_df.groupby(['target_ip', 'probe_type'])['rtt_ms'].describe()
        stats_df.to_csv(os.path.join(self.task_dir, 'descriptive_stats.csv'))

        ks_result = self.perform_ks_test(success_df, return_result=True)
        if ks_result:
            import json as _json
            with open(os.path.join(self.task_dir, 'ks_test.json'), 'w', encoding='utf-8') as f:
                _json.dump(ks_result, f, ensure_ascii=False, indent=2)

        logger.info("RTT analysis (pair mode) complete.")

    def calculate_packet_loss(self):
        """Calculates and logs the packet loss percentage for each target."""
        logger.info("--- Packet Loss Calculation ---")
        for target, group in self.df.groupby('target_ip'):
            total_probes = len(group)
            non_success_probes = len(group[group['status'] != 'success'])
            loss_percentage = (non_success_probes / total_probes) * 100
            logger.info(f"Target: {target} -> Packet Loss: {loss_percentage:.2f}% ({non_success_probes}/{total_probes})")

    def calculate_descriptive_stats(self, df):
        """Calculates and logs descriptive statistics for RTTs. Returns DataFrame."""
        logger.info("--- Descriptive RTT Statistics (ms) ---")
        stats_df = df.groupby(['target_ip', 'probe_type'])['rtt_ms'].describe()
        logger.info("\n" + stats_df.to_string())
        return stats_df

    def perform_ks_test(self, df, return_result=False):
        """
        Performs a Kolmogorov-Smirnov test between RTT distributions
        if there are exactly two target IPs to compare.
        """
        targets = df['target_ip'].unique()
        if len(targets) == 2:
            logger.info("--- Kolmogorov-Smirnov (K-S) Test ---")
            ip1, ip2 = targets[0], targets[1]
            rtt_data_1 = df.loc[df['target_ip'] == ip1, 'rtt_ms'].dropna()
            rtt_data_2 = df.loc[df['target_ip'] == ip2, 'rtt_ms'].dropna()

            if len(rtt_data_1) > 1 and len(rtt_data_2) > 1:
                ks_statistic, p_value = stats.ks_2samp(rtt_data_1, rtt_data_2)
                logger.info(f"Comparing '{ip1}' and '{ip2}':")
                logger.info(f"  K-S Statistic: {ks_statistic:.4f}")
                logger.info(f"  P-value: {p_value:.4g}")
                if p_value < 0.05:
                    logger.info("  Conclusion: The RTT distributions are significantly different (P < 0.05).")
                else:
                    logger.info("  Conclusion: No significant difference detected between RTT distributions (P >= 0.05).")
                if return_result:
                    return {
                        'target_1': ip1,
                        'target_2': ip2,
                        'ks_statistic': float(f"{ks_statistic:.6f}"),
                        'p_value': float(f"{p_value:.6g}"),
                        'significant': bool(p_value < 0.05)
                    }
            else:
                logger.warning("Not enough data for one or both targets to perform K-S test.")
                if return_result:
                    return {
                        'note': 'insufficient_samples',
                        'counts': {targets[0]: int(len(rtt_data_1)), targets[1]: int(len(rtt_data_2))}
                    }
        else:
            logger.info("Skipping K-S test: requires exactly two target IPs for comparison.")
            if return_result:
                return {'note': 'requires_two_targets', 'targets_found': [str(t) for t in targets.tolist()]}
        if return_result:
            return None


if __name__ == '__main__':
    # Standalone execution
    if len(sys.argv) != 2:
        print("Usage: python pair_rtt_analyzer.py <path_to_task_directory>")
        sys.exit(1)

    task_directory = sys.argv[1]
    if not os.path.isdir(task_directory):
        print(f"Error: Directory not found at '{task_directory}'")
        sys.exit(1)

    setup_logger(task_directory, log_level='INFO')

    analyzer = PairRTTAnalyzer(task_directory)
    analyzer.run()
