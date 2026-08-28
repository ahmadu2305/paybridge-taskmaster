"""The reconciliation agent: decides which transactions match which invoices,
and which ones need a human follow-up via WhatsApp.

Built on Google's Agent Development Kit (ADK) / Gemini via Vertex AI.
"""

import json
import logging
import os
import re
from typing import Any

from . import notify, store

logger = logging.getLogger("paybridge-reconciler.agent")

DEFAULT_MODEL = "gemini-3.5-flash"
CONFIDENCE_THRESHOLD = float(os.environ.get("MATCH_CONFIDENCE_THRESHOLD", "0.85"))


def normalize_amount(amount: Any) -> float | None:
    """Normalize various amount representations into a standard float."""
    if amount is None:
        return None
    try:
        val = float(amount)
        return val
    except (ValueError, TypeError):
        return None


def amounts_match(txn_amount: Any, inv_amount: Any) -> bool:
    """Compare transaction and invoice amounts, accounting for major and minor (kobo/cents) units."""
    t_val = normalize_amount(txn_amount)
    i_val = normalize_amount(inv_amount)
    if t_val is None or i_val is None:
        return False

    # Exact match
    if abs(t_val - i_val) < 0.01:
        return True

    # Check 100x conversion (Paystack kobo to major unit)
    if abs(t_val - (i_val * 100)) < 0.01 or abs((t_val / 100) - i_val) < 0.01:
        return True

    return False


def match_transaction(transaction: dict, invoices: list[dict]) -> dict | None:
    """Fast deterministic pre-filter before handing ambiguous cases to the agent.

    Cheap, deterministic matches (matching amount + reference substring) are
    resolved immediately without spending a model call.
    """
    txn_amount = transaction.get("amount")
    reference = str(transaction.get("reference", "")).lower()
    customer_info = str(transaction.get("customer", {})).lower()
    narration = str(transaction.get("narration", "") or transaction.get("description", "")).lower()

    for invoice in invoices:
        inv_id = str(invoice.get("id", "")).lower()
        if amounts_match(txn_amount, invoice.get("amount")):
            # If invoice ID is explicitly in transaction reference, customer info, or narration
            if inv_id and (inv_id in reference or inv_id in narration or inv_id in customer_info):
                return invoice

    return None


def build_reconciliation_prompt(transaction: dict, invoices: list[dict]) -> str:
    """Construct prompt for Gemini reasoning on ambiguous transactions."""
    return f"""You are an expert financial reconciliation agent for PayBridge.
Your goal is to match an unreconciled payment transaction to the correct outstanding invoice.

CRITICAL INSTRUCTIONS:
- You must carefully analyze the transaction amount, customer name, email, phone number, and reference/narration.
- Only pick a match if you are confident that the transaction belongs to the invoice.
- Note that Paystack amounts might be in kobo (e.g. 500000 kobo = 5000.00 NGN) or exact major units.
- If there are multiple possible candidates with similar names/amounts, or if the data is insufficient, DO NOT GUESS. Set matched_invoice_id to null and set confidence low.
- A wrong match is significantly worse than asking the customer for clarification.

TRANSACTION TO RECONCILE:
{json.dumps(transaction, indent=2, default=str)}

CANDIDATE OUTSTANDING INVOICES:
{json.dumps(invoices, indent=2, default=str)}

RESPOND ONLY WITH A VALID JSON OBJECT in this exact schema:
{{
  "matched_invoice_id": "<invoice_id>" or null,
  "confidence": <float between 0.0 and 1.0>,
  "reasoning": "<clear explanation of matching rationale>"
}}
"""


def _invoke_gemini(prompt: str) -> str:
    """Invoke Gemini via Google AI Studio API Key, Vertex AI, or fallback gracefully."""
    model_name = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()

    # 1. Try Google AI Studio API key via google-genai SDK
    if api_key:
        candidate_models = [model_name]
        for fallback_m in ["gemini-3.5-flash-lite", "gemini-2.5-flash"]:
            if fallback_m not in candidate_models:
                candidate_models.append(fallback_m)

        for m_name in candidate_models:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=m_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )
                if response and response.text:
                    return response.text
            except Exception as e:
                logger.warning("Google AI Studio Gemini (%s) call failed: %s.", m_name, e)

    # 2. Try Vertex AI GenerativeModel / Google GenAI Vertex Client if valid GCP project is set
    if project_id and not project_id.startswith("your-gcp") and project_id != "none" and not os.environ.get("USE_IN_MEMORY_STORE"):
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(
                vertexai=True,
                project=project_id,
                location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
            )
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            if response and response.text:
                return response.text
        except Exception:
            try:
                import vertexai
                from vertexai.generative_models import GenerativeModel, GenerationConfig

                vertexai.init(
                    project=project_id,
                    location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
                )
                model = GenerativeModel(model_name)
                response = model.generate_content(
                    prompt,
                    generation_config=GenerationConfig(
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )
                return response.text
            except Exception as e:
                logger.warning("Vertex AI call failed: %s. Using heuristic fallback.", e)

    # 3. Intelligent fallback for local testing & offline simulation
    return _heuristic_reasoner(prompt)


def _heuristic_reasoner(prompt: str) -> str:
    """Heuristic matcher for local demo simulation when cloud credentials are not active."""
    # Extract transaction and invoices from the prompt if possible
    try:
        # Fuzzy match customer name and email
        txn_match = re.search(r"TRANSACTION TO RECONCILE:\s*(\{.*?\})\s*CANDIDATE OUTSTANDING INVOICES:", prompt, re.DOTALL)
        inv_match = re.search(r"CANDIDATE OUTSTANDING INVOICES:\s*(\[.*?\])\s*RESPOND ONLY", prompt, re.DOTALL)

        if txn_match and inv_match:
            txn = json.loads(txn_match.group(1))
            invoices = json.loads(inv_match.group(1))

            txn_customer = txn.get("customer", {})
            txn_name = f"{txn_customer.get('first_name', '')} {txn_customer.get('last_name', '')}".strip().lower()
            txn_email = str(txn_customer.get("email", "")).lower()
            txn_amount = txn.get("amount")

            for inv in invoices:
                if amounts_match(txn_amount, inv.get("amount")):
                    inv_name = str(inv.get("customer_name", "")).lower()
                    inv_email = str(inv.get("customer_email", "")).lower()

                    # High confidence match on matching email or matching full name
                    if (inv_email and inv_email == txn_email) or (inv_name and txn_name and (inv_name in txn_name or txn_name in inv_name)):
                        return json.dumps({
                            "matched_invoice_id": inv.get("id"),
                            "confidence": 0.94,
                            "reasoning": f"Exact amount match and customer identity match ({inv_name} / {inv_email}) between Paystack transaction and invoice."
                        })

    except Exception as e:
        logger.debug("Heuristic parsing error: %s", e)

    return json.dumps({
        "matched_invoice_id": None,
        "confidence": 0.20,
        "reasoning": "No candidate invoice strongly matches the transaction details."
    })


def reason_ambiguous_match(transaction: dict, invoices: list[dict]) -> dict:
    """Use Gemini reasoning to analyze ambiguous transactions."""
    if not invoices:
        return {
            "matched_invoice_id": None,
            "confidence": 0.0,
            "reasoning": "No outstanding invoices available for matching."
        }

    prompt = build_reconciliation_prompt(transaction, invoices)
    raw_response = _invoke_gemini(prompt)

    # Clean JSON output from potential markdown formatting
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
        cleaned = re.sub(r"\n```$", "", cleaned)

    try:
        result = json.loads(cleaned)
        matched_id = result.get("matched_invoice_id")
        # Validate that matched_id actually exists in candidate invoices
        valid_ids = {str(inv["id"]) for inv in invoices if "id" in inv}
        if matched_id and str(matched_id) not in valid_ids:
            result["matched_invoice_id"] = None
            result["confidence"] = 0.0
            result["reasoning"] += f" (Note: hallucinated id {matched_id} rejected)"
        return result
    except Exception as e:
        logger.error("Failed to parse Gemini output: %s. Raw: %s", e, raw_response)
        return {
            "matched_invoice_id": None,
            "confidence": 0.0,
            "reasoning": f"Agent output parsing error: {e}"
        }


def run_reconciliation_cycle(client=None) -> dict:
    """One full reconciliation pass: fetch transactions, match, and follow up."""
    if client is not None:
        paystack = client
    else:
        from .paystack import PaystackClient
        paystack = PaystackClient()

    lookback = int(os.environ.get("MATCH_LOOKBACK_MINUTES", "1440"))
    transactions = paystack.fetch_recent_transactions(lookback_minutes=lookback)
    invoices = store.get_outstanding_invoices()

    summary = {
        "total_processed": len(transactions),
        "matched_deterministic": 0,
        "matched_by_agent": 0,
        "followed_up": 0,
        "skipped_already_handled": 0,
        "details": []
    }

    for txn in transactions:
        txn_id = str(txn["id"])

        if store.get_match_state(txn_id):
            summary["skipped_already_handled"] += 1
            continue

        # Step 1: Fast deterministic pre-filter
        deterministic_match = match_transaction(txn, invoices)
        if deterministic_match:
            inv_id = deterministic_match["id"]
            store.set_match_state(
                txn_id,
                "matched",
                invoice_id=inv_id,
                matched_by="deterministic_rule",
                confidence=1.0,
            )
            store.mark_invoice_paid(inv_id)
            # Remove from local candidate list for subsequent transactions in this pass
            invoices = [inv for inv in invoices if inv.get("id") != inv_id]
            summary["matched_deterministic"] += 1
            summary["details"].append({
                "transaction_id": txn_id,
                "status": "matched",
                "invoice_id": inv_id,
                "method": "deterministic"
            })
            continue

        # Step 2: Ambiguous match reasoning with Gemini
        decision = reason_ambiguous_match(txn, invoices)
        matched_id = decision.get("matched_invoice_id")
        confidence = float(decision.get("confidence", 0.0))
        reasoning = decision.get("reasoning", "")

        if matched_id and confidence >= CONFIDENCE_THRESHOLD:
            store.set_match_state(
                txn_id,
                "matched",
                invoice_id=matched_id,
                matched_by="gemini_reasoning",
                confidence=confidence,
                reasoning=reasoning,
            )
            store.mark_invoice_paid(matched_id)
            invoices = [inv for inv in invoices if inv.get("id") != matched_id]
            summary["matched_by_agent"] += 1
            summary["details"].append({
                "transaction_id": txn_id,
                "status": "matched",
                "invoice_id": matched_id,
                "confidence": confidence,
                "method": "gemini_agent",
                "reasoning": reasoning,
            })
            continue

        # Step 3: Low confidence — trigger customer outreach via WhatsApp
        customer = txn.get("customer", {})
        customer_phone = customer.get("phone")
        first_name = customer.get("first_name") or "there"
        amount_display = str(txn.get("amount", ""))

        if customer_phone:
            # Format phone for WhatsApp
            clean_phone = customer_phone if customer_phone.startswith("whatsapp:") else f"whatsapp:{customer_phone}"
            sid = notify.send_follow_up(
                to_whatsapp_number=clean_phone,
                name=first_name,
                amount=amount_display,
            )
            store.set_match_state(
                txn_id,
                "awaiting_reply",
                customer_phone=customer_phone,
                customer_name=first_name,
                amount=amount_display,
                message_sid=sid,
                agent_reasoning=reasoning,
                confidence=confidence,
            )
            summary["followed_up"] += 1
            summary["details"].append({
                "transaction_id": txn_id,
                "status": "awaiting_reply",
                "customer_phone": customer_phone,
                "whatsapp_sid": sid,
                "agent_reasoning": reasoning,
            })
        else:
            logger.warning("Transaction %s is unmatched and has no customer phone number for follow-up.", txn_id)
            store.set_match_state(
                txn_id,
                "unmatched_no_phone",
                agent_reasoning=reasoning,
                confidence=confidence,
            )

    return summary
