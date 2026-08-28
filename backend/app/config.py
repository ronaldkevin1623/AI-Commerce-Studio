"""
Loads all environment config in one place so nothing is hardcoded
anywhere else in the codebase.
"""
import os
from dotenv import load_dotenv

load_dotenv()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")

FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "./serviceAccountKey.json")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# Where AI Commerce Studio looks for a UCP merchant. Defaults to this same process,
# because the demo store ships with the project — but it is a URL, not an
# import, so pointing it at another UCP store is a config change and not a
# code change.
MERCHANT_BASE_URL = os.getenv("MERCHANT_BASE_URL", "http://127.0.0.1:8010")

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")

# Risk gate: orders above this (in paise) get ESCALATED instead of auto-approved
AUTO_APPROVE_LIMIT_PAISE = int(os.getenv("AUTO_APPROVE_LIMIT_PAISE", "500000"))
print(f"[DEBUG] Loaded Key ID: {RAZORPAY_KEY_ID}")
print(f"[DEBUG] Loaded Secret length: {len(RAZORPAY_KEY_SECRET) if RAZORPAY_KEY_SECRET else 'MISSING'}")