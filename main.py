import os
import sys
import time
import shutil
import json
import argparse
from datetime import datetime, timedelta
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
from src.collection.rdns_collector import RdnsCollector
from src.collection.traceroute_collector import TracerouteCollector

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

# --- Global Variables ---
config = None
logger = None
output_queue = None  # Will be created in workflows to avoid Windows spawn issues

def get_task_id(task_name, targets):
    """Generates a unique ID for the current task.

    NOTE: To keep directories tidy when many targets are used, we now only
    include the timestamp in the task id (no IPs/targets).
    """
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    # Only keep time component to avoid very long directory names
    return f"{timestamp}"

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

    # Prepare separate folder for RDNS/Traceroute metadata
    meta_dir = os.path.join(os.path.dirname(output_file), 'meta')
    os.makedirs(meta_dir, exist_ok=True)

    rdns_file_path = os.path.join(meta_dir, 'rdns.jsonl')
    traceroute_file_path = os.path.join(meta_dir, 'traceroute.jsonl')

    with open(output_file, 'a', encoding='utf-8') as f, \
         open(rdns_file_path, 'a', encoding='utf-8') as frdns, \
         open(traceroute_file_path, 'a', encoding='utf-8') as ftr:
        while True:
            try:
                result = queue.get()
                if result is None:  # Sentinel value to stop the process
                    writer_logger.info("I/O writer process received stop signal. Shutting down.")
                    break
                # Serialize dict to a JSON string before writing
                try:
                    probe_type = result.get('probe_type')
                    if probe_type in ('rdns', 'traceroute'):
                        if probe_type == 'rdns':
                            frdns.write(json.dumps(result) + '\n')
                            frdns.flush()
                        else:
                            ftr.write(json.dumps(result) + '\n')
                            ftr.flush()
                    else:
                        f.write(json.dumps(result) + '\n')
                        f.flush()
                except Exception as e:
                    writer_logger.error(f"Failed to write result: {e}", exc_info=True)
            except (KeyboardInterrupt, SystemExit):
                break
            except Exception as e:
                writer_logger.error(f"I/O writer process encountered an error: {e}", exc_info=True)
    writer_logger.info("I/O writer process finished.")


def io_writer_process_mass(queue, output_dir, log_dir, log_level, log_format):
    """
    I/O writer for mass-scan mode: writes one CSV per IP under output_dir.

    CSV schema: timestamp,target_ip,probe_type,rtt_ms,status
    """
    writer_logger = setup_logger(log_dir, log_level, log_format)
    writer_logger.info(f"Mass I/O writer started. Output dir: {output_dir}")

    # Rotate writer's own log to separate file
    handler_index = -1
    for i, handler in enumerate(writer_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            handler_index = i
            break
    if handler_index != -1:
        writer_logger.handlers[handler_index].close()
        writer_logger.removeHandler(writer_logger.handlers[handler_index])
        writer_log_file = os.path.join(log_dir, 'io_writer_mass.log')
        file_handler = logging.FileHandler(writer_log_file)
        file_handler.setFormatter(logging.Formatter(log_format))
        writer_logger.addHandler(file_handler)

    os.makedirs(output_dir, exist_ok=True)

    # Lazy-open file handles per IP with header
    handles = {}

    def _get_handle(ip):
        path = os.path.join(output_dir, f"{ip}.csv")
        if ip not in handles:
            f = open(path, 'a', encoding='utf-8')
            if os.stat(path).st_size == 0:
                f.write('timestamp,target_ip,probe_type,rtt_ms,status\n')
                f.flush()
            handles[ip] = f
        return handles[ip]

    try:
        while True:
            try:
                item = queue.get()
                if item is None:
                    writer_logger.info("Mass I/O writer received stop signal.")
                    break
                ip = item.get('target_ip', 'unknown')
                f = _get_handle(ip)
                # Prepare CSV row (metadata omitted)
                ts = item.get('timestamp', '')
                probe_type = item.get('probe_type', '')
                rtt = item.get('rtt_ms')
                status = item.get('status', '')
                rtt_str = '' if rtt is None else f"{float(rtt):.6f}"
                line = f"{ts},{ip},{probe_type},{rtt_str},{status}\n"
                f.write(line)
                f.flush()
            except (KeyboardInterrupt, SystemExit):
                break
            except Exception as e:
                writer_logger.error(f"Mass I/O writer error: {e}", exc_info=True)
    finally:
        for f in handles.values():
            try:
                f.close()
            except Exception:
                pass
        writer_logger.info("Mass I/O writer finished.")


def _parse_mass_targets(file_path: str):
    """Parse mass target file with [ground] and [satellite] sections.

    File format example:

    [ground]
    1.1.1.1
    8.8.8.8

    [satellite]
    203.0.113.1

    Lines starting with '#' are ignored. Section headers are case-insensitive.
    """
    ground, satellite = [], []
    current = None
    if not os.path.exists(file_path):
        print(f"ERROR: Mass target file not found: {file_path}", file=sys.stderr)
        return ground, satellite
    with open(file_path, 'r', encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('[') and line.endswith(']'):
                sec = line[1:-1].strip().lower()
                if sec in ('ground', 'satellite'):
                    current = sec
                else:
                    current = None
                continue
            if current == 'ground':
                ground.append(line)
            elif current == 'satellite':
                satellite.append(line)
            else:
                # default to ground if no section specified yet
                ground.append(line)
    return ground, satellite


def run_pair_workflow():
    """Original scan+analyze workflow for two-point comparison."""
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
    # Directory only contains timestamp now
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

        # RDNS & Traceroute are heavier; schedule to run once shortly after start
        if config.getboolean('RDNS', 'enabled', fallback=False):
            rdns_collector = RdnsCollector(target_ip, config, output_queue)
            scheduler.add_job(
                rdns_collector.run_probe,
                'date',
                run_date=datetime.now() + timedelta(seconds=2),
                id=f'rdns_{target_ip}',
                replace_existing=True
            )
            logger.info(f"Scheduled RDNS probe once for {target_ip}.")

        if config.getboolean('Traceroute', 'enabled', fallback=False):
            tr_collector = TracerouteCollector(target_ip, config, output_queue)
            scheduler.add_job(
                tr_collector.run_probe,
                'date',
                run_date=datetime.now() + timedelta(seconds=3),
                id=f'traceroute_{target_ip}',
                replace_existing=True
            )
            logger.info(f"Scheduled Traceroute probe once for {target_ip}.")

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
        from src.analysis.pair_rtt_analyzer import PairRTTAnalyzer
        # Reuse the same log directory; analyzer will log into task dir
        analyzer = PairRTTAnalyzer(task_dir)
        analyzer.run()
        logger.info("Automated analysis finished. Outputs saved under 'plots/'.")
    except Exception as e:
        logger.error(f"Automated analysis failed: {e}", exc_info=True)


def run_mass_scan():
    """Mass scan mode: ping many IPs once (or a few times) and store per-IP CSVs."""
    global config, logger, output_queue

    # 1. Load Configuration
    try:
        config_path = os.path.join(PROJECT_ROOT, 'configs', 'default_config.ini')
        config = load_config(config_path)
    except FileNotFoundError as e:
        print(f"FATAL: Configuration file not found. {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Load mass targets
    mass_target_file_rel = config.get('General', 'mass_target_file', fallback='data/input/mass_targets.txt')
    target_file_path = os.path.join(PROJECT_ROOT, mass_target_file_rel)
    ground_targets, sat_targets = _parse_mass_targets(target_file_path)
    if not ground_targets and not sat_targets:
        print("FATAL: No mass targets to probe (ground/satellite empty). Exiting.", file=sys.stderr)
        sys.exit(1)

    # 3. Setup directories and logging
    timestamp = datetime.now().strftime('%Y%m%dT%H%M%S')
    # Place outputs under data/output/mass/<timestamp>/
    result_root = os.path.join(PROJECT_ROOT, 'data', 'output', 'mass', timestamp)
    os.makedirs(result_root, exist_ok=True)
    ground_dir = os.path.join(result_root, 'ground')
    satellite_dir = os.path.join(result_root, 'satellite')
    os.makedirs(ground_dir, exist_ok=True)
    os.makedirs(satellite_dir, exist_ok=True)

    log_level = config.get('Logging', 'level', fallback='INFO')
    log_format = config.get('Logging', 'format', raw=True)
    logger = setup_logger(result_root, log_level, log_format)
    logger.info(f"Mass scan starting. Ground: {len(ground_targets)}, Satellite: {len(sat_targets)}")

    # Snapshot config and target list
    try:
        shutil.copy(os.path.join(PROJECT_ROOT, 'configs', 'default_config.ini'), os.path.join(result_root, 'config.ini'))
        shutil.copy(target_file_path, os.path.join(result_root, 'targets.txt'))
    except Exception as e:
        logger.warning(f"Failed to snapshot inputs: {e}")

    # 4. Start mass writer processes (ground & satellite)
    ground_queue = Queue()
    sat_queue = Queue()
    io_ground = Process(target=io_writer_process_mass, args=(ground_queue, ground_dir, result_root, log_level, log_format))
    io_sat = Process(target=io_writer_process_mass, args=(sat_queue, satellite_dir, result_root, log_level, log_format))
    io_ground.start()
    io_sat.start()

    # 5. Schedule probes with interval similar to pair mode
    executors = {
        'default': ThreadPoolExecutor(config.getint('General', 'worker_threads', fallback=10))
    }
    job_defaults = {
        'coalesce': True,
        'max_instances': 1,
        'misfire_grace_time': 10
    }
    scheduler = BackgroundScheduler(executors=executors, job_defaults=job_defaults)

    probe_interval = config.getint('Scheduler', 'probe_interval_seconds', fallback=1)

    # Schedule ICMP and optionally DNS for each set
    for ip in ground_targets:
        if config.getboolean('ICMP', 'enabled', fallback=True):
            scheduler.add_job(IcmpCollector(ip, config, ground_queue).run_probe, 'interval', seconds=probe_interval, id=f'mass_icmp_ground_{ip}', replace_existing=True)
        if config.getboolean('DNS', 'enabled', fallback=False):
            scheduler.add_job(DnsCollector(ip, config, ground_queue).run_probe, 'interval', seconds=probe_interval, id=f'mass_dns_ground_{ip}', replace_existing=True)

    for ip in sat_targets:
        if config.getboolean('ICMP', 'enabled', fallback=True):
            scheduler.add_job(IcmpCollector(ip, config, sat_queue).run_probe, 'interval', seconds=probe_interval, id=f'mass_icmp_sat_{ip}', replace_existing=True)
        if config.getboolean('DNS', 'enabled', fallback=False):
            scheduler.add_job(DnsCollector(ip, config, sat_queue).run_probe, 'interval', seconds=probe_interval, id=f'mass_dns_sat_{ip}', replace_existing=True)

    scheduler.start()
    logger.info(f"Mass scheduler started. Interval={probe_interval}s")

    run_duration = config.getint('Scheduler', 'run_duration_seconds', fallback=300)
    logger.info(f"Mass probing will run for {run_duration} seconds as configured.")
    print(f"Mass probing started. Will run for {run_duration} seconds...")

    def _handle_term(signum, frame):
        raise KeyboardInterrupt()

    try:
        signal.signal(signal.SIGTERM, _handle_term)
    except Exception:
        pass

    try:
        end_time = time.time() + run_duration
        while time.time() < end_time:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Mass scan interrupted by user.")
    finally:
        try:
            scheduler.shutdown()
        except Exception:
            pass
        # stop writers
        for q in (ground_queue, sat_queue):
            try:
                q.put(None)
            except Exception:
                pass
        for p in (io_ground, io_sat):
            p.join(timeout=5)
        for p in (io_ground, io_sat):
            if p.is_alive():
                p.terminate()
        logger.info("Mass scan finished.")


def prompt_mode_if_needed(args_mode: str | None) -> str:
    """Return chosen mode either from args or interactive prompt."""
    choices = ['pair', 'mass-scan', 'analyze-pair', 'analyze-mass', 'analyze-pair-from-mass']
    if args_mode in choices:
        return args_mode
    print("请选择运行模式: \n  1) pair (两点扫描+自动分析)\n  2) mass-scan (大规模扫描，定时采样)\n  3) analyze-pair (分析两点结果)\n  4) analyze-mass (分析大规模结果)\n  5) analyze-pair-from-mass (从大规模结果中选两IP做两点分析)")
    sel = input("输入序号或名称 [1-5]: ").strip()
    mapping = {'1': 'pair', '2': 'mass-scan', '3': 'analyze-pair', '4': 'analyze-mass', '5': 'analyze-pair-from-mass'}
    return mapping.get(sel, sel if sel in choices else 'pair')


def _parse_analyses_arg(input_str: str | None, defaults: list[str]) -> list[str]:
    if not input_str:
        return defaults
    items = [x.strip() for x in input_str.split(',') if x.strip()]
    return items or defaults


def _list_mass_ips(result_dir: str, label: str) -> list[str]:
    path = os.path.join(result_dir, label)
    if not os.path.isdir(path):
        return []
    ips = []
    for name in os.listdir(path):
        if name.endswith('.csv'):
            ips.append(name[:-4])
    return sorted(ips)


def _choose_ip_interactively(ips: list[str], label: str) -> str:
    if not ips:
        return ''
    print(f"可选 {label} IP 数量: {len(ips)}")
    preview = ips[:10]
    for i, ip in enumerate(preview, 1):
        print(f"  {i}. {ip}")
    if len(ips) > 10:
        print("  ... (其余省略)")
    sel = input(f"请选择 {label} IP（输入序号或直接输入IP）: ").strip()
    if sel.isdigit():
        idx = int(sel)
        if 1 <= idx <= len(preview):
            return preview[idx - 1]
    return sel


def _build_pair_from_mass_dataset(result_dir: str, ground_ip: str, sat_ip: str, probe_type: str) -> str:
    """Create a temporary pair-style dataset (raw_data.jsonl) from mass CSVs and return its directory."""
    import csv, json as _json
    timestamp = datetime.now().strftime('%Y%m%dT%H%M%S')
    out_dir = os.path.join(result_dir, f'pair_from_mass_{probe_type}_{ground_ip}_vs_{sat_ip}_{timestamp}')
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, 'raw_data.jsonl')

    def emit_from_csv(csv_path: str):
        if not os.path.isfile(csv_path):
            return
        with open(csv_path, 'r', encoding='utf-8') as f, open(out_file, 'a', encoding='utf-8') as w:
            reader = csv.DictReader(f)
            for row in reader:
                if probe_type and row.get('probe_type') != probe_type:
                    continue
                rec = {
                    'timestamp': row.get('timestamp'),
                    'target_ip': row.get('target_ip'),
                    'probe_type': row.get('probe_type'),
                    'rtt_ms': float(row['rtt_ms']) if row.get('rtt_ms') not in (None, '',) else None,
                    'status': row.get('status'),
                    'metadata': {}
                }
                w.write(_json.dumps(rec) + '\n')

    emit_from_csv(os.path.join(result_dir, 'ground', f'{ground_ip}.csv'))
    emit_from_csv(os.path.join(result_dir, 'satellite', f'{sat_ip}.csv'))
    return out_dir


def main():
    parser = argparse.ArgumentParser(description='Starlink RTT Scanner/Analyzer')
    parser.add_argument('--mode', choices=['pair', 'mass-scan', 'analyze-pair', 'analyze-mass', 'analyze-pair-from-mass'], help='运行模式')
    parser.add_argument('--input', help='当使用 analyze-* 模式时，指定待分析的目录')
    parser.add_argument('--analyses', help='逗号分隔的分析项，例如: timeseries,kde,hist,box,ks,summary,loss,cdf,violin,topn')
    args = parser.parse_args()

    mode = prompt_mode_if_needed(args.mode)
    if mode == 'pair':
        run_pair_workflow()
    elif mode == 'mass-scan':
        run_mass_scan()
    elif mode == 'analyze-pair':
        # 分析两点结果
        task_dir = args.input or input('请输入两点结果目录路径: ').strip()
        if not os.path.isdir(task_dir):
            print(f"目录不存在: {task_dir}", file=sys.stderr)
            sys.exit(2)
        # setup simple logger
        setup_logger(task_dir, 'INFO', '%(asctime)s - %(message)s')
        from src.analysis.pair_rtt_analyzer import PairRTTAnalyzer
        selected = _parse_analyses_arg(args.analyses, ['timeseries','kde','hist','box','ks','summary','loss'])
        analyzer = PairRTTAnalyzer(task_dir, analyses=selected)
        analyzer.run()
    elif mode == 'analyze-mass':
        # 分析大规模结果
        result_dir = args.input or input('请输入大规模扫描结果目录（包含一堆按IP命名的CSV）: ').strip()
        if not os.path.isdir(result_dir):
            print(f"目录不存在: {result_dir}", file=sys.stderr)
            sys.exit(2)
        setup_logger(result_dir, 'INFO', '%(asctime)s - %(message)s')
        from src.analysis.mass_rtt_analyzer import MassRTTAnalyzer
        selected = _parse_analyses_arg(args.analyses, ['summary_by_ip','summary_by_label','mean_hist','mean_vs_loss','kde_by_label'])
        analyzer = MassRTTAnalyzer(result_dir, analyses=selected)
        analyzer.run()
    elif mode == 'analyze-pair-from-mass':
        # 从大规模结果中选两IP做两点分析
        result_dir = args.input or input('请输入大规模扫描结果目录（data/output/mass/<timestamp>）: ').strip()
        if not os.path.isdir(result_dir):
            print(f"目录不存在: {result_dir}", file=sys.stderr)
            sys.exit(2)
        setup_logger(result_dir, 'INFO', '%(asctime)s - %(message)s')
        g_ips = _list_mass_ips(result_dir, 'ground')
        s_ips = _list_mass_ips(result_dir, 'satellite')
        g_sel = _choose_ip_interactively(g_ips, 'ground')
        s_sel = _choose_ip_interactively(s_ips, 'satellite')
        # 选择探测类型（从已有数据考虑，默认 icmp）
        probe = input('请选择探测类型（icmp/dns，默认 icmp）: ').strip().lower() or 'icmp'
        tmp_pair_dir = _build_pair_from_mass_dataset(result_dir, g_sel, s_sel, probe)
        from src.analysis.pair_rtt_analyzer import PairRTTAnalyzer
        selected = _parse_analyses_arg(args.analyses, ['timeseries','kde','hist','box','ks','summary','loss'])
        analyzer = PairRTTAnalyzer(tmp_pair_dir, analyses=selected)
        analyzer.run()
    else:
        print(f"未知模式: {mode}", file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
