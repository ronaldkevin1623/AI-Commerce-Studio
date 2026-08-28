"""
UCP — Universal Commerce Protocol surface.

UCP is the open specification Google and Shopify published for how AI agents
discover products, run checkout, and exchange post-purchase data. Its point
is composability: UCP defines the conversation shape and delegates the parts
that already have standards — MCP for tool access, AP2 for payment
authorisation, A2A for agent-to-agent delegation.

AI Commerce Studio had two of those three legs already. The MCP server exposes the
gated pipeline as tools; the mandate chain is AP2-shaped and publishes an
ES256 verification key. What was missing was the discovery layer that ties
them together and lets another agent find any of it without being told.

TWO DOCUMENTS, TWO DIRECTIONS:

  /.well-known/ucp        outward — what AI Commerce Studio offers. Another agent
                          fetches this to learn which services and
                          capabilities exist and where to reach them.

  /.well-known/ucp-agent  inward — who AI Commerce Studio is when it calls someone
                          else. Shopify's Global Catalog MCP refuses a
                          tools/call without a fetchable agent profile
                          ("invalid_profile_url"), so this is the document
                          that would let AI Commerce Studio search their catalog.

The manifest is generated rather than served as a static file so the signing
key and the endpoint list can never drift from what the application actually
does — a discovery document that lies about its own capabilities is worse
than no discovery document.
"""
import os

from fastapi import APIRouter, Request

from app.agent import mandates

router = APIRouter()

UCP_VERSION = "2026-04-08"
SPEC_BASE = f"https://ucp.dev/{UCP_VERSION}"

# AI Commerce Studio's own capability namespace. Declared under a commerce-studio.* id
# rather than borrowing a dev.ucp.* one, because these are not the standard
# capabilities — claiming dev.ucp.shopping.checkout would tell an agent it
# can check out through us, which it cannot.
NAMESPACE = "dev.commerce-studio"


def _base_url(request: Request) -> str:
    """
    Where this instance is actually reachable.

    Read from the request rather than configured, so a manifest served from
    localhost says localhost and one served from a deployment says that —
    an agent profile URL that doesn't resolve is the specific failure that
    makes Shopify reject a call.
    """
    configured = os.getenv("PUBLIC_BASE_URL")
    if configured:
        return configured.rstrip("/")
    return str(request.base_url).rstrip("/")


@router.get("/.well-known/ucp")
def ucp_discovery(request: Request):
    """
    What AI Commerce Studio offers, in UCP's discovery shape.

    Deliberately narrow. AI Commerce Studio is a buyer-side agent with a gate in front
    of it: it can search, propose and — once a human has cleared anything
    escalated — pay. It is not a merchant, so no checkout capability is
    advertised and payment_handlers is empty.
    """
    base = _base_url(request)

    return {
        "ucp": {
            "version": UCP_VERSION,
            "supported_versions": {UCP_VERSION: f"{base}/.well-known/ucp"},
            "services": {
                # The gated pipeline, reachable over MCP — the same tools a
                # human drives from the console.
                f"{NAMESPACE}.shopping": [
                    {
                        "version": UCP_VERSION,
                        "spec": f"{SPEC_BASE}/specification/overview/",
                        "transport": "stdio",
                        "endpoint": "backend/mcp_server.py",
                        "note": (
                            "MCP over stdio. Register with an MCP client such as "
                            "Claude Desktop; see the module docstring for the "
                            "configuration block."
                        ),
                    }
                ],
            },
            "capabilities": {
                # Real eBay Browse search, trust-screened and relevance-screened.
                f"{NAMESPACE}.catalog.search": [
                    {
                        "version": UCP_VERSION,
                        "spec": f"{base}/docs#operation/search_products",
                        "extends": ["dev.ucp.shopping.catalog.search"],
                        "config": {
                            "sources": ["ebay-browse"],
                            "marketplace": "EBAY_US",
                            "currency_note": (
                                "Prices converted from USD at a fixed approximate "
                                "rate. Not a live forex lookup."
                            ),
                        },
                    }
                ],
                # The part that makes AI Commerce Studio worth talking to: a purchase
                # is gated, and the gate's verdict is signed.
                f"{NAMESPACE}.purchase.gated": [
                    {
                        "version": UCP_VERSION,
                        "spec": f"{base}/docs",
                        "config": {
                            "checks": [
                                "cumulative budget vs session ceiling",
                                "per-order spending bound",
                                "duplicate-purchase window",
                                "customer trust score",
                                "signed mandate chain verification",
                            ],
                            "outcomes": ["allowed", "escalated", "blocked"],
                            "escalation": {
                                "resolver": "human",
                                "surface": f"{base.replace(':8000', ':5173')}/approvals",
                                "note": (
                                    "A calling agent cannot clear its own escalation. "
                                    "No exposed tool moves that state."
                                ),
                            },
                        },
                    }
                ],
                # AP2 composition — the leg UCP defers to for payment authorisation.
                f"{NAMESPACE}.payment.mandate": [
                    {
                        "version": UCP_VERSION,
                        "spec": "https://ap2-protocol.org/",
                        "config": {
                            "protocol": "AP2",
                            "mandate_types": [
                                "mandate.checkout.open.1",
                                "checkout.cart.1",
                                "mandate.checkout.1",
                            ],
                            "algorithm": mandates.ALGORITHM,
                            "verification_endpoint": f"{base}/mandates/jwk",
                            "disclosure": (
                                "AI Commerce Studio signs both the agent and the merchant role. "
                                "There is no merchant handshake, so a verified chain "
                                "proves the agent kept to the constraints the person "
                                "approved — not that any seller agreed to anything."
                            ),
                        },
                    }
                ],
                # Every gated action is logged and readable.
                f"{NAMESPACE}.audit.trail": [
                    {
                        "version": UCP_VERSION,
                        "spec": f"{base}/docs",
                        "config": {
                            "endpoint": f"{base}/growth-insights",
                            "records": [
                                "purchase_attempt", "run_abandoned", "payment_confirmed",
                                "payment_failed", "mandate_rejected",
                                "financial_bound_changed", "escalation_resolved",
                            ],
                        },
                    }
                ],
            },
            # AI Commerce Studio pays through Razorpay in test mode. It is not a UCP
            # payment handler and cannot settle to a third-party merchant, so
            # this stays empty rather than advertising a capability that would
            # fail the moment an agent tried to use it.
            "payment_handlers": {},
            "signing_keys": {
                "algorithm": mandates.ALGORITHM,
                "jwks_uri": f"{base}/mandates/jwk",
                "kid": mandates.thumbprint(),
            },
        }
    }


@router.get("/.well-known/ucp-agent")
def ucp_agent_profile(request: Request):
    """
    Who AI Commerce Studio is when it calls another UCP service.

    Shopify's Global Catalog MCP fetches this URL and rejects the call if it
    cannot resolve it, which is why this must be served from somewhere
    publicly reachable before AI Commerce Studio can search their catalog. On
    localhost it is still correct and still useful for local testing — it
    just isn't fetchable from the outside.
    """
    base = _base_url(request)

    return {
        "ucp_agent": {
            "version": UCP_VERSION,
            "name": "AI Commerce Studio",
            "description": (
                "A buyer-side shopping agent. Searches live listings, screens "
                "them, and gates every purchase behind bounded checks, human "
                "approval for anything escalated, and a signed AP2 mandate chain."
            ),
            "homepage": "https://github.com/ronaldkevin1623/AI Commerce Studio",
            "capabilities": [
                "dev.ucp.shopping.catalog.search",
                "dev.ucp.shopping.catalog.lookup",
            ],
            "signing_keys": {
                "algorithm": mandates.ALGORITHM,
                "jwks_uri": f"{base}/mandates/jwk",
                "kid": mandates.thumbprint(),
            },
            "contact": {"issues": "https://github.com/ronaldkevin1623/AI Commerce Studio/issues"},
        }
    }


@router.get("/ucp/merchant")
def merchant_link():
    """
    Whether the buyer can currently see a UCP merchant, and what that
    merchant says it can do.

    Surfaced so the console can state plainly that a second venue was
    reachable — or that it wasn't. An agent quietly falling back to
    search-only looks identical to one that never had a merchant, and the
    person deserves to be able to tell those apart.
    """
    from app.agent import merchant_client
    return merchant_client.describe()
