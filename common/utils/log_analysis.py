# common/utils/log_analysis.py
import json
from typing import Dict, List, Any
from collections import defaultdict
from datetime import datetime, timedelta


def analyze_log_file(file_path: str, time_window: timedelta = timedelta(hours=1)) -> Dict[str, Any]:
    """
    Analyze a JSON log file and provide statistics

    Args:
        file_path: Path to the log file
        time_window: Time window for analysis

    Returns:
        Dictionary with analysis results
    """
    stats = defaultdict(int)
    errors_by_operation = defaultdict(list)
    operations_timing = defaultdict(list)

    cutoff_time = datetime.utcnow() - time_window

    with open(file_path, 'r') as f:
        for line in f:
            try:
                log_entry = json.loads(line)
                timestamp = datetime.fromisoformat(log_entry['timestamp'])

                if timestamp < cutoff_time:
                    continue

                # Count log levels
                stats[f"level_{log_entry['level']}"] += 1

                # Track errors by operation
                if log_entry['level'] == 'ERROR' and 'operation' in log_entry:
                    errors_by_operation[log_entry['operation']].append(log_entry['message'])

                # Track operation timing
                if 'duration_seconds' in log_entry and 'operation' in log_entry:
                    operations_timing[log_entry['operation']].append(log_entry['duration_seconds'])

            except (json.JSONDecodeError, KeyError):
                continue

    # Calculate averages for operations
    operation_avg_timing = {}
    for operation, timings in operations_timing.items():
        if timings:
            operation_avg_timing[operation] = sum(timings) / len(timings)

    return {
        'stats': dict(stats),
        'errors_by_operation': dict(errors_by_operation),
        'operation_avg_timing': operation_avg_timing
    }