from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import (
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
)

app = FastAPI(title="AI Commerce Studio API")

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


@app.get("/health")
def health():
    return {"status": "ok"}