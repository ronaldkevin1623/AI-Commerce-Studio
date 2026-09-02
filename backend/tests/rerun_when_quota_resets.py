"""
WAIT FOR THE FIRESTORE QUOTA, THEN RUN EVERYTHING FOR REAL.

    python tests/rerun_when_quota_resets.py            # poll, then run
    python tests/rerun_when_quota_resets.py --now      # skip the wait
    python tests/rerun_when_quota_resets.py --revert-only

WHY THIS EXISTS

The project's Firestore is on the free tier, which has a daily read quota.
A few full runs exhaust it, and once it is gone ten suites cannot run at
all — they fail with `429 ResourceExhausted`, which is not a test failure
and must not be recorded as one. The quota resets at midnight US/Pacific.

WHAT IT DOES ABOUT THE EMULATOR

While the quota was out, the stack was pointed at a local Firestore
emulator by adding FIRESTORE_EMULATOR_HOST to backend/.env. That is fine
for verifying code paths and useless for verifying data facts — an
integrity suite that reads an empty emulator reports "0 orders, 0
fabricated", which is a pass over nothing.

So this script REVERTS that line — but only once the real Firestore
answers, not on startup. Reverting first would leave the running app on a
503 for however many hours the wait is. A real-quota run has to read the
real records or it is not the sign-off run it claims to be.

IT WRITES A HEARTBEAT to backend/quota_rerun.log on every poll, so that
whether this ever ran is a question you answer by opening one file rather
than by trusting that a terminal stayed open.
"""
import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
sys.stdout.reconfigure(encoding="utf-8")

ENV = BACKEND / ".env"
BACKUP = BACKEND / ".env.realdata.bak"
POLL_SECONDS = 600

# One file that always says what happened, appended to and flushed on every
# poll. The point is that a person can open it cold the next morning and
# know whether this ever ran, without having to reconstruct it from a
# terminal that was closed hours ago. A process that dies silently is worse
# than one that never started, because it looks like it is still going.
HEARTBEAT = BACKEND / "quota_rerun.log"

# Only one poller at a time.
#
# Two things start this — the detached process and the scheduled task —
# and without a lock both sit waiting, then both run the whole suite the
# moment the quota returns. That spends the newly reset daily allowance
# twice over to answer one question, and can exhaust it again on the spot.
# --skip-if-done does not help: by then both are already past that check.
LOCK = BACKEND / "quota_rerun.pid"


def _started_at(pid: int) -> str:
    """
    When that pid started, or "" if it is not running.

    The start time is what makes the lock safe against PID REUSE. Checking
    only that some process with that number exists is not enough over a
    wait this long: Windows recycles pids, and if an unrelated process
    inherited the dead poller's number the lock would never be released and
    the run would never happen — the exact silent-failure this is meant to
    prevent.
    """
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'"
             f" -ErrorAction SilentlyContinue).CreationDate"],
            capture_output=True, text=True, timeout=20).stdout.strip()
        return out
    except Exception:
        # Cannot tell. Report "not running" so a broken lookup can never
        # deadlock the run; the worst case is a duplicate, which is far
        # less bad than never running at all.
        return ""


def _me() -> str:
    return f"{os.getpid()}|{_started_at(os.getpid())}"


def claim_lock() -> bool:
    """True if this process may proceed."""
    if LOCK.exists():
        raw = ""
        try:
            raw = LOCK.read_text(encoding="utf-8").strip()
        except Exception:
            raw = ""
        pid_text, _, stamp = raw.partition("|")
        try:
            holder = int(pid_text or 0)
        except ValueError:
            holder = 0
        if holder and holder != os.getpid():
            live = _started_at(holder)
            # Held only if that pid is running AND is the same process that
            # took the lock. Same number, different start time, means the
            # original died and the number was reused — a stale lock.
            if live and (not stamp or live == stamp):
                return False
    LOCK.write_text(_me(), encoding="utf-8")
    return True


def release_lock() -> None:
    try:
        # Compare the pid part only — the file holds "pid|starttime" now, so
        # matching the whole string would never succeed and the lock would
        # be left behind on every clean finish.
        if LOCK.exists():
            held = LOCK.read_text(encoding="utf-8").strip().partition("|")[0]
            if held == str(os.getpid()):
                LOCK.unlink()
    except Exception:
        pass


def beat(message: str) -> None:
    line = f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC] {message}"
    print(line, flush=True)
    try:
        with HEARTBEAT.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        # Never let logging be the thing that kills the run.
        pass


def notify(title: str, body: str, report: str = "") -> None:
    """
    Tell the person at the keyboard, since nothing else will.

    Claude cannot initiate a message — it only runs when spoken to — so if
    this finishes at 03:00 unattended, the only way anyone finds out is if
    the machine itself says so. Two channels, because either can fail
    silently: a Windows toast, and a file on the Desktop that survives a
    dismissed or missed notification.

    Neither is allowed to break the run: a notification failing is not a
    reason to lose a completed test result.
    """
    try:
        desktop = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Environment]::GetFolderPath('Desktop')"],
            capture_output=True, text=True, timeout=20).stdout.strip()
        if desktop:
            out = Path(desktop) / "CARTPILOT test result.txt"
            out.write_text(
                "\n".join([
                    title,
                    "=" * len(title),
                    "",
                    body,
                    "",
                    report,
                    "",
                    f"Full log: {HEARTBEAT}",
                    "",
                    "Re-check any time:",
                    f"  cd {BACKEND}",
                    "  venv/Scripts/python.exe tests/check_rerun.py",
                    "",
                ]),
                encoding="utf-8")
            beat(f"wrote {out}")
    except Exception as exc:
        beat(f"could not write the desktop report: {exc}")

    try:
        safe_title = title.replace("'", "").replace('"', "")
        safe_body = body.replace("'", "").replace('"', "")
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"""
$ErrorActionPreference='Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
        [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$n = $t.GetElementsByTagName('text')
$n.Item(0).AppendChild($t.CreateTextNode('{safe_title}')) | Out-Null
$n.Item(1).AppendChild($t.CreateTextNode('{safe_body}')) | Out-Null
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier(
    '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\WindowsPowerShell\v1.0\powershell.exe'
).Show([Windows.UI.Notifications.ToastNotification]::new($t))
"""], capture_output=True, text=True, timeout=30)
        beat("desktop notification sent")
    except Exception as exc:
        beat(f"could not send a notification: {exc}")


def revert_to_real_data() -> str:
    """Take FIRESTORE_EMULATOR_HOST back out of .env."""
    if not ENV.exists():
        return "no .env found"
    text = ENV.read_text(encoding="utf-8")
    # Also catches a block of emulator comments left with no setting — an
    # earlier revert removed the line but not the paragraph, so .env still
    # claimed an emulator was in use.
    if ("FIRESTORE_EMULATOR_HOST" not in text
            and "Firestore emulator" not in text):
        return "already on real data"

    # Drop the setting AND the comment block that introduced it, rather than
    # restoring the backup wholesale — anything else edited in .env since
    # then is somebody's real change and must survive.
    #
    # Done by walking comment blocks rather than by matching one phrasing.
    # A regex anchored on the exact wording missed blocks written slightly
    # differently and left them behind, so .env ended up still announcing an
    # emulator that had already been switched off — worse than no comment,
    # because it is confidently wrong.
    def _emulator_block(lines):
        return any("FIRESTORE_EMULATOR" in ln or "Firestore emulator" in ln
                   for ln in lines)

    out, block = [], []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            block.append(line)
            continue
        if stripped.startswith("FIRESTORE_EMULATOR_HOST="):
            block = []                      # setting plus its own comments
            continue
        if _emulator_block(block) and not stripped:
            block = []                      # orphan left by an earlier revert
            continue
        out.extend(block)
        block = []
        out.append(line)
    if block and not _emulator_block(block):
        out.extend(block)

    # Collapse the run of blank lines a removal leaves behind.
    cleaned, blanks = [], 0
    for line in out:
        blanks = blanks + 1 if not line.strip() else 0
        if blanks <= 1:
            cleaned.append(line)
    ENV.write_text("\n".join(cleaned).rstrip() + "\n", encoding="utf-8")
    os.environ.pop("FIRESTORE_EMULATOR_HOST", None)
    return "reverted — .env now points at the real project"


def quota_available() -> tuple[bool, str]:
    """One cheap read against the real project."""
    env = dict(os.environ)
    env.pop("FIRESTORE_EMULATOR_HOST", None)
    # The probe deliberately does NOT import app code. Two earlier attempts
    # failed for the same underlying reason: app.config calls load_dotenv(),
    # which puts FIRESTORE_EMULATOR_HOST straight back from .env, and the
    # probe then reported the local emulator as proof that the real quota
    # had returned — a false green on exactly the question being asked.
    # Setting the variable empty instead of removing it does not help
    # either: the client treats presence, not truthiness, as "use an
    # emulator", and tries to open a channel to ''.
    #
    # So this builds a client straight from the service account key and
    # never reads .env at all. It is the only way to be sure the answer is
    # about the real project.
    # Reads enough to mean something. A single one-document read is not a
    # test of quota: one slipped through while the suite was still failing
    # on everything else, the poller declared recovery, reverted .env and
    # launched a full run that immediately died. The probe now reads from
    # the collection the suites actually hammer, and reads a realistic
    # number of documents.
    probe = (
        "import os; os.environ.pop('FIRESTORE_EMULATOR_HOST', None);"
        "from google.cloud import firestore;"
        "from google.oauth2 import service_account;"
        "c = service_account.Credentials.from_service_account_file"
        "('serviceAccountKey.json');"
        "db = firestore.Client(credentials=c, project=c.project_id);"
        "n = len(list(db.collection('orders').limit(30).get()));"
        "m = len(list(db.collection('decisions').limit(30).get()));"
        "print('OK', n, m)"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", env=env)
    if "OK" in (result.stdout or ""):
        return True, "reachable"
    blob = (result.stdout or "") + (result.stderr or "")
    if "ResourceExhausted" in blob or "429" in blob:
        return False, "still over quota"
    return False, (blob.strip().splitlines() or ["unknown error"])[-1][:80]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", action="store_true", help="do not wait")
    parser.add_argument("--revert-only", action="store_true")
    parser.add_argument("--skip-if-done", action="store_true",
                        help="exit quietly if the sign-off run already happened")
    args = parser.parse_args()


    # Two things can start this: the detached poller and the scheduled task.
    # Whichever gets there second must not run the whole suite again — that
    # would spend another slice of the same daily quota to re-answer a
    # question already answered, and could exhaust it a second time.
    if args.skip_if_done and HEARTBEAT.exists():
        # Only a CLEAN finish counts. "DONE WITH FAILURES" also contains
        # "DONE", so the first version of this would have seen the failed
        # 12:18 run, decided the job was complete, and made tomorrow's
        # scheduled retry skip silently — turning a recoverable quota
        # failure into a result that never arrives.
        done = [ln for ln in HEARTBEAT.read_text(encoding="utf-8").splitlines()
                if "DONE" in ln and "WITH FAILURES" not in ln]
        if done:
            beat(f"skipping — already finished: {done[-1].split('] ', 1)[-1]}")
            return 0

    if args.revert_only:
        beat(revert_to_real_data())
        return 0

    if not claim_lock():
        holder = LOCK.read_text(encoding="utf-8").strip().partition("|")[0]
        beat(f"another poller (pid {holder}) already holds the lock — exiting")
        return 0

    beat(f"started, pid {os.getpid()} — polling every "
         f"{POLL_SECONDS // 60} min until the real Firestore answers")

    # Poll BEFORE reverting. Reverting first would take the running app off
    # the emulator and back onto a datastore that is still over quota, so
    # every screen would show the 503 for however many hours the wait is.
    # The emulator stays in place until the moment the real thing can answer.
    # Two clean probes a minute apart before believing it. Quota recovery
    # is not instantaneous and a single success can be a transient window;
    # acting on one cost a wasted full run.
    confirmations = 0
    while True:
        ok, why = quota_available()
        if ok and confirmations < 1:
            confirmations += 1
            beat(f"Firestore {why} — confirming in 60s before committing")
            time.sleep(60)
            continue
        if not ok:
            confirmations = 0
        if ok:
            beat(f"Firestore {why}, confirmed twice")
            beat(revert_to_real_data())
            beat("running the full suite against real data")
            break
        if args.now:
            beat(f"Firestore {why} — running anyway (--now)")
            beat(revert_to_real_data())
            break
        beat(f"Firestore {why}; next check in {POLL_SECONDS // 60} min")
        time.sleep(POLL_SECONDS)

    result = subprocess.run(
        [sys.executable, str(BACKEND / "tests" / "run_all.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = (result.stdout or "") + (result.stderr or "")
    print(output)

    # The whole run goes in the log, not just a verdict. Someone reading
    # this cold needs to see which suites ran and which did not, and a
    # single "passed"/"failed" word cannot carry that.
    summary = [ln.strip() for ln in output.splitlines()
               if "passed," in ln or "NO RESULT" in ln or "assertions passed" in ln
               or "COULD NOT RUN" in ln or "report, exit" in ln]

    # The money-reconciliation assertions, quoted verbatim rather than left
    # inside a suite total. These are the ones somebody is actually waiting
    # on — whether every rupee the dashboard claims is confirmed by
    # Razorpay, and whether anything Razorpay moved went unrecorded here
    # (the question raised by the Rs319.55 refunded order). "audit_3_live:
    # 20 passed" does not answer either of them.
    WATCHED = (
        "confirmed by Razorpay",
        "payment moved money without this app recording",
        "Every stored payment id names a payment Razorpay actually took",
        "Orders we call refunded are refunded at Razorpay too",
    )
    reconciliation = [ln.strip() for ln in output.splitlines()
                      if any(w in ln for w in WATCHED)]
    if reconciliation:
        summary.append("")
        summary.append("Money reconciliation, in full:")
        summary.extend("  " + ln for ln in reconciliation)
    else:
        summary.append("")
        summary.append("Money reconciliation: NOT REACHED — audit_3_live did "
                       "not get far enough to run it.")
    beat(f"full suite finished, exit {result.returncode}")
    for line in summary:
        beat(f"  {line}")
    verdict = ("DONE — this is the real-quota sign-off run"
               if not result.returncode else
               "DONE WITH FAILURES — see the lines above and rerun run_all.py")
    beat(verdict)
    notify(
        "CartPilot: full test suite finished"
        + ("" if not result.returncode else " WITH FAILURES"),
        ("All suites passed against real Firestore."
         if not result.returncode else
         "Some suites failed or could not run. Open the report."),
        chr(10).join(summary),
    )
    release_lock()
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
