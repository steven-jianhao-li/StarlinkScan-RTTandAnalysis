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
)
from src.utils.logger_setup import setup_logger

logger = logging.getLogger("SatelliteDetector.RTTAnalyzer")

class RTTAnalyzer(BaseAnalyzer):
    """
    Performs RTT analysis, including statistics, packet loss,
    and generates visualizations.
    """
    def analyze(self):
        """
        The main analysis pipeline for RTT data.
        """
        logger.info("Starting RTT analysis...")
        
        # --- Data Cleaning ---
        # 仅使用成功且具有 RTT 数值的条目进行 RTT 统计与绘图
        success_df = self.df[(self.df['status'] == 'success') & (self.df['rtt_ms'].notnull())].copy()
        if success_df.empty:
            logger.warning("No successful probes found. Cannot perform RTT analysis.")
            return

        # --- Analysis ---
        self.calculate_packet_loss()
        self.calculate_descriptive_stats(success_df)
        self.perform_ks_test(success_df)

        # --- Visualization ---
        plot_dir = os.path.join(self.task_dir, 'plots')
        plot_rtt_timeseries(success_df, plot_dir)
        plot_rtt_distribution(success_df, plot_dir)
        plot_rtt_boxplot(success_df, plot_dir)
        
        logger.info("RTT analysis complete.")

    def calculate_packet_loss(self):
        """Calculates and logs the packet loss percentage for each target."""
        logger.info("--- Packet Loss Calculation ---")
        for target, group in self.df.groupby('target_ip'):
            total_probes = len(group)
            non_success_probes = len(group[group['status'] != 'success'])
            loss_percentage = (non_success_probes / total_probes) * 100
            logger.info(f"Target: {target} -> Packet Loss: {loss_percentage:.2f}% ({non_success_probes}/{total_probes})")

    def calculate_descriptive_stats(self, df):
        """Calculates and logs descriptive statistics for RTTs."""
        logger.info("--- Descriptive RTT Statistics (ms) ---")
        stats_df = df.groupby(['target_ip', 'probe_type'])['rtt_ms'].describe()
        logger.info("\n" + stats_df.to_string())

    def perform_ks_test(self, df):
        """
        Performs a Kolmogorov-Smirnov test between RTT distributions
        if there are exactly two target IPs to compare.
        """
        targets = df['target_ip'].unique()
        if len(targets) == 2:
            logger.info("--- Kolmogorov-Smirnov (K-S) Test ---")
            ip1, ip2 = targets[0], targets[1]
            # Extract RTT samples for each target separately
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
            else:
                logger.warning("Not enough data for one or both targets to perform K-S test.")
        else:
            logger.info("Skipping K-S test: requires exactly two target IPs for comparison.")


if __name__ == '__main__':
    # This allows the script to be run directly for analysis.
    # Example: python src/analysis/rtt_analyzer.py data/output/Your_Task_ID
    if len(sys.argv) != 2:
        print("Usage: python rtt_analyzer.py <path_to_task_directory>")
        sys.exit(1)
    
    task_directory = sys.argv[1]
    if not os.path.isdir(task_directory):
        print(f"Error: Directory not found at '{task_directory}'")
        sys.exit(1)

    # Setup a basic logger for standalone execution
    setup_logger(task_directory, log_level='INFO')
    
    analyzer = RTTAnalyzer(task_directory)
    analyzer.run()
