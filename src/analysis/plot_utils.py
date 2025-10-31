import matplotlib.pyplot as plt
import seaborn as sns
import os
import logging

logger = logging.getLogger("SatelliteDetector.PlotUtils")

# Global plotting aesthetics
sns.set_theme(context='talk', style='whitegrid', palette='Set2')
plt.rcParams.update({
    'axes.titlesize': 16,
    'axes.labelsize': 14,
    'legend.fontsize': 11,
    'xtick.labelsize': 11,
    'ytick.labelsize': 11,
})

def save_plot(fig, save_dir, filename, dpi=300):
    """
    Saves a matplotlib figure to a specified directory.

    Args:
        fig (matplotlib.figure.Figure): The figure object to save.
        save_dir (str): The directory to save the plot in.
        filename (str): The name of the output file.
        dpi (int): The resolution of the saved image.
    """
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    save_path = os.path.join(save_dir, filename)
    try:
        fig.savefig(save_path, dpi=dpi, bbox_inches='tight')
        logger.info(f"Plot saved to {save_path}")
        plt.close(fig)  # Close the figure to free up memory
    except Exception as e:
        logger.error(f"Failed to save plot {filename}: {e}")

def _maybe_add_legend(ax, title=None):
    handles, labels = ax.get_legend_handles_labels()
    if labels:
        ax.legend(title=title, ncol=2, frameon=True)
    else:
        legend = ax.get_legend()
        if legend:
            legend.remove()


def _ensure_non_negative_rtt(df, col='rtt_ms'):
    """
    Return a copy of df where RTT values are non-negative.
    If negative values exist, they will be clipped to 0 for visualization.
    """
    if df[col].min() < 0:
        df = df.copy()
        df[col] = df[col].clip(lower=0)
    return df


def _auto_hue(df):
    """Choose hue automatically: prefer probe_type when it has >1 unique values, else target_ip."""
    if 'probe_type' in df.columns and df['probe_type'].nunique() > 1:
        return 'probe_type', 'Probe Type'
    return 'target_ip', 'Target IP'


def plot_rtt_timeseries(df, save_dir, filename_prefix="combined"):
    """
    Plots RTT over time for each target IP and probe type.
    """
    fig, ax = plt.subplots(figsize=(16, 7))

    # Draw smoother lines without markers; separate hue/style
    sns.lineplot(
        data=df.sort_values('timestamp'),
        x='timestamp', y='rtt_ms',
        hue='target_ip', style='probe_type',
        ax=ax, linewidth=1.6, alpha=0.9, marker=None, errorbar=None
    )

    ax.set_title('RTT Time Series')
    ax.set_xlabel('Timestamp')
    ax.set_ylabel('RTT (ms)')
    _maybe_add_legend(ax, title='Target & Type')
    ax.tick_params(axis='x', rotation=30)

    fig.tight_layout()
    save_plot(fig, save_dir, f'{filename_prefix}_rtt_timeseries.png')

def plot_rtt_distribution(df, save_dir, filename_prefix="combined", hue: str | None = None):
    """
    Plot RTT distribution (KDE).

    - Adds legend automatically.
    - Ensures density is not drawn for negative RTTs.
    - If hue is None, chooses 'probe_type' when both DNS/ICMP exist; else 'target_ip'.
    """
    fig, ax = plt.subplots(figsize=(12, 7))

    df_plot = _ensure_non_negative_rtt(df)
    # Decide hue and legend title
    if hue is None:
        hue, legend_title = _auto_hue(df_plot)
    else:
        legend_title = 'Probe Type' if hue == 'probe_type' else 'Target IP'

    sns.kdeplot(
        data=df_plot,
        x='rtt_ms',
        hue=hue,
        fill=True,
        common_norm=False,
        alpha=0.25,
        linewidth=1.5,
        ax=ax,
        clip=(0, None),  # do not draw negative densities
        cut=0,
    )

    ax.set_title('RTT Distribution (KDE)')
    ax.set_xlabel('RTT (ms)')
    ax.set_ylabel('Density')
    ax.set_xlim(left=0)
    _maybe_add_legend(ax, title=legend_title)

    fig.tight_layout()
    save_plot(fig, save_dir, f'{filename_prefix}_rtt_distribution_kde.png')

def plot_rtt_boxplot(df, save_dir, filename_prefix="combined"):
    """
    Creates a box plot to compare RTT distributions for each target IP.
    """
    fig, ax = plt.subplots(figsize=(12, 8))

    sns.boxplot(
        data=df, x='target_ip', y='rtt_ms', hue='probe_type',
        ax=ax, linewidth=1.2, fliersize=2
    )

    ax.set_title('RTT Distribution Comparison (Box Plot)')
    ax.set_xlabel('Target IP')
    ax.set_ylabel('RTT (ms)')
    ax.tick_params(axis='x', rotation=30)
    _maybe_add_legend(ax, title='Probe Type')

    fig.tight_layout()
    save_plot(fig, save_dir, f'{filename_prefix}_rtt_boxplot.png')


def plot_rtt_histogram(
    df,
    save_dir,
    filename_prefix: str = "combined",
    bins: int = 50,
    kde: bool = False,
    hue: str | None = None,
):
    """Plot RTT histogram with optional KDE overlay.

    - Non-negative RTTs enforced.
    - If hue is None, selects automatically (probe_type preferred when available).
    """
    fig, ax = plt.subplots(figsize=(12, 7))

    df_plot = _ensure_non_negative_rtt(df)
    if hue is None:
        hue, legend_title = _auto_hue(df_plot)
    else:
        legend_title = 'Probe Type' if hue == 'probe_type' else 'Target IP'

    sns.histplot(
        data=df_plot,
        x='rtt_ms',
        hue=hue,
        bins=bins,
        stat='density',
        common_norm=False,
        multiple='layer',
        element='step',
        fill=False,
        ax=ax,
    )

    if kde:
        sns.kdeplot(
            data=df_plot,
            x='rtt_ms',
            hue=hue,
            common_norm=False,
            ax=ax,
            clip=(0, None),
            cut=0,
            linewidth=1.2,
            alpha=0.9,
        )

    ax.set_title('RTT Distribution (Histogram)')
    ax.set_xlabel('RTT (ms)')
    ax.set_ylabel('Density')
    ax.set_xlim(left=0)
    _maybe_add_legend(ax, title=legend_title)

    fig.tight_layout()
    save_plot(fig, save_dir, f'{filename_prefix}_rtt_histogram.png')
