# Output Data Directory

This directory is used to store the results of all measurement tasks.

Each time the main program is run, a new subdirectory will be created here. The name of the subdirectory is now just a timestamp (YYYYMMDDTHHMMSS) to keep paths short and readable.

Each task subdirectory will contain:
- `raw_data.jsonl`: The raw measurement data in JSON Lines format (pair mode).
- `task.log`: The detailed log file for the task execution.
- `config.ini`: A snapshot of the configuration used for this specific task, ensuring reproducibility.
- (Optional) `plots/`: A directory containing generated plots and figures from the analysis phase.

## Mass Scan Mode

For mass scan, results are placed under `data/output/mass/<timestamp>/`.

Ground-truth separation:
- `ground/` — CSV files for ground-network targets
- `satellite/` — CSV files for satellite-network targets

Each CSV is named by IP (e.g., `1.2.3.4.csv`) with schema:
`timestamp,target_ip,probe_type,rtt_ms,status`

The analyzer writes aggregate outputs in the same `<timestamp>/` directory, e.g. `summary_by_ip.csv`, `summary_by_label.csv`, plots like `kde_by_label.png`.
