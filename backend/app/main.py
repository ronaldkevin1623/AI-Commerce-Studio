from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.api_core.exceptions import GoogleAPICallError, ResourceExhausted

from app.routes import (
    recovery_routes,
    policy_routes,
    agent_routes,
    webhook_routes,
    refund_routes,
    payment_routes,
    negotiator_routes,
    settings_routes,
    order_routes,
    growth_routes,
    proposal_routes,
    cart_routes,
    ucp_routes,
    merchant_store_routes,
    redteam_routes,
    security_routes,
    preflight_routes,
    image_routes,
    product_check_routes,
    autonomy_routes, venue_routes, recommend_routes, sector_routes, growth_agent_routes, x402_routes, acp_routes,
)

app = FastAPI(title="AI Commerce Studio API")


# ── When the store itself is unavailable ─────────────────────────────────
#
# Found by a test run during a Firestore free-tier quota outage: seven
# endpoints — including /merchant/catalog, which is the one a BUYING AGENT
# reads over UCP — turned a datastore error into an unhandled 500 with a
# stack trace in the log and "Internal Server Error" on the wire.
#
# That is the wrong answer twice over. An agent cannot tell a 500 from a
# broken integration, so it has no way to know the shop is fine and merely
# unreachable; and this project's whole position is that a component which
# cannot answer should say so rather than failing opaquely. 503 with a
# readable reason is what a caller can actually act on, and it matches how
# the buyer side already treats an unreachable venue: fewer options, not a
# broken run.
@app.exception_handler(GoogleAPICallError)
async def datastore_unavailable(request: Request, exc: GoogleAPICallError):
    quota = isinstance(exc, ResourceExhausted)
    print(f"[store] {request.url.path} could not read the datastore: "
          f"{type(exc).__name__}: {exc}", flush=True)
    return JSONResponse(
        status_code=503,
        content={
            "error": "datastore_unavailable",
            "detail": ("The project's Firestore has hit its free-tier daily "
                       "quota, so this endpoint cannot read its records "
                       "right now. It resets at midnight Pacific."
                       if quota else
                       "This endpoint could not reach its datastore."),
            "retryable": True,
            # Named so a buying agent can tell "the shop has nothing for you"
            # from "the shop could not be asked" — which are different facts
            # and should not both look like an empty catalogue.
            "is_empty_result": False,
        },
    )

# Loosened for hackathon dev — tighten allow_origins before any real deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_routes.router)
app.include_router(webhook_routes.router)
app.include_router(refund_routes.router)
app.include_router(payment_routes.router)
app.include_router(negotiator_routes.router)
app.include_router(settings_routes.router)
app.include_router(order_routes.router)
app.include_router(growth_routes.router)
app.include_router(proposal_routes.router)
app.include_router(cart_routes.router)
app.include_router(ucp_routes.router)
app.include_router(merchant_store_routes.router)
app.include_router(redteam_routes.router)
app.include_router(security_routes.router)
app.include_router(preflight_routes.router)
app.include_router(image_routes.router)
app.include_router(product_check_routes.router)
app.include_router(autonomy_routes.router)
app.include_router(venue_routes.router)
app.include_router(recommend_routes.router)
app.include_router(sector_routes.router)
app.include_router(growth_agent_routes.router)
app.include_router(x402_routes.router)
app.include_router(acp_routes.router)
app.include_router(policy_routes.router)
app.include_router(recovery_routes.router)


@app.get("/health")
def health():
    # The datastore is reported because it is the one thing a caller cannot
    # work out for itself. Anything talking to this server over HTTP —
    # the seeder especially — was previously guessing from its OWN
    # environment, which can disagree with the server's and did.
    from app.firebase_client import store_binding
    return {"status": "ok", "datastore": store_binding()}