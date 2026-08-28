"""
AI Commerce Studio MCP server — lets another agent shop through AI Commerce Studio's gate.

Point Claude Desktop (or any MCP client) at this and it can search real eBay
listings and propose purchases. What it cannot do is buy something the gate
refuses, or approve its own escalation. Every tool call lands in the same
audit trail as the console's own runs.

WHY THIS IS HAND-ROLLED RATHER THAN USING THE OFFICIAL SDK:
    The `mcp` package pulls a newer pydantic than this project's FastAPI is
    pinned against, and installing it while uvicorn holds the compiled
    pydantic_core DLL breaks the venv on Windows. MCP is JSON-RPC 2.0 over
    newline-delimited stdio; the handful of methods a tool server needs are
    implemented below with nothing but the standard library. Zero new
    dependencies, and nothing about the running stack has to move.

Register it with Claude Desktop by adding to claude_desktop_config.json:

    {
      "mcpServers": {
        "commerce-studio": {
          "command": "C:\\\\office\\\\project\\\\Razorpay-Buildathon\\\\AI Commerce Studio\\\\backend\\\\venv\\\\Scripts\\\\python.exe",
          "args": ["C:\\\\office\\\\project\\\\Razorpay-Buildathon\\\\AI Commerce Studio\\\\backend\\\\mcp_server.py"]
        }
      }
    }

Everything this process writes to stdout is protocol. Diagnostics go to
stderr — a stray print() to stdout corrupts the stream and the client will
disconnect without explaining why.
"""
import json
import sys
import traceback

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "commerce-studio"
SERVER_VERSION = "1.0.0"

# The protocol owns the real stdout, and nothing else may touch it.
#
# This is not defensive tidiness — config.py prints "[DEBUG] Loaded Key ID"
# on import, catalog.py prints when eBay falls back, settings.py prints when
# Firestore is unreachable. Any one of those lands mid-stream and the client
# gets "[DEBU..." where it expected JSON, then disconnects without saying
# why. Swapping sys.stdout for stderr means every print anywhere in the
# codebase becomes a harmless diagnostic instead of a corrupt frame.
_PROTOCOL_OUT = sys.stdout
sys.stdout = sys.stderr


def log(message: str) -> None:
    print(f"[commerce-studio-mcp] {message}", file=sys.stderr, flush=True)


def emit(payload: dict) -> None:
    _PROTOCOL_OUT.write(json.dumps(payload) + "\n")
    _PROTOCOL_OUT.flush()


# ── Tool definitions ─────────────────────────────────────────────────────
# Descriptions are written for the calling model. They state the boundaries
# plainly, because a model that understands it cannot self-approve will ask
# the person instead of retrying — which is the behaviour we want.

TOOLS = [
    {
        "name": "search_products",
        "description": (
            "Search real, live eBay listings under a budget. Results are screened by "
            "AI Commerce Studio's trust agent, which flags price outliers, weak sellers and risky "
            "conditions. Read-only: this does not spend anything. Prices are converted "
            "from USD at a fixed approximate rate."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for, e.g. 'wireless earbuds'"},
                "max_price_inr": {"type": "integer", "description": "Budget ceiling in rupees"},
            },
            "required": ["query", "max_price_inr"],
        },
    },
    {
        "name": "propose_purchase",
        "description": (
            "Run AI Commerce Studio's full gate over one listing: cumulative budget, per-order "
            "spending bound, duplicate window, customer trust score, and a signed mandate "
            "chain. Returns allowed, escalated or blocked. This does NOT charge anything "
            "and does not create an order — call confirm_purchase afterwards. If the "
            "result is 'escalated', a human must approve it in AI Commerce Studio's own UI; you "
            "cannot approve it yourself and no tool here will let you."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "id from search_products"},
                "query": {"type": "string", "description": "the same query used to find it"},
                "max_price_inr": {"type": "integer", "description": "the same budget ceiling"},
            },
            "required": ["product_id", "query", "max_price_inr"],
        },
    },
    {
        "name": "confirm_purchase",
        "description": (
            "Create a real Razorpay order for a proposal. Every check is re-run from "
            "scratch first — the earlier verdict is not trusted, because prices and "
            "budgets move. Refuses if the gate now blocks, if the listing's price has "
            "changed since approval, or if a human approval is still outstanding. "
            "Creating the order does not pay for it: a person completes checkout. "
            "Safe to retry: this call is idempotent on the proposal id, so a "
            "repeat returns the original order rather than charging twice."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"proposal_id": {"type": "string"}},
            "required": ["proposal_id"],
        },
    },
    {
        "name": "check_approval",
        "description": (
            "Check where a proposal stands, including whether a human has approved or "
            "denied an escalated purchase. Poll this after telling the person to review "
            "it at http://localhost:5173/approvals."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"proposal_id": {"type": "string"}},
            "required": ["proposal_id"],
        },
    },
    {
        "name": "get_audit_trail",
        "description": (
            "Recent decisions AI Commerce Studio has logged — purchases, blocks, escalations, "
            "abandonments and configuration changes. Every financial action the agent "
            "takes is recorded here with its reason."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "default 20"}},
        },
    },
]


# ── Tool implementations ─────────────────────────────────────────────────

def _broker():
    # Imported lazily so a Firestore or Razorpay failure surfaces as a tool
    # error the client can read, rather than killing the process at startup.
    from app.agent import broker
    return broker


def call_tool(name: str, args: dict) -> dict:
    broker = _broker()

    if name == "search_products":
        return broker.search(args["query"], args["max_price_inr"])

    if name == "propose_purchase":
        return broker.propose(
            product_id=args["product_id"],
            query=args["query"],
            max_price_inr=args["max_price_inr"],
        )

    if name == "confirm_purchase":
        # Idempotent on the proposal id, so a client retrying a timed-out
        # call replays the original order instead of creating a second one.
        return broker.confirm(
            args["proposal_id"],
            ucp_agent=args.get("ucp_agent"),
            request_id=args.get("request_id"),
        )

    if name == "check_approval":
        return broker.status(args["proposal_id"])

    if name == "get_audit_trail":
        from app.firebase_client import list_decisions
        rows = list_decisions(limit=int(args.get("limit") or 20))
        return {"decisions": [{
            "action": r.get("action_type"),
            "decision": r.get("decision"),
            "reason": r.get("reason"),
            "amount_inr": round((r.get("amount_paise") or 0) / 100, 2),
        } for r in rows]}

    raise ValueError(f"Unknown tool: {name}")


# ── JSON-RPC plumbing ────────────────────────────────────────────────────

def result(request_id, payload):
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: dict):
    """Returns a response dict, or None for notifications (which get no reply)."""
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return result(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })

    # Notifications carry no id and must not be answered.
    if method in ("notifications/initialized", "initialized"):
        return None

    if method == "tools/list":
        return result(request_id, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments") or {}
        try:
            payload = call_tool(tool_name, args)
            return result(request_id, {
                "content": [{"type": "text", "text": json.dumps(payload, indent=2, default=str)}],
                "isError": False,
            })
        except Exception as exc:
            log(f"tool {tool_name} failed: {exc}\n{traceback.format_exc()}")
            # Reported as a tool-level error, not a protocol error, so the
            # model can read what went wrong and adjust.
            return result(request_id, {
                "content": [{"type": "text", "text": f"Tool failed: {exc}"}],
                "isError": True,
            })

    if method == "ping":
        return result(request_id, {})

    if request_id is None:
        return None
    return error(request_id, -32601, f"Method not found: {method}")


def main():
    log("started — waiting for a client on stdio")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            log(f"bad JSON: {exc}")
            continue

        try:
            response = handle(message)
        except Exception as exc:
            log(f"handler crashed: {exc}\n{traceback.format_exc()}")
            response = error(message.get("id"), -32603, str(exc))

        if response is not None:
            emit(response)

    log("stdin closed — exiting")


if __name__ == "__main__":
    main()
