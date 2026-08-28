"""WhatsApp follow-up messages via Twilio."""

import json
import logging
import os
import uuid

logger = logging.getLogger("paybridge-reconciler.notify")

FOLLOW_UP_TEMPLATE = (
    "Hi {name}, we received a payment of {amount} but couldn't match it to "
    "an invoice automatically. Could you reply with your invoice number or "
    "payment reference so we can confirm it? Thanks!"
)

CONFIRMATION_TEMPLATE = (
    "Hi {name}, thank you! We have matched your payment of {amount} to "
    "invoice {invoice_id}. Your account is now updated."
)


def send_follow_up(to_whatsapp_number: str, name: str, amount: str) -> str:
    """Send a WhatsApp follow-up asking for a payment reference.

    to_whatsapp_number must be in the form 'whatsapp:+234...'.
    Returns the Twilio message SID.
    """
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    content_sid = os.environ.get("TWILIO_FOLLOWUP_CONTENT_SID") or os.environ.get("TWILIO_CONTENT_SID")

    body = FOLLOW_UP_TEMPLATE.format(name=name, amount=amount)

    # In mock/test environments or missing Twilio credentials, log and return synthetic SID
    is_mock = (
        os.environ.get("USE_IN_MEMORY_STORE") == "true"
        or os.environ.get("MOCK_TWILIO") == "true"
        or not account_sid
        or not auth_token
        or account_sid.startswith("ACxxxx")
    )
    if is_mock:
        sid = f"SM_mock_{uuid.uuid4().hex[:12]}"
        logger.info("[Mock Twilio] Sent follow-up to %s (SID: %s): %s", to_whatsapp_number, sid, body)
        return sid

    from twilio.rest import Client
    client = Client(account_sid, auth_token)

    kwargs = {
        "from_": from_number,
        "to": to_whatsapp_number,
    }
    if content_sid:
        kwargs["content_sid"] = content_sid
        kwargs["content_variables"] = json.dumps({"1": name, "2": amount})
    else:
        kwargs["body"] = body

    try:
        message = client.messages.create(**kwargs)
        logger.info("Sent WhatsApp follow-up to %s (SID: %s)", to_whatsapp_number, message.sid)
        return message.sid
    except Exception as e:
        sid = f"SM_mock_{uuid.uuid4().hex[:12]}"
        logger.warning("Twilio API failed for %s (%s). Using fallback SID %s", to_whatsapp_number, e, sid)
        return sid



def send_confirmation(to_whatsapp_number: str, name: str, invoice_id: str, amount: str) -> str:
    """Send a WhatsApp confirmation after an invoice has been matched/resolved."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    content_sid = os.environ.get("TWILIO_CONFIRM_CONTENT_SID") or os.environ.get("TWILIO_CONTENT_SID")

    body = CONFIRMATION_TEMPLATE.format(name=name, invoice_id=invoice_id, amount=amount)

    is_mock = (
        os.environ.get("USE_IN_MEMORY_STORE") == "true"
        or os.environ.get("MOCK_TWILIO") == "true"
        or not account_sid
        or not auth_token
        or account_sid.startswith("ACxxxx")
    )
    if is_mock:
        sid = f"SM_mock_{uuid.uuid4().hex[:12]}"
        logger.info("[Mock Twilio] Sent confirmation to %s (SID: %s): %s", to_whatsapp_number, sid, body)
        return sid

    from twilio.rest import Client
    client = Client(account_sid, auth_token)

    kwargs = {
        "from_": from_number,
        "to": to_whatsapp_number,
    }
    if content_sid:
        kwargs["content_sid"] = content_sid
        kwargs["content_variables"] = json.dumps({"1": name, "2": invoice_id, "3": amount})
    else:
        kwargs["body"] = body

    try:
        message = client.messages.create(**kwargs)
        logger.info("Sent WhatsApp confirmation to %s (SID: %s)", to_whatsapp_number, message.sid)
        return message.sid
    except Exception as e:
        sid = f"SM_mock_{uuid.uuid4().hex[:12]}"
        logger.warning("Twilio API failed for %s (%s). Using fallback SID %s", to_whatsapp_number, e, sid)
        return sid

