"""Firestore-backed state: outstanding invoices and reconciliation status.

Collections:
  invoices        -- outstanding invoices awaiting payment
  match_state     -- per-transaction status: matched | awaiting_reply | resolved
"""

import os
from typing import Any

# In-memory store for local testing / simulations when Firestore is unavailable
_memory_invoices: dict[str, dict[str, Any]] = {}
_memory_match_state: dict[str, dict[str, Any]] = {}

_client = None


def is_memory_mode() -> bool:
    val = os.environ.get("USE_IN_MEMORY_STORE", "").lower()
    if val in ("1", "true", "yes"):
        return True
    proj = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if not proj or proj.startswith("your-gcp-project") or proj == "none":
        return True
    return False


def get_client():
    global _client
    if is_memory_mode():
        return None
    if _client is None:
        try:
            from google.cloud import firestore
            _client = firestore.Client(project=os.environ["GOOGLE_CLOUD_PROJECT"])
        except Exception as e:
            # Fall back gracefully to memory store if cloud credentials unavailable
            return None
    return _client


def save_invoice(invoice_id: str, data: dict[str, Any]) -> None:
    """Create or update an invoice in the store."""
    db = get_client()
    if db is None:
        _memory_invoices[invoice_id] = {"id": invoice_id, **data}
        return
    db.collection("invoices").document(invoice_id).set(data, merge=True)


def get_invoice(invoice_id: str) -> dict | None:
    """Retrieve an invoice by ID."""
    db = get_client()
    if db is None:
        return _memory_invoices.get(invoice_id)
    doc = db.collection("invoices").document(invoice_id).get()
    return {**doc.to_dict(), "id": doc.id} if doc.exists else None


def get_outstanding_invoices() -> list[dict]:
    """Retrieve all invoices with status 'outstanding'."""
    db = get_client()
    if db is None:
        return [
            inv for inv in _memory_invoices.values()
            if inv.get("status") == "outstanding"
        ]
    docs = db.collection("invoices").where("status", "==", "outstanding").stream()
    return [{**d.to_dict(), "id": d.id} for d in docs]


def get_match_state(transaction_id: str) -> dict | None:
    """Retrieve reconciliation state for a specific transaction."""
    db = get_client()
    if db is None:
        return _memory_match_state.get(str(transaction_id))
    doc = db.collection("match_state").document(str(transaction_id)).get()
    return doc.to_dict() if doc.exists else None


def set_match_state(transaction_id: str, status: str, **fields) -> None:
    """status: 'matched' | 'awaiting_reply' | 'resolved'"""
    txn_id_str = str(transaction_id)
    data = {"status": status, **fields}
    db = get_client()
    if db is None:
        if txn_id_str not in _memory_match_state:
            _memory_match_state[txn_id_str] = {}
        _memory_match_state[txn_id_str].update(data)
        return
    db.collection("match_state").document(txn_id_str).set(data, merge=True)


def mark_invoice_paid(invoice_id: str) -> None:
    """Mark an invoice as paid."""
    db = get_client()
    if db is None:
        if invoice_id in _memory_invoices:
            _memory_invoices[invoice_id]["status"] = "paid"
        return
    db.collection("invoices").document(invoice_id).update({"status": "paid"})


def find_pending_transaction_by_phone(phone_number: str) -> tuple[str, dict] | None:
    """Find the most recent transaction awaiting reply from a given customer phone number."""
    normalized_target = "".join(filter(str.isdigit, phone_number))
    db = get_client()
    if db is None:
        for txn_id, state in _memory_match_state.items():
            if state.get("status") == "awaiting_reply":
                stored_phone = state.get("customer_phone", "")
                norm_stored = "".join(filter(str.isdigit, str(stored_phone)))
                if norm_stored and (norm_stored.endswith(normalized_target) or normalized_target.endswith(norm_stored)):
                    return txn_id, state
        return None

    docs = db.collection("match_state").where("status", "==", "awaiting_reply").stream()
    for d in docs:
        state = d.to_dict()
        stored_phone = state.get("customer_phone", "")
        norm_stored = "".join(filter(str.isdigit, str(stored_phone)))
        if norm_stored and (norm_stored.endswith(normalized_target) or normalized_target.endswith(norm_stored)):
            return d.id, state
    return None


def resolve_transaction(transaction_id: str, invoice_id: str, resolved_by: str = "customer_reply") -> None:
    """Resolve an ambiguous transaction once confirmed, marking the invoice paid."""
    set_match_state(
        transaction_id,
        "resolved",
        invoice_id=invoice_id,
        resolved_by=resolved_by,
    )
    mark_invoice_paid(invoice_id)
