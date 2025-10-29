# Output Data Directory

This directory is used to store the results of all measurement tasks.

Each time the main program is run, a new subdirectory will be created here. The name of the subdirectory will be a unique **Task ID**, generated based on the task name, target IPs, and start time.

Each task subdirectory will contain:
- `raw_data.jsonl`: The raw measurement data in JSON Lines format.
- `task.log`: The detailed log file for the task execution.
- `config.ini`: A snapshot of the configuration used for this specific task, ensuring reproducibility.
- (Optional) `plots/`: A directory containing generated plots and figures from the analysis phase.
