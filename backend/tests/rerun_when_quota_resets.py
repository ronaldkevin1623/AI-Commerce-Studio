"""
WAIT FOR THE FIRESTORE QUOTA, THEN RUN EVERYTHING FOR REAL.

    python tests/rerun_when_quota_resets.py            # poll, then run
    python tests/rerun_when_quota_resets.py --now      # skip the wait

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

AFTER THE QUOTA RETURNS it runs three things in order and writes them all
to backend/quota_rerun_report.txt: the orphaned-order backfill in PREVIEW
ONLY (never --commit — an unattended task does not get to write a financial
record on someone's behalf), then audit_3_live on its own so the money
reconciliation is legible even if the quota runs out again, then the full
suite.

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
# .env.realdata.bak is no longer this script's business: nothing here
# writes .env any more, so there is nothing to restore. The file stays
# on disk until its owner decides otherwise.
POLL_SECONDS = 600

# One file that always says what happened, appended to and flushed on every
# poll. The point is that a person can open it cold the next morning and
# know whether this ever ran, without having to reconstruct it from a
# terminal that was closed hours ago. A process that dies silently is worse
# than one that never started, because it looks like it is still going.
HEARTBEAT = BACKEND / "quota_rerun.log"
# The full transcript of the post-quota run, written for a person to
# read cold hours later. The heartbeat is a running log; this is the
# document that answers "what happened and what do I do next".
REPORT = BACKEND / "quota_rerun_report.txt"

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


# How long to hold a switch while a checkout is still open, and how often
# to look again. Deliberately finite: a wait with no ceiling turns one
# abandoned bank page into a poller that never completes.
INFLIGHT_WAIT_SECONDS = 8 * 60
INFLIGHT_POLL_SECONDS = 20


def wait_for_inflight(limit_seconds: int = INFLIGHT_WAIT_SECONDS) -> str:
    """
    Let open checkouts settle before the sign-off suite reconciles money.

    This used to guard the .env switch. There is no switch any more — the
    store is chosen per process at launch — but the wait is still worth
    doing, for a different reason.

    Between a capture and verify-payment running, Razorpay holds the money
    and this app has no payment id for it. That is indistinguishable from a
    genuine orphan, so reconciling in that window reports a real payment as
    unrecorded. audit_3_live holds those orders out by consulting the same
    register; waiting here simply means there are fewer to hold out, and a
    cleaner result to sign off on.

    It waits, it does not block forever. A poller that never returns
    because someone closed a bank tab is a worse failure than a run with
    one payment held out and named.
    """
    sys.path.insert(0, str(BACKEND))
    try:
        from app import inflight
    except Exception as exc:
        return f"in-flight register unavailable ({exc}) — switching without it"

    waited = 0
    while waited < limit_seconds:
        rows = inflight.active()
        if not rows:
            return "no checkouts in flight" if waited == 0 else (
                f"waited {waited}s for {'checkouts'} to settle — register now clear")
        beat(f"HOLDING the switch: {inflight.describe()}")
        # Never sleep past the ceiling. Sleeping a full interval on the
        # last iteration makes the guard overshoot the budget it was
        # given, which is exactly the kind of quiet inaccuracy that makes
        # a timeout untrustworthy.
        nap = min(INFLIGHT_POLL_SECONDS, limit_seconds - waited)
        time.sleep(nap)
        waited += nap

    rows = inflight.active()
    if not rows:
        return f"waited {waited}s — register now clear"
    return (f"WARNING: switching datastore with {inflight.describe()}. "
            f"Waited {waited}s and they did not settle. If any of these is a "
            f"real open checkout, its order and its capture will land in "
            f"different stores.")


# revert_to_real_data() USED TO LIVE HERE. It rewrote backend/.env to take
# FIRESTORE_EMULATOR_HOST back out.
#
# It is gone rather than kept as a no-op. The datastore is now chosen by
# CARTPILOT_STORE at launch, so rewriting .env would change nothing about
# any running process while still reporting "reverted — .env now points at
# the real project". Infrastructure that announces success and does nothing
# is worse than infrastructure that is absent: the next person to debug a
# wrong-store write would read that line and rule out the cause.
#
# What replaced it: the suite subprocess is launched with
# CARTPILOT_STORE=real in its own environment. Nothing on disk is mutated,
# so nothing needs restoring afterwards — which is also why
# .env.realdata.bak stops having a job.


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
            beat(wait_for_inflight())   # so reconciliation is not run mid-checkout
            beat("running the full suite against real data "
                 "(CARTPILOT_STORE=real, passed to the child)")
            break
        if args.now:
            beat(f"Firestore {why} — running anyway (--now)")
            beat(wait_for_inflight())
            break
        beat(f"Firestore {why}; next check in {POLL_SECONDS // 60} min")
        time.sleep(POLL_SECONDS)

    # The store is passed to the child, not written to a file. A parent
    # that mutates shared state so a child reads it differently is the
    # pattern that caused all of this.
    suite_env = dict(os.environ)
    suite_env["CARTPILOT_STORE"] = "real"
    suite_env.pop("FIRESTORE_EMULATOR_HOST", None)

    def run_step(title: str, argv: list[str]) -> tuple[int, str]:
        beat(f"running: {title}")
        proc = subprocess.run(argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              env=suite_env, cwd=str(BACKEND))
        text = (proc.stdout or "") + (proc.stderr or "")
        print(text)
        return proc.returncode, text

    # A LIVE SERVER ON ANOTHER STORE STOPS THIS BEFORE IT STARTS.
    #
    # The suite runs with CARTPILOT_STORE=real, and the datastore guard
    # refuses to start any process whose binding differs from a live one.
    # So if a dev server is up on the emulator — which is the normal state
    # while someone is demoing — every suite would die on a refusal banner
    # and the report would be a wall of them with no explanation.
    #
    # Saying it once, clearly, at the top is the difference between "the
    # run failed" and "the run could not start, here is the one thing to
    # change".
    try:
        sys.path.insert(0, str(BACKEND))
        from app.datastore_guard import _live_entries
        clashing = [e for e in _live_entries() if e.get("binding") != "real"]
    except Exception as exc:
        clashing = []
        beat(f"could not read the binding registry: {exc}")

    if clashing:
        lines = ["The suite runs against real Firestore, but these processes "
                 "are live on another datastore:"]
        for entry in clashing:
            lines.append(f"  pid {entry['pid']} on {entry['binding']}")
        lines += [
            "",
            "The datastore guard refuses to start a process whose store "
            "differs from a live one, so every suite would refuse.",
            "",
            "Nothing was run and nothing was written. Stop that process "
            "(or restart it with CARTPILOT_STORE=real) and run:",
            "  python tests/rerun_when_quota_resets.py --now",
        ]
        for line in lines:
            beat(f"  {line}")
        try:
            REPORT.write_text(
                chr(10).join(["=" * 74,
                              "  CartPilot — post-quota run DID NOT START",
                              "=" * 74, ""] + ["  " + ln for ln in lines]),
                encoding="utf-8")
        except Exception:
            pass
        notify("CartPilot: post-quota run could not start",
               "A server is live on a different datastore.",
               chr(10).join(lines))
        release_lock()
        return 1

    sections: list[tuple[str, str]] = []

    # ── 1. the orphaned-order backfill, PREVIEW ONLY ────────────────────
    #
    # Deliberately without --commit. This writes a financial record into
    # real Firestore, and that is not a decision an unattended task at
    # 00:00 gets to make on someone's behalf. It shows what it WOULD write
    # so a person can compare it against what they already approved.
    _, backfill_out = run_step(
        "orphaned-order backfill (PREVIEW ONLY — no --commit)",
        [sys.executable, str(BACKEND / "tests" / "backfill_orphaned_order.py")])
    sections.append(("BACKFILL PREVIEW — nothing was written", backfill_out))

    # ── 2. audit_3_live on its own, before the rest ─────────────────────
    #
    # Run separately so its money reconciliation is legible even if the
    # full suite later exhausts the quota again and buries it.
    _, live_out = run_step(
        "audit_3_live (money reconciliation)",
        [sys.executable, str(BACKEND / "tests" / "audit_3_live.py")])
    sections.append(("AUDIT_3_LIVE — money reconciliation", live_out))

    # ── 3. the full suite ───────────────────────────────────────────────
    result = subprocess.run(
        [sys.executable, str(BACKEND / "tests" / "run_all.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=suite_env)
    output = (result.stdout or "") + (result.stderr or "")
    print(output)
    sections.append(("FULL SUITE", output))

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

    # ── the report a person reads cold, hours later ─────────────────────
    #
    # The standing instruction this satisfies: a clean backfill preview
    # must NOT read as "verified". It is a preview. Nothing was written,
    # nothing is signed off, and .env.realdata.bak stays. That has to be
    # stated at the TOP, because a reader who sees three green sections
    # and stops reading is exactly the reader this is written for.
    header = [
        "=" * 74,
        "  CartPilot — post-quota unattended run",
        f"  {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}",
        "=" * 74,
        "",
        "  WHAT STILL NEEDS YOU",
        "",
        "  1. The orphaned-order backfill ran in PREVIEW ONLY. Nothing was",
        "     written to real Firestore. Check the preview below still says:",
        "",
        "         order   cp-5efd6d4c7e5b465e",
        "         amount  Rs829.17  (82917 paise)",
        "         payment pay_TX27e4NKLGuuvX",
        "",
        "     If it matches, approving --commit is yours to give. This task",
        "     will never run it.",
        "",
        "  2. .env.realdata.bak IS STILL PENDING. Both conditions are needed:",
        "     the CARTPILOT_STORE fix implemented (done) AND verified by a",
        "     real run that includes this backfill committed and audit_3_live",
        "     re-checked afterwards (NOT done).",
        "",
        "     A clean preview below does NOT mean verified. It means nothing",
        "     was written yet.",
        "",
        "=" * 74,
        "",
        "  SUMMARY",
        "",
    ]
    body = []
    for title, text in sections:
        body += ["", "=" * 74, f"  {title}", "=" * 74, "", text.rstrip(), ""]
    try:
        REPORT.write_text(
            chr(10).join(header + ["  " + ln for ln in summary] + body),
            encoding="utf-8")
        beat(f"report written to {REPORT}")
    except Exception as exc:
        beat(f"could not write the report: {exc}")

    notify(
        "CartPilot: full test suite finished"
        + ("" if not result.returncode else " WITH FAILURES"),
        (("All suites passed against real Firestore."
          if not result.returncode else
          "Some suites failed or could not run.")
         + " The orphaned-order backfill ran PREVIEW ONLY — nothing was"
           " written, and .env.realdata.bak is still pending your approval."
           f" Report: {REPORT}"),
        chr(10).join(summary),
    )
    release_lock()
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
