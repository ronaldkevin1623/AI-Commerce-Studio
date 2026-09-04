"""
THE TRANSACTION POLICY OVER HTTP.

  GET /transaction-policy              every bound, live, with its enforcer
  GET /transaction-policy/check        would this amount clear the bound?

Exists so the answer to "what stops this agent" is one request rather than a
tour of five modules — and so the checkout screen can show the bound it is
about to be judged against BEFORE the person commits, rather than reporting
the refusal afterwards.
"""
from fastapi import APIRouter

from app.agent import policy

router = APIRouter(tags=["policy"])


@router.get("/transaction-policy")
def transaction_policy():
    return policy.transaction_policy()


@router.get("/transaction-policy/check")
def check(amount_paise: int = 0):
    """
    One bound of six. The payload names the five it did not check, so a
    green tick here can never be mistaken for the gate's verdict.
    """
    return policy.check(amount_paise)
