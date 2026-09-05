"""
PUT THE MERCHANT'S DIALS BACK THE WAY THE SUITE FOUND THEM.

Several suites have to move a real setting to test the bound behind it: you
cannot prove a daily cap refuses anything without a daily cap that is spent,
and you cannot prove a kill switch stops an agent without switching it off.
That is legitimate, and the suites explain why they do it.

What is not legitimate is leaving it that way. `settings.apply()` writes
through to Firestore (`agent_settings/current`), so these are not
process-local test values — they are the live dials the running app reads on
its next lookup, and they stay moved after the process that moved them has
exited. Two real failures came out of that, both from
tests/audit_24_growth.py:

  * The daily growth cap was left at whatever headroom the suite computed
    for itself — ₹7,713 against a default of ₹500 — so the merchant's real
    bound was whatever the last test run happened to need.
  * The suite finishes by switching growth off to prove the kill switch
    blocks, and left it off. Every proposal in the merchant console then
    showed as blocked, which is indistinguishable from a broken feature.

WHY atexit AND NOT ONLY try/finally

A `finally` covers the block it wraps, and these suites are flat scripts
that move dials in a dozen places and can leave from any of them on a failed
assertion or an unhandled exception. Registering the restore up front covers
all of it, and there is no way to add a dial change further down the file
that forgets to be covered. `restore()` is also called explicitly at the
foot of each suite, on the ordinary path, while the process is
unquestionably healthy — atexit is the net under the failure path, not the
main mechanism, because it does not run for os._exit(), a segfault or a
kill -9.

WHOLE NODES, NOT THE KEYS A SUITE NAMED

Restoring the whole node is deliberate: a suite that calls
`settings.reset()` wipes keys it never named, and putting back only the
named ones would silently leave the rest at defaults.

WHERE THIS LIVES

The backend root, not tests/, because both suites insert this directory on
sys.path themselves before importing anything. That makes the import work
whether a suite is run as a script, through tests/run_all.py, or as
`python -m`; a helper under tests/ resolves in the first two cases and not
the third.
"""
import atexit

from app.agent import settings

# node -> the values it held before any suite touched it. First snapshot
# wins: a second protect() call in the same process must not record dials a
# test has already moved as if they were the merchant's.
_snapshot: dict[str, dict] = {}
_registered = False


def protect(*nodes: str) -> dict[str, dict]:
    """
    Snapshot the named settings nodes — every node the spec declares if none
    are named — and arrange for them to be written back when the process
    ends, however it ends.

    Passing no nodes is the right choice for a suite that calls
    `settings.reset()`, which resets all of them.

    Returns the snapshot, so a caller that wants to assert on it can.
    """
    global _registered

    live = settings.all_settings()
    chosen = list(nodes) or list(live.keys())

    unknown = [node for node in chosen if node not in live]
    if unknown:
        # Loudly, at the top of a run: a typo here reads as protection and
        # provides none, which is worse than no guard at all.
        raise ValueError(
            f"dial_guard.protect() asked to protect unknown node(s) {unknown}; "
            f"known nodes are {sorted(live)}"
        )

    for node in chosen:
        _snapshot.setdefault(node, dict(live[node]))

    if not _registered:
        atexit.register(restore)
        _registered = True

    return {node: dict(values) for node, values in _snapshot.items()}


def restore() -> list[dict]:
    """
    Write the snapshot back and report what moved. Safe to call twice — the
    second call has nothing left to put back, which is what makes an
    explicit call at the end of a suite and the atexit net compatible.
    """
    if not _snapshot:
        return []

    # Cleared before the write, not after: if the write raises, the atexit
    # handler must not retry it in the middle of interpreter shutdown and
    # bury the suite's own error under a second traceback.
    patch = {node: dict(values) for node, values in _snapshot.items()}
    _snapshot.clear()

    try:
        changes = settings.apply(patch)
    except Exception as exc:
        # Loudly, and naming the values: a merchant whose dials were left
        # mutated needs to know exactly what to put back by hand.
        print(f"[dial_guard] COULD NOT RESTORE {sorted(patch)}: {exc}",
              flush=True)
        print(f"[dial_guard] the values they should hold are: {patch}",
              flush=True)
        return []

    if changes:
        moved = ", ".join(f"{c['node']}.{c['key']} {c['old']!r} <- {c['new']!r}"
                          for c in changes)
        print(f"[dial_guard] restored {moved}", flush=True)
    else:
        print(f"[dial_guard] {', '.join(sorted(patch))} already as found",
              flush=True)
    return changes
