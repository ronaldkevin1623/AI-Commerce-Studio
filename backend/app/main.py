from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import agent_routes, webhook_routes, refund_routes, payment_routes

app = FastAPI(title="CartPilot API")

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


@app.get("/health")
def health():
    return {"status": "ok"}