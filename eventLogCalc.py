import subprocess
from datetime import datetime


LOG_NAMES = [
    "System",
    "Application",
    "Security"
]

# Windows Event Log levels
# 1 = Critical
# 2 = Error
# 3 = Warning
EVENT_LEVELS = {
    1: "CRITICAL",
    2: "ERROR",
    3: "WARNING"
}


def get_event_logs():

    # PowerShell command
    powershell_command = r"""
$startTime = (Get-Date).AddHours(-5)

$logs = @(
    "System",
    "Application",
    "Security"
)

Get-WinEvent -FilterHashtable @{
    LogName   = $logs
    Level     = 1,2,3
    StartTime = $startTime
} |
Select-Object TimeCreated,
              LogName,
              Id,
              LevelDisplayName,
              ProviderName,
              Message |
Sort-Object TimeCreated -Descending |
Format-List
"""

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            powershell_command
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    if result.returncode != 0:
        print("Failed to retrieve Windows Event Logs.", flush=True)
        print(result.stderr, flush=True)
        return

    print("=" * 90, flush=True)
    print("          WINDOWS EVENT LOG MONITOR - LAST 5 HOURS", flush=True)
    print("=" * 90, flush=True)

    if not result.stdout.strip():
        print("\nNo Critical, Error, or Warning events found.", flush=True)
        return

    print(result.stdout, flush=True)


if __name__ == "__main__":
    get_event_logs()