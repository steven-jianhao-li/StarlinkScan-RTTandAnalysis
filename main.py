import os
import sys
import time
import shutil
import json
from datetime import datetime
from multiprocessing import Queue, Process
import signal
import logging

# --- Path Setup ---
# This ensures that the script can be run from anywhere and still find its modules and config file.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = SCRIPT_DIR
sys.path.append(SCRIPT_DIR)

from src.utils.config_loader import load_config
from src.utils.logger_setup import setup_logger
from src.collection.icmp_collector import IcmpCollector
from src.collection.dns_collector import DnsCollector

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

# --- Global Variables ---
config = None
logger = None
output_queue = None  # Will be created in main() to avoid Windows spawn issues

def get_task_id(task_name, targets):
    """Generates a unique ID for the current task."""
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    # Use a sanitized version of the first target for brevity
    first_target = targets.replace('.', '_') if targets else 'no_targets'
    return f"{task_name}_{first_target}_{timestamp}"

def load_targets(target_file):
    """Loads target IPs from the specified file."""
    if not os.path.exists(target_file):
        # Use print here because logger might not be initialized yet
        print(f"ERROR: Target file not found: {target_file}", file=sys.stderr)
        return []
    with open(target_file, 'r', encoding='utf-8') as f:
        targets = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    # Logger will be available after this function is called in main
    if logger:
        logger.info(f"Loaded {len(targets)} targets from {target_file}")
    else:
        print(f"INFO: Loaded {len(targets)} targets from {target_file}")
    return targets

def io_writer_process(queue, output_file, log_dir, log_level, log_format):
    """
    A dedicated process to write results from the queue to a file.
    This avoids I/O blocking in the worker threads.
    """
    # Logger must be configured within the new process
    writer_logger = setup_logger(log_dir, log_level, log_format)
    writer_logger.info(f"I/O writer process started. Writing to {output_file}")
    
    # Use a different file for the writer's log to avoid conflicts
    handler_index = -1
    for i, handler in enumerate(writer_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            handler_index = i
            break
    if handler_index != -1:
        writer_logger.handlers[handler_index].close()
        writer_logger.removeHandler(writer_logger.handlers[handler_index])
        writer_log_file = os.path.join(log_dir, 'io_writer.log')
        file_handler = logging.FileHandler(writer_log_file)
        file_handler.setFormatter(logging.Formatter(log_format))
        writer_logger.addHandler(file_handler)

    with open(output_file, 'a', encoding='utf-8') as f:
        while True:
            try:
                result = queue.get()
                if result is None:  # Sentinel value to stop the process
                    writer_logger.info("I/O writer process received stop signal. Shutting down.")
                    break
                # Serialize dict to a JSON string before writing
                f.write(json.dumps(result) + '\n')
                f.flush()
            except (KeyboardInterrupt, SystemExit):
                break
            except Exception as e:
                writer_logger.error(f"I/O writer process encountered an error: {e}", exc_info=True)
    writer_logger.info("I/O writer process finished.")


def main():
    global config, logger, output_queue

    # 1. Load Configuration
    try:
        config_path = os.path.join(PROJECT_ROOT, 'configs', 'default_config.ini')
        config = load_config(config_path)
    except FileNotFoundError as e:
        print(f"FATAL: Configuration file not found. {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Load Targets
    target_file_path = os.path.join(PROJECT_ROOT, config.get('General', 'target_file'))
    targets = load_targets(target_file_path)
    if not targets:
        print("FATAL: No targets to probe. Exiting.", file=sys.stderr)
        sys.exit(1)

    # 3. Setup Task Directory and Logging
    task_name = config.get('General', 'task_name')
    # Convert list of targets to a string for the task ID
    task_id = get_task_id(task_name, "_".join(targets))
    task_dir = os.path.join(PROJECT_ROOT, 'data', 'output', task_id)
    os.makedirs(task_dir, exist_ok=True)

    log_level = config.get('Logging', 'level', fallback='INFO')
    # Use raw=True to prevent interpolation of '%' characters in the log format string
    log_format = config.get('Logging', 'format', raw=True)
    
    logger = setup_logger(
        log_dir=task_dir,
        log_level=log_level,
        log_format=log_format
    )
    logger.info(f"Task '{task_id}' starting.")

    # 4. Save a snapshot of the config for reproducibility
    config_snapshot_path = os.path.join(PROJECT_ROOT, 'configs', 'default_config.ini')
    shutil.copy(config_snapshot_path, os.path.join(task_dir, 'config.ini'))
    logger.info(f"Saved configuration snapshot to {task_dir}")

    # 5. Snapshot inputs for reproducibility
    try:
        shutil.copy(target_file_path, os.path.join(task_dir, 'targets.txt'))
        logger.info("Saved targets snapshot.")
    except Exception as e:
        logger.warning(f"Failed to snapshot targets file: {e}")

    # 6. Start I/O Writer Process
    output_queue = Queue()
    output_file = os.path.join(task_dir, 'raw_data.jsonl')
    io_process = Process(
        target=io_writer_process,
        args=(output_queue, output_file, task_dir, log_level, log_format)
    )
    io_process.start()

    # 7. Configure Scheduler and Thread Pool
    executors = {
        'default': ThreadPoolExecutor(config.getint('General', 'worker_threads', fallback=10))
    }
    job_defaults = {
        'coalesce': True,                 # Combine missed runs into one
        'max_instances': 1,               # Avoid overlapping probes per job
        'misfire_grace_time': 10          # Seconds to allow late runs
    }
    scheduler = BackgroundScheduler(executors=executors, job_defaults=job_defaults)

    # 8. Schedule Probing Jobs
    probe_interval = config.getint('Scheduler', 'probe_interval_seconds', fallback=1)
    
    for target_ip in targets:
        if config.getboolean('ICMP', 'enabled', fallback=False):
            icmp_collector = IcmpCollector(target_ip, config, output_queue)
            scheduler.add_job(
                icmp_collector.run_probe,
                'interval',
                seconds=probe_interval,
                id=f'icmp_{target_ip}',
                replace_existing=True
            )
            logger.info(f"Scheduled ICMP probes for {target_ip} every {probe_interval}s.")

        if config.getboolean('DNS', 'enabled', fallback=False):
            dns_collector = DnsCollector(target_ip, config, output_queue)
            scheduler.add_job(
                dns_collector.run_probe,
                'interval',
                seconds=probe_interval,
                id=f'dns_{target_ip}',
                replace_existing=True
            )
            logger.info(f"Scheduled DNS probes for {target_ip} every {probe_interval}s.")

    # 9. Start the Scheduler and Wait (bounded by configured duration)
    scheduler.start()
    logger.info("Scheduler started. Probing is now active.")

    run_duration = config.getint('Scheduler', 'run_duration_seconds', fallback=300)
    logger.info(f"Probing will run for {run_duration} seconds as configured.")
    print(f"Probing started. Will run for {run_duration} seconds...")

    # Handle graceful shutdown on SIGTERM as well
    def _handle_term(signum, frame):
        raise KeyboardInterrupt()

    try:
        signal.signal(signal.SIGTERM, _handle_term)
    except Exception:
        # Some environments may not support signal operations (e.g., certain Windows contexts)
        pass

    shutdown_reason = "duration-complete"
    try:
        # Keep the main thread alive for the configured duration
        end_time = time.time() + run_duration
        while time.time() < end_time:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        shutdown_reason = "signal"
    finally:
        logger.info(f"Shutting down due to: {shutdown_reason}. Stopping scheduler and I/O process...")
        try:
            scheduler.shutdown()
        except Exception as e:
            logger.warning(f"Scheduler shutdown encountered an issue: {e}")
        # Send sentinel value to stop the I/O process
        try:
            output_queue.put(None)
        except Exception:
            pass
        io_process.join(timeout=5)  # Wait for the I/O process to finish
        if io_process.is_alive():
            logger.warning("I/O process did not terminate gracefully. Forcing termination.")
            io_process.terminate()
        logger.info("Probe phase shutdown complete. Proceeding to analysis...")

    # 10. Run Analysis automatically
    try:
        from src.analysis.rtt_analyzer import RTTAnalyzer
        # Reuse the same log directory; analyzer will log into task dir
        analyzer = RTTAnalyzer(task_dir)
        analyzer.run()
        logger.info("Automated analysis finished. Outputs saved under 'plots/'.")
    except Exception as e:
        logger.error(f"Automated analysis failed: {e}", exc_info=True)


if __name__ == '__main__':
    main()
