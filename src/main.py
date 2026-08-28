"""Cloud Run / FastAPI entrypoint for PayBridge Taskmaster Agent.

Handles:
1. Cloud Scheduler periodic ticks / Manual trigger (POST /reconcile or POST /)
2. Inbound Twilio WhatsApp webhooks (POST /webhook/whatsapp)
3. Health checks & Swagger UI (GET /health, GET /docs)
4. State & seed helpers (POST /seed, GET /state)

Run locally with:
    .venv/bin/uvicorn src.main:app --port 8080 --reload
"""

import json
import logging
import os
import re
from typing import Any

from fastapi import FastAPI, Request, Response, Form
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("paybridge-reconciler")

app = FastAPI(
    title="PayBridge Reconciliation Agent",
    description="Autonomous Taskmaster agent matching Paystack payments to invoices with Gemini 3.5 & WhatsApp outreach",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def parse_invoice_id_from_text(text: str) -> str | None:
    """Extract candidate invoice ID (e.g. INV-102, INV_123, 102) from freeform WhatsApp message."""
    if not text:
        return None
    patterns = [
        r"(?i)\b(inv[-_]?[0-9][0-9a-z_-]*)\b",
        r"(?i)invoice\s*[:#]?\s*([0-9a-z_-]+)",
        r"(?i)#([0-9a-z_-]+)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            matched = m.group(1).upper()
            if matched != "INVOICE":
                return matched
    return None


def handle_whatsapp_webhook(request_data: dict) -> tuple[dict, int, dict]:
    """Process incoming WhatsApp message from Twilio."""
    from . import notify, store

    from_number = request_data.get("From", "")
    message_body = request_data.get("Body", "").strip()

    logger.info("Received WhatsApp webhook from %s: '%s'", from_number, message_body)

    headers = {"Content-Type": "application/json"}

    if not from_number:
        return json.dumps({"error": "Missing 'From' phone number"}), 400, headers

    # Find pending transaction awaiting reply from this customer phone
    pending = store.find_pending_transaction_by_phone(from_number)
    if not pending:
        logger.info("No pending transaction awaiting reply for phone %s", from_number)
        return json.dumps({
            "status": "ignored",
            "message": "No pending unreconciled transaction found for this number."
        }), 200, headers

    txn_id, state = pending
    customer_name = state.get("customer_name", "Customer")
    amount = state.get("amount", "")

    # Try extracting invoice ID
    extracted_inv_id = parse_invoice_id_from_text(message_body) or message_body.strip()
    target_invoice = store.get_invoice(extracted_inv_id)

    # If exact invoice not found, check outstanding invoices matching candidate ID in text
    if not target_invoice:
        outstanding = store.get_outstanding_invoices()
        for inv in outstanding:
            if extracted_inv_id.lower() in inv.get("id", "").lower() or str(inv.get("id", "")).lower() in message_body.lower():
                target_invoice = inv
                extracted_inv_id = inv["id"]
                break

    if target_invoice:
        store.resolve_transaction(txn_id, extracted_inv_id, resolved_by="whatsapp_reply")
        notify.send_confirmation(
            to_whatsapp_number=from_number,
            name=customer_name,
            invoice_id=extracted_inv_id,
            amount=amount,
        )
        logger.info("Resolved transaction %s with invoice %s from WhatsApp reply.", txn_id, extracted_inv_id)
        return json.dumps({
            "status": "resolved",
            "transaction_id": txn_id,
            "invoice_id": extracted_inv_id
        }), 200, headers

    logger.warning("Could not match reply '%s' to any known invoice for transaction %s.", message_body, txn_id)
    return json.dumps({
        "status": "unresolved",
        "transaction_id": txn_id,
        "message": f"Invoice '{extracted_inv_id}' could not be verified."
    }), 200, headers


# ==========================================
# FastAPI Route Handlers
# ==========================================

@app.get("/")
@app.get("/health")
async def health_check():
    """Service health and metadata check."""
    return {
        "status": "healthy",
        "service": "PayBridge Reconciliation Agent",
        "version": "1.0.0",
        "track": "All Things Agentic Hackathon — Taskmaster Track",
    }


@app.post("/")
@app.post("/reconcile")
async def trigger_reconciliation():
    """Trigger the autonomous multi-tier reconciliation cycle."""
    from .agent import run_reconciliation_cycle

    try:
        summary = run_reconciliation_cycle()
        logger.info("Reconciliation cycle complete: %s", json.dumps(summary))
        return JSONResponse(content=summary, status_code=200)
    except Exception as e:
        logger.exception("Error during reconciliation cycle: %s", e)
        return JSONResponse(
            content={"error": "Reconciliation cycle failed", "details": str(e)},
            status_code=500,
        )


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """Twilio WhatsApp Inbound Webhook."""
    # Twilio sends application/x-www-form-urlencoded
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
    else:
        form_data = await request.form()
        data = dict(form_data)

    body_str, status_code, _ = handle_whatsapp_webhook(data)
    return Response(content=body_str, status_code=status_code, media_type="application/json")


@app.post("/seed")
async def seed_demo_data():
    """Seed test invoices and unreconciled state for live demo testing."""
    from . import store

    invoices = [
        {"id": "INV-101", "customer_name": "Amina Bello", "customer_email": "amina.bello@gmail.com", "customer_phone": "+2348011111111", "amount": 5000.00, "status": "outstanding"},
        {"id": "INV-102", "customer_name": "Chidi Okonkwo", "customer_email": "chidi.okonkwo@techcorp.ng", "customer_phone": "+2348022222222", "amount": 12500.00, "status": "outstanding"},
        {"id": "INV-103", "customer_name": "Tunde Bakare", "customer_email": "tunde.bakare@startup.io", "customer_phone": "+2349130110901", "amount": 8000.00, "status": "outstanding"},
    ]
    for inv in invoices:
        store.save_invoice(inv["id"], inv)

    return {"status": "seeded", "invoices_count": len(invoices)}


@app.get("/state")
async def get_system_state():
    """Get current snapshot of invoices and reconciliation match state."""
    from . import store
    return {
        "outstanding_invoices": store.get_outstanding_invoices(),
        "all_match_states": store.get_all_match_states(),
    }


# ==========================================
# Google Functions Framework Compatibility
# ==========================================

def handle_request(request=None):
    """Entrypoint for Google Cloud Functions / Functions Framework."""
    from .agent import run_reconciliation_cycle

    path = getattr(request, "path", "/") if request else "/"
    if "/webhook" in path or (request and getattr(request, "form", None) and "From" in request.form):
        form_data = dict(request.form) if hasattr(request, "form") and request.form else {}
        if not form_data and hasattr(request, "get_json"):
            form_data = request.get_json(silent=True) or {}
        res, code = handle_whatsapp_webhook(form_data)
        return json.dumps(res), code, {"Content-Type": "application/json"}

    try:
        summary = run_reconciliation_cycle()
        return json.dumps(summary, indent=2), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("src.main:app", host="0.0.0.0", port=port, reload=True)
