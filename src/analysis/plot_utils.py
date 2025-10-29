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

def plot_rtt_distribution(df, save_dir, filename_prefix="combined"):
    """
    Plots the RTT distribution (KDE) for each target IP.
    """
    fig, ax = plt.subplots(figsize=(12, 7))

    sns.kdeplot(
        data=df, x='rtt_ms', hue='target_ip', fill=True,
        common_norm=False, alpha=0.25, linewidth=1.5, ax=ax
    )

    ax.set_title('RTT Distribution (KDE)')
    ax.set_xlabel('RTT (ms)')
    ax.set_ylabel('Density')
    _maybe_add_legend(ax, title='Target IP')

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
