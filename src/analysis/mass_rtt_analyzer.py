import os
import sys
import logging
import pandas as pd
import glob
from pathlib import Path

from src.analysis.plot_utils import (
    save_plot,
    _maybe_add_legend,
)
import matplotlib.pyplot as plt
import seaborn as sns

logger = logging.getLogger("SatelliteDetector.MassRTTAnalyzer")


class MassRTTAnalyzer:
    """
    Analyze mass-scan results where each IP has a CSV file of individual probes.

    Expected input directory structure:
    - <root>/
        <ip1>.csv
        <ip2>.csv
        ...

    CSV schema: timestamp,target_ip,probe_type,rtt_ms,status
    """

    def __init__(self, result_dir: str, analyses: list[str] | None = None):
        self.result_dir = result_dir
        # 支持：summary_by_ip,summary_by_label,mean_hist,mean_vs_loss,kde_by_label,cdf_by_label,box_violin_by_label,topn,hist_by_label,rtt_hist
        self.analyses = analyses or ['summary_by_ip','summary_by_label','mean_hist','mean_vs_loss','kde_by_label','hist_by_label']

    def _do(self, key: str) -> bool:
        return key in self.analyses or 'all' in self.analyses

    def _load_all(self) -> pd.DataFrame:
        # Allow both flat and labeled structure (ground/satellite subfolders)
        p = Path(self.result_dir)
        files = [str(fp) for fp in p.rglob('*.csv') if fp.is_file()]
        if not files:
            logger.warning("No CSV files found for mass analysis.")
            return pd.DataFrame()
        dfs = []
        for f in files:
            try:
                df = pd.read_csv(f)
                # Add label by parent folder name if it's 'ground' or 'satellite'
                parent = Path(f).parent.name.lower()
                if parent in ('ground', 'satellite'):
                    df['label'] = parent
                dfs.append(df)
            except Exception as e:
                logger.warning(f"Skip file {f}: {e}")
        if not dfs:
            return pd.DataFrame()
        df_all = pd.concat(dfs, ignore_index=True)
        # ensure data types
        df_all['rtt_ms'] = pd.to_numeric(df_all['rtt_ms'], errors='coerce')
        try:
            df_all['timestamp'] = pd.to_datetime(df_all['timestamp'])
        except Exception:
            pass
        return df_all

    def analyze(self):
        df = self._load_all()
        if df.empty:
            logger.warning('MassRTTAnalyzer: empty dataset.')
            return

        # success-only RTTs
        ok = df[(df['status'] == 'success') & (df['rtt_ms'].notnull())].copy()

        # Overall RTT histogram（所有数据，不分组）
        if self._do('rtt_hist'):
            fig, ax = plt.subplots(figsize=(12, 7))
            sns.histplot(ok['rtt_ms'], bins=60, stat='density', kde=False, element='step', fill=False, ax=ax)
            ax.set_title('RTT Distribution (All) - Histogram')
            ax.set_xlabel('RTT (ms)')
            ax.set_ylabel('Density')
            ax.set_xlim(left=0)
            fig.tight_layout()
            save_plot(fig, self.result_dir, 'rtt_hist_all.png')

        # Aggregate per IP
        agg = ok.groupby('target_ip')['rtt_ms'].agg(
            count='count', mean='mean', median='median', p95=lambda s: s.quantile(0.95),
            min='min', max='max'
        )

        # Packet loss per IP
        total = df.groupby('target_ip')['status'].size().rename('total')
        non_ok = df[df['status'] != 'success'].groupby('target_ip')['status'].size().rename('non_success')
        summary = agg.join(total, how='outer').join(non_ok, how='left').fillna({'non_success': 0})
        summary['loss_pct'] = (summary['non_success'] / summary['total']).fillna(0) * 100
        summary = summary.sort_values(by='mean', ascending=True)

        out_csv = os.path.join(self.result_dir, 'summary_by_ip.csv')
        summary.to_csv(out_csv)
        logger.info(f"Saved summary: {out_csv}")

        # Plot distribution of mean RTT across IPs
        if self._do('mean_hist'):
            fig, ax = plt.subplots(figsize=(12, 7))
            sns.histplot(summary['mean'].dropna(), bins=40, stat='density', kde=True, ax=ax)
            ax.set_title('Distribution of mean RTT across IPs')
            ax.set_xlabel('Mean RTT (ms)')
            ax.set_ylabel('Density')
            fig.tight_layout()
            save_plot(fig, self.result_dir, 'mean_rtt_across_ips.png')

        # Scatter: mean RTT vs packet loss
        if self._do('mean_vs_loss'):
            fig, ax = plt.subplots(figsize=(12, 7))
            ax.scatter(summary['mean'], summary['loss_pct'], alpha=0.7)
            ax.set_title('Mean RTT vs Packet Loss per IP')
            ax.set_xlabel('Mean RTT (ms)')
            ax.set_ylabel('Packet Loss (%)')
            fig.tight_layout()
            save_plot(fig, self.result_dir, 'mean_vs_loss_scatter.png')

        # Optional: if labels exist, compare distributions per label
        if 'label' in ok.columns and (self._do('summary_by_label') or self._do('kde_by_label') or self._do('cdf_by_label') or self._do('box_violin_by_label') or self._do('hist_by_label')):
            # per-label summary
            if self._do('summary_by_label'):
                label_summary = ok.groupby('label')['rtt_ms'].agg(
                    count='count', mean='mean', median='median', p95=lambda s: s.quantile(0.95)
                )
                label_summary.to_csv(os.path.join(self.result_dir, 'summary_by_label.csv'))

            # KDE per label
            if self._do('kde_by_label'):
                fig, ax = plt.subplots(figsize=(12, 7))
                sns.kdeplot(data=ok, x='rtt_ms', hue='label', common_norm=False, fill=True, clip=(0, None), cut=0, ax=ax)
                ax.set_title('RTT Distribution by Label (KDE)')
                ax.set_xlabel('RTT (ms)')
                ax.set_ylabel('Density')
                ax.set_xlim(left=0)
                fig.tight_layout()
                save_plot(fig, self.result_dir, 'kde_by_label.png')

            # Histogram per label
            if self._do('hist_by_label'):
                fig, ax = plt.subplots(figsize=(12, 7))
                sns.histplot(data=ok, x='rtt_ms', hue='label', bins=60, stat='density', element='step', fill=False, common_norm=False, multiple='layer', ax=ax)
                ax.set_title('RTT Distribution by Label (Histogram)')
                ax.set_xlabel('RTT (ms)')
                ax.set_ylabel('Density')
                ax.set_xlim(left=0)
                fig.tight_layout()
                save_plot(fig, self.result_dir, 'hist_by_label.png')

            # CDF per label
            if self._do('cdf_by_label'):
                fig, ax = plt.subplots(figsize=(12, 7))
                sns.ecdfplot(data=ok, x='rtt_ms', hue='label', complementary=False, ax=ax)
                ax.set_title('RTT CDF by Label')
                ax.set_xlabel('RTT (ms)')
                ax.set_ylabel('CDF')
                ax.set_xlim(left=0)
                fig.tight_layout()
                save_plot(fig, self.result_dir, 'cdf_by_label.png')

            # Box/Violin per label
            if self._do('box_violin_by_label'):
                fig, ax = plt.subplots(figsize=(10, 6))
                sns.boxplot(data=ok, x='label', y='rtt_ms', ax=ax)
                ax.set_title('RTT by Label (Box)')
                ax.set_xlabel('Label')
                ax.set_ylabel('RTT (ms)')
                ax.set_ylim(bottom=0)
                fig.tight_layout()
                save_plot(fig, self.result_dir, 'box_by_label.png')

                fig, ax = plt.subplots(figsize=(10, 6))
                sns.violinplot(data=ok, x='label', y='rtt_ms', inner='quartile', cut=0, ax=ax)
                ax.set_title('RTT by Label (Violin)')
                ax.set_xlabel('Label')
                ax.set_ylabel('RTT (ms)')
                ax.set_ylim(bottom=0)
                fig.tight_layout()
                save_plot(fig, self.result_dir, 'violin_by_label.png')

        # TopN CSVs（低均值/低p95/低丢包 + 反向榜）
        if self._do('topn'):
            for n in (20,):
                # 低值榜
                summary.nsmallest(n, 'mean').to_csv(os.path.join(self.result_dir, f'top{n}_low_mean.csv'))
                summary.nsmallest(n, 'p95').to_csv(os.path.join(self.result_dir, f'top{n}_low_p95.csv'))
                summary.nsmallest(n, 'loss_pct').to_csv(os.path.join(self.result_dir, f'top{n}_low_loss.csv'))
                # 高值榜
                summary.nlargest(n, 'mean').to_csv(os.path.join(self.result_dir, f'top{n}_high_mean.csv'))
                summary.nlargest(n, 'p95').to_csv(os.path.join(self.result_dir, f'top{n}_high_p95.csv'))
                summary.nlargest(n, 'loss_pct').to_csv(os.path.join(self.result_dir, f'top{n}_high_loss.csv'))

    def run(self):
        self.analyze()


if __name__ == '__main__':
    # Standalone run: python src/analysis/mass_rtt_analyzer.py <result_dir>
    if len(sys.argv) != 2:
        print('Usage: python mass_rtt_analyzer.py <result_dir>')
        sys.exit(1)
    rd = sys.argv[1]
    if not os.path.isdir(rd):
        print(f'Directory not found: {rd}')
        sys.exit(1)
    logging.basicConfig(level=logging.INFO)
    MassRTTAnalyzer(rd).run()
