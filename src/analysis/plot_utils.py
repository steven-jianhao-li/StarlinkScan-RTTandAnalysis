import matplotlib.pyplot as plt
import seaborn as sns
import os
import logging

logger = logging.getLogger("SatelliteDetector.PlotUtils")

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

def plot_rtt_timeseries(df, save_dir):
    """
    Plots RTT over time for each target IP and probe type.
    """
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(15, 7))
    
    sns.lineplot(data=df, x='timestamp', y='rtt_ms', hue='target_ip', style='probe_type', ax=ax, marker='o', markersize=4)
    
    ax.set_title('RTT Time Series')
    ax.set_xlabel('Timestamp')
    ax.set_ylabel('RTT (ms)')
    ax.legend(title='Target & Type')
    ax.tick_params(axis='x', rotation=45)
    
    fig.tight_layout()
    save_plot(fig, save_dir, 'rtt_timeseries.png')

def plot_rtt_distribution(df, save_dir):
    """
    Plots the RTT distribution (KDE) for each target IP.
    """
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(12, 7))
    
    sns.kdeplot(data=df, x='rtt_ms', hue='target_ip', fill=True, common_norm=False, ax=ax)
    
    ax.set_title('RTT Distribution (KDE)')
    ax.set_xlabel('RTT (ms)')
    ax.set_ylabel('Density')
    ax.legend(title='Target IP')
    
    fig.tight_layout()
    save_plot(fig, save_dir, 'rtt_distribution_kde.png')

def plot_rtt_boxplot(df, save_dir):
    """
    Creates a box plot to compare RTT distributions for each target IP.
    """
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 8))
    
    sns.boxplot(data=df, x='target_ip', y='rtt_ms', hue='probe_type', ax=ax)
    
    ax.set_title('RTT Distribution Comparison (Box Plot)')
    ax.set_xlabel('Target IP')
    ax.set_ylabel('RTT (ms)')
    ax.tick_params(axis='x', rotation=45)
    
    fig.tight_layout()
    save_plot(fig, save_dir, 'rtt_boxplot.png')
