"""One-off sanity check: confirm real Twilio credentials can send a WhatsApp
message through your Twilio WhatsApp sender and Content Templates.

Run:
    .venv/bin/python scripts/test_whatsapp.py
"""

import json
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

load_dotenv()

DEFAULT_PHONE_NUMBER = "2349130110901"


def main():
    target_phone = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PHONE_NUMBER
    clean_target = target_phone.lstrip("+")

    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+17372508034")
    content_sid = os.environ.get("TWILIO_CONTENT_SID", "HX8dc9eea84231541b091557c47cc2a342")

    if not account_sid or not auth_token:
        print("❌ Error: TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN is missing in your .env file.")
        sys.exit(1)

    print("=" * 65)
    print("📱 PayBridge Twilio WhatsApp Connectivity Test")
    print("=" * 65)
    print(f"Twilio Account SID : {account_sid[:8]}...{account_sid[-4:]}")
    print(f"From Number        : {from_number}")
    print(f"To WhatsApp Number : whatsapp:+{clean_target}")
    if content_sid:
        print(f"Content SID        : {content_sid}")
    print("-" * 65)

    client = Client(account_sid, auth_token)

    kwargs = {
        "from_": from_number,
        "to": f"whatsapp:+{clean_target}",
    }

    if content_sid:
        kwargs["content_sid"] = content_sid
    else:
        kwargs["body"] = "Test message from PayBridge reconciliation agent — if you got this, real Twilio sending works."

    try:
        message = client.messages.create(**kwargs)
        print(f"✅ Success! Message SID: {message.sid}")
        print("📲 Check your WhatsApp now — message has been dispatched!")
    except TwilioRestException as e:
        print(f"\n❌ Twilio API Error (HTTP {e.status}): {e.msg}")
        print(f"\nDetails: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()