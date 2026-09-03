"""
WHICH DATASTORE THIS PROCESS USES, DECIDED ONCE AND REFUSED IF AMBIGUOUS.

The store is chosen by CARTPILOT_STORE at launch, not by rewriting a file
that a running process already read. That is the whole point: a process's
binding becomes a property of how it was started, and nothing outside it
can change the answer afterwards.

This module runs BEFORE any Firestore client is constructed. It lives here
rather than in main.py because 34 modules import app.firebase_client
directly — every test suite among them — and none of those go through
main.py. A guard there would be bypassed by all of them. Placed in the
import path of the client itself, it cannot be skipped by anything that
touches Firestore at all.

WHAT IT REFUSES, AND WHY IT EXITS RATHER THAN WARNS

A server that comes up against the store you did not intend is the entire
failure this exists to prevent, so there is no "log it and continue" path.
It prints a banner and calls os._exit(1) — uncatchable, unlike SystemExit,
which a bare `except:` anywhere up the import chain could swallow. At
import time there is nothing to clean up, so bypassing cleanup costs
nothing.

    1. A leftover FIRESTORE_EMULATOR_HOST in .env.

       load_dotenv() does NOT override a variable already present in the
       real environment. So .env can carry that key, load_dotenv can
       decline to set it, and a check that only reads os.environ misses it
       entirely. Both are read here: the environment AND the raw file text.

    2. An externally-set FIRESTORE_EMULATOR_HOST that disagrees with
       CARTPILOT_STORE. Two mechanisms with an undefined winner is worse
       than one bad mechanism.

    3. Another LIVE process on this machine already bound to a different
       store. Without this, per-process selection would make heterogeneous
       instances easier to create than a shared file ever did — an order
       written by one server and its capture by another.

WHAT IT STILL CANNOT GUARANTEE, stated rather than implied:

  - Processes on separate filesystems (another machine, an isolated
    container) share no registry, so nothing here constrains them.
  - Two processes starting within the same few milliseconds can both read
    "no conflict" before either writes. The window is milliseconds against
    a checkout measured in minutes, but it is not zero.
  - A dead process whose PID was recycled by an unrelated process reads as
    live. That fails CLOSED — it refuses to start rather than allowing a
    mismatch — and the banner names the exact file to delete.
"""
import os
import sys
import time
import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND / ".env"
REGISTRY = BACKEND / ".bindings"

# A registry entry older than this is ignored no matter what the PID says.
# A backstop for the recycled-PID case above, so a machine can always be
# unstuck by waiting rather than only by deleting a file.
MAX_ENTRY_AGE = 24 * 60 * 60

DEFAULT_EMULATOR_HOST = "127.0.0.1:8085"


def _die(title: str, lines: list[str]) -> None:
    """Say exactly what is wrong and stop. Never returns."""
    width = 74
    out = sys.stderr
    print("\n" + "=" * width, file=out)
    print(f"  REFUSING TO START — {title}", file=out)
    print("=" * width, file=out)
    for line in lines:
        print(f"  {line}", file=out)
    print("=" * width + "\n", file=out)
    out.flush()
    sys.stdout.flush()
    # Not SystemExit: that is an exception, and an exception can be caught.
    os._exit(1)


def _env_file_sets_emulator() -> str | None:
    """
    The emulator host .env sets, ignoring comments — or None.

    Read from the file rather than from os.environ precisely because
    load_dotenv() will not have applied it if the variable was already set
    in the real environment.
    """
    if not ENV_FILE.exists():
        return None
    try:
        text = ENV_FILE.read_text(encoding="utf-8")
    except Exception:
        return None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "FIRESTORE_EMULATOR_HOST":
            return value.strip().strip('"').strip("'") or None
    return None


def _alive(pid: int) -> bool:
    """Is this PID a running process? Cheap, stdlib only."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        # 259 is STILL_ACTIVE. A finished process keeps a handle briefly.
        return exit_code.value == 259
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _live_entries() -> list[dict]:
    """Registry entries whose process is still running. Sweeps the rest."""
    if not REGISTRY.exists():
        return []
    now = time.time()
    live = []
    for path in REGISTRY.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            path.unlink(missing_ok=True)
            continue
        stale = (now - float(data.get("started_at") or 0)) > MAX_ENTRY_AGE
        if stale or not _alive(int(data.get("pid") or 0)):
            path.unlink(missing_ok=True)
            continue
        data["_path"] = str(path)
        live.append(data)
    return live


def _register(binding: str) -> None:
    try:
        REGISTRY.mkdir(parents=True, exist_ok=True)
        (REGISTRY / f"{os.getpid()}.json").write_text(json.dumps({
            "pid": os.getpid(),
            "binding": binding,
            "started_at": time.time(),
            "argv": " ".join(sys.argv[:3]),
        }), encoding="utf-8")
    except Exception as exc:
        # Failing to record the binding must not stop the process — the
        # checks above have already run. It only weakens the next process's
        # view, and that is a smaller harm than refusing to boot.
        print(f"[datastore] could not register binding: {exc}", flush=True)


def _require_emulator_running(host: str = DEFAULT_EMULATOR_HOST) -> None:
    """
    Fail with instructions if the emulator is not up.

    Without this the Firestore client is created happily and every call
    hangs or fails deep in gRPC with a connection error that says nothing
    about what to do. The fix is one command; the error should say it.
    """
    import socket
    name, _, port = host.partition(":")
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(1.5)
    try:
        if probe.connect_ex((name, int(port or 8085))) == 0:
            return
    except Exception:
        pass
    finally:
        probe.close()
    _die(f"the Firestore emulator is not running on {host}", [
        "This project uses the local emulator by default, so there is no",
        "daily quota and no cloud dependency while you build.",
        "",
        "Start it (from the repo root):",
        "",
        "    start-emulator.cmd",
        "",
        "It imports firebase-export/ on start and writes it back on exit,",
        "so your demo data survives a restart.",
    ])


def resolve_binding() -> str:
    """
    Decide this process's datastore, refuse if anything is ambiguous, and
    set FIRESTORE_EMULATOR_HOST if the emulator was chosen.

    Must be called before the Firestore client is constructed. Returns the
    binding string that gets stamped onto every order.
    """
    # DEFAULT IS THE LOCAL EMULATOR, deliberately.
    #
    # Real Firestore is on a free tier with a daily read quota, and hitting
    # it mid-demo takes the whole app down. Nothing in the product needs
    # the real project: the agent, the sectors, the recommendations and the
    # merchant loop behave identically against the emulator, and Razorpay
    # is real either way because it is a different service.
    #
    # The one thing that genuinely needs real Firestore is reconciling
    # recorded money against the Razorpay account. That is an occasional
    # check, not a mode to develop in, so it is the case that has to ask
    # (CARTPILOT_STORE=real) rather than the everyday case.
    requested = (os.environ.get("CARTPILOT_STORE") or "emulator").strip().lower()

    # ── 1. a leftover in .env, whether or not it reached the environment ──
    leftover = _env_file_sets_emulator()
    if leftover:
        _die("FIRESTORE_EMULATOR_HOST is still set in .env", [
            f".env sets FIRESTORE_EMULATOR_HOST={leftover}",
            f"CARTPILOT_STORE={requested!r}",
            "",
            "The datastore is chosen by CARTPILOT_STORE now. That key in .env",
            "is a second mechanism with an undefined winner, and it decides",
            "which store your orders and payments are written to.",
            "",
            f"Fix: remove the FIRESTORE_EMULATOR_HOST line from {ENV_FILE}",
            "     and start with CARTPILOT_STORE=emulator if you wanted the",
            "     emulator.",
        ])

    # ── 2. an externally-set host that disagrees with the request ────────
    external = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if external and requested == "real":
        _die("FIRESTORE_EMULATOR_HOST is set but CARTPILOT_STORE=real", [
            f"FIRESTORE_EMULATOR_HOST={external} is set in the environment,",
            "but this process was asked for the real datastore.",
            "",
            "Refusing rather than picking one: coming up against the store",
            "you did not intend is the failure this guard exists to prevent.",
        ])

    if requested.startswith("emulator"):
        # Accept "emulator" or "emulator:host:port".
        _, _, override = requested.partition(":")
        host = override or external or DEFAULT_EMULATOR_HOST
        if external and override and external != override:
            _die("Two different emulator hosts were requested", [
                f"CARTPILOT_STORE asks for {override}",
                f"FIRESTORE_EMULATOR_HOST is {external}",
            ])
        # Set BEFORE the client is constructed — this is the whole reason
        # this function has to run first.
        # Probed AFTER the host is resolved. Calling this before meant it
        # always checked the default port and reported the wrong one as
        # down — a diagnostic that sends you to look at the wrong thing.
        _require_emulator_running(host)
        os.environ["FIRESTORE_EMULATOR_HOST"] = host
        binding = f"emulator:{host}"
    elif requested == "real":
        binding = "real"
    else:
        _die(f"CARTPILOT_STORE={requested!r} is not a datastore", [
            "Valid values: 'real', 'emulator', or 'emulator:<host>:<port>'.",
            "",
            "Refusing rather than defaulting: a typo silently falling back to",
            "real data is exactly the class of accident this prevents.",
        ])

    # ── 3. another live process on a different store ─────────────────────
    conflicts = [e for e in _live_entries() if e.get("binding") != binding]
    if conflicts:
        lines = [f"This process wants: {binding}", ""]
        for entry in conflicts:
            lines.append(f"  pid {entry['pid']} is running on {entry['binding']}")
            lines.append(f"      started {entry.get('argv', '')}")
            lines.append(f"      {entry['_path']}")
        lines += [
            "",
            "Two servers on different datastores means an order can be",
            "written by one and its payment confirmed by the other, leaving",
            "neither store with a complete record.",
            "",
            "Fix: stop the other process, or start this one on the same",
            "     store. If that pid is genuinely dead, delete the file above.",
        ]
        _die("another process is bound to a different datastore", lines)

    _register(binding)
    return binding
