"""Thin client for pulling transactions from the Paystack sandbox/live API with mock fallback."""

import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("paybridge-reconciler.paystack")
PAYSTACK_BASE_URL = "https://api.paystack.co"


def get_mock_transactions() -> list[dict]:
    """Sample transactions for offline development & demo simulations."""
    return [
        {
            "id": "txn_1001",
            "amount": 500000,  # 5,000 NGN in kobo
            "reference": "PAY-REF-INV-101-ONLINE",
            "status": "success",
            "customer": {
                "first_name": "Amina",
                "last_name": "Bello",
                "email": "amina.bello@example.com",
                "phone": "+2348011111111"
            }
        },
        {
            "id": "txn_1002",
            "amount": 1250000,  # 12,500 NGN in kobo
            "reference": "NIP/TRF/GTB/CHIDI_OKONKWO_TRANS",
            "narration": "Transfer from Chidi Okonkwo for software services",
            "status": "success",
            "customer": {
                "first_name": "Chidi",
                "last_name": "Okonkwo",
                "email": "chidi.okonkwo@techcorp.ng",
                "phone": "+2348022222222"
            }
        },
        {
            "id": "txn_1003",
            "amount": 800000,  # 8,000 NGN in kobo
            "reference": "POS-TERMINAL-0049281",
            "narration": "POS Purchase at Victoria Island Branch",
            "status": "success",
            "customer": {
                "first_name": "Kelechi",
                "last_name": "ThirdParty",
                "email": "kelechi.unknown@gmail.com",
                "phone": "+2348033333333"
            }
        }
    ]


class PaystackClient:
    def __init__(self, secret_key: str | None = None):
        import requests
        self.secret_key = secret_key or os.environ.get("PAYSTACK_SECRET_KEY", "")
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {self.secret_key}"}
        )

    def fetch_recent_transactions(self, lookback_minutes: int = 1440) -> list[dict]:
        """Return successful transactions from the last `lookback_minutes`.

        Paystack's /transaction endpoint supports `from`/`to` ISO timestamps.
        Falls back to mock demo transactions if no valid key is configured or offline.
        """
        is_placeholder = not self.secret_key or "xxxx" in self.secret_key or self.secret_key.startswith("your_")
        force_mock = os.environ.get("USE_MOCK_PAYSTACK", "").lower() in ("1", "true", "yes")

        if force_mock or is_placeholder:
            logger.info("Using mock Paystack transactions (no live PAYSTACK_SECRET_KEY configured or USE_MOCK_PAYSTACK enabled).")
            return get_mock_transactions()

        try:
            since = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
            resp = self.session.get(
                f"{PAYSTACK_BASE_URL}/transaction",
                params={
                    "status": "success",
                    "from": since.isoformat(),
                    "perPage": 100,
                },
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception as e:
            logger.warning("Paystack API call failed (%s). Falling back to mock demo transactions.", e)
            return get_mock_transactions()

