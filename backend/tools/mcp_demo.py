"""
An external agent shops through AI Commerce Studio, and gets stopped.

Run this and it speaks real MCP — JSON-RPC 2.0 over stdio — to the same
server Claude Desktop would connect to. Nothing here is simulated: the tools
are the tools, the gate is the gate, and the Razorpay order at the end is a
real order in test mode.

WHAT IT IS FOR:
The interesting claim AI Commerce Studio makes is not that it can shop. It is that
something else can shop through it and still be bounded. That is hard to
show from inside the app, because the app is the thing being trusted. Here
the buyer is a separate process holding no credentials and no privileges,
reaching AI Commerce Studio only through five declared tools — and it still cannot
approve its own purchase.

    python tools/mcp_demo.py

The run pauses at the escalation. Approve or deny it at
http://localhost:5173/approvals and the agent picks up whatever you decided.

Requires the backend running (for the approvals UI) and Ollama up.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "venv" / "Scripts" / "python.exe"
SERVER = ROOT / "mcp_server.py"

QUERY = "noise cancelling headphones"
BUDGET_INR = 15000
POLL_SECONDS = 3
GIVE_UP_AFTER = 300


class Client:
    """A minimal MCP client. Enough of the protocol to hold a conversation."""

    def __init__(self):
        self.proc = subprocess.Popen(
            [str(PYTHON), str(SERVER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
        )
        self.id = 0

    def _send(self, method, params):
        self.id += 1
        self.proc.stdin.write(json.dumps({
            "jsonrpc": "2.0", "id": self.id, "method": method, "params": params,
        }) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def handshake(self):
        return self._send("initialize", {})["result"]

    def tools(self):
        return self._send("tools/list", {})["result"]["tools"]

    def call(self, name, **arguments):
        reply = self._send("tools/call", {"name": name, "arguments": arguments})
        return json.loads(reply["result"]["content"][0]["text"])

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.terminate()
        except Exception:
            pass


def say(step, text):
    print(f"\n\033[1m{step}\033[0m  {text}", flush=True)


def detail(text):
    print(f"    {text}", flush=True)


def main():
    if not PYTHON.exists():
        sys.exit(f"No interpreter at {PYTHON} — run this from the backend directory.")

    client = Client()
    try:
        info = client.handshake()
        say("CONNECT", f"Speaking MCP to {info['serverInfo']['name']} "
                       f"v{info['serverInfo']['version']}")
        names = [t["name"] for t in client.tools()]
        detail(f"{len(names)} tools offered: {', '.join(names)}")
        detail("No credentials were exchanged. This process holds nothing.")

        say("SEARCH", f"Asking for '{QUERY}' under Rs{BUDGET_INR:,}")
        found = client.call("search_products", query=QUERY, max_price_inr=BUDGET_INR)
        if not found.get("count"):
            sys.exit("eBay returned nothing for that query — try another.")
        detail(f"{found['count']} live listings came back, already trust-screened.")

        # The dearest one, deliberately: this demo is about the boundary, and a
        # cheap listing would sail through without ever reaching it.
        target = sorted(found["products"], key=lambda p: -(p.get("price_inr") or 0))[0]
        detail(f"Picking the most expensive: {target['name'][:60]}")
        detail(f"Rs{target['price_inr']:,.2f}")

        say("PROPOSE", "Running it through AI Commerce Studio's gate")
        proposal = client.call(
            "propose_purchase", product_id=target["id"],
            query=QUERY, max_price_inr=BUDGET_INR,
        )
        verdict = proposal.get("decision")
        detail(f"Verdict: {verdict.upper()} — {proposal.get('reason')}")

        if verdict == "blocked":
            detail("The gate refused outright. Nothing further to do.")
            return

        proposal_id = proposal["proposal_id"]

        say("CONFIRM", "The agent tries to complete the purchase anyway")
        attempt = client.call("confirm_purchase", proposal_id=proposal_id)
        if attempt.get("ok"):
            detail("It went through — this purchase was inside the auto-approve limit.")
            detail(f"Order {attempt.get('order_id')} for Rs{attempt.get('amount_inr'):,.2f}")
            return

        detail(f"REFUSED — {attempt.get('error')}")
        detail(attempt.get("action_required", ""))
        # Printed so whoever is watching can match this run to the card on
        # screen — there may be more than one waiting.
        detail(f"This proposal: {proposal_id}")

        say("WAIT", "The agent cannot proceed. It has to ask a person.")
        detail("Approve or deny at http://localhost:5173/approvals")
        detail(f"Polling check_approval every {POLL_SECONDS}s…")

        deadline = time.time() + GIVE_UP_AFTER
        status = "awaiting_human"
        while time.time() < deadline:
            time.sleep(POLL_SECONDS)
            status = client.call("check_approval", proposal_id=proposal_id).get("status")
            if status != "awaiting_human":
                break
            print("    …still waiting", flush=True)
        else:
            detail("Nobody decided in time. The agent gave up rather than retrying.")
            return

        say("DECIDED", f"A human said: {status}")
        if status != "ready":
            detail("Denied. The agent stops here — it has no way to overrule that.")
            return

        say("ORDER", "Now the agent may finish, and only now")
        done = client.call("confirm_purchase", proposal_id=proposal_id)
        if done.get("ok"):
            detail(f"Razorpay order {done.get('razorpay_order_id')} "
                   f"for Rs{done.get('amount_inr'):,.2f}")
            detail(done.get("checkout_note", ""))
        else:
            detail(f"Still refused: {done.get('error')}")
            detail("The gate re-runs every check at confirm time — an approval is "
                   "not a blank cheque, and prices move.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
