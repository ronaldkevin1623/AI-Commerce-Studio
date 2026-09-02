"""
DID THE OVERNIGHT REAL-QUOTA RUN ACTUALLY HAPPEN?

    python tests/check_rerun.py

One command, one answer, read from the heartbeat rather than from whether a
terminal happened to stay open. Written in Python rather than PowerShell on
purpose: a .ps1 is refused outright under the default execution policy, and
a check you cannot run is not a check.

Three outcomes, and the third is the reason this exists:

    FINISHED      the suite ran; the summary lines are in the log
    STILL POLLING the process is alive and waiting for the quota
    STOPPED       it died without finishing, and nothing else would have
                  told you
"""
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
LOG = BACKEND / "quota_rerun.log"
sys.stdout.reconfigure(encoding="utf-8")


def poller_pids() -> list[int]:
    """Any live process running the rerun script."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -like '*rerun_when_quota*' } | "
             "ForEach-Object { $_.ProcessId }"],
            capture_output=True, text=True, timeout=30).stdout
        return [int(n) for n in re.findall(r"\d+", out)]
    except Exception:
        return []


def main() -> int:
    if not LOG.exists():
        print("\nNO HEARTBEAT FILE — the poller never started.\n")
        print("  cd backend")
        print("  venv/Scripts/python.exe tests/rerun_when_quota_resets.py\n")
        return 1

    lines = [ln.rstrip() for ln in
             LOG.read_text(encoding="utf-8").splitlines() if ln.strip()]
    print()
    for line in lines[-25:]:
        print("  " + line)
    print()

    last = lines[-1] if lines else ""
    pids = poller_pids()

    # Age comes from the timestamp INSIDE the last line, not from the file's
    # mtime. Anything that rewrites the file — a copy, a backup, an editor
    # saving it — resets mtime and would report a stale log as fresh, which
    # is precisely the wrong way round for a staleness check.
    stamp = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC\]", last)
    if stamp:
        written = datetime.strptime(stamp.group(1), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc)
        age_min = (datetime.now(timezone.utc) - written).total_seconds() / 60
    else:
        age_min = (datetime.now(timezone.utc).timestamp() - LOG.stat().st_mtime) / 60

    if "DONE" in last:
        failed = "WITH FAILURES" in last
        print(f"STATUS: the run FINISHED{' — WITH FAILURES' if failed else ''}.")
        print(f"        {last}")
        return 1 if failed else 0

    if pids:
        print(f"STATUS: still polling (pid {pids[0]}), "
              f"last heartbeat {age_min:.0f} min ago.")
        if age_min > 25:
            # Alive but not writing is its own kind of stuck, and it looks
            # identical to healthy if you only check that a pid exists.
            print("        WARNING: it is alive but has not written for a "
                  "while — check it is not wedged.")
        return 0

    print("STATUS: the poller is NOT running and did NOT finish.")
    print(f"        Last heartbeat was {age_min:.0f} min ago: {last}")
    print("        Run it now:")
    print("          cd backend")
    print("          venv/Scripts/python.exe tests/rerun_when_quota_resets.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
