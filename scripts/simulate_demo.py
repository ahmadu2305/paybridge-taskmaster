#!/usr/bin/env python3
"""PayBridge End-to-End Demo & Simulation Script

Demonstrates the entire lifecycle:
1. Seeding outstanding invoices into the store.
2. Ingesting transactions with 3 scenarios:
   - Scenario A: Deterministic match (exact ID in reference).
   - Scenario B: Ambiguous match resolved with Gemini reasoning (customer name + email correlation).
   - Scenario C: Unmatched transaction triggering WhatsApp outreach.
3. Simulating customer WhatsApp reply via webhook to resolve Scenario C.
"""

import json
import os
import sys
from pathlib import Path

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Force in-memory mode for offline demo simulation
os.environ["USE_IN_MEMORY_STORE"] = "true"
os.environ["MATCH_CONFIDENCE_THRESHOLD"] = "0.85"

from src import agent, main, store


class MockPaystackClient:
    """Mock Paystack client returning 3 test transactions."""

    def fetch_recent_transactions(self, lookback_minutes: int = 1440) -> list[dict]:
        return [
            # Scenario A: Exact match (ID in reference)
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
            # Scenario B: Ambiguous (no invoice ID in reference, but matches customer name & email)
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
            # Scenario C: Unknown / Unmatched (payer name differs from invoice, reference is generic)
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


def seed_invoices():
    print("\n📦 Seeding Outstanding Invoices in Firestore / Store...")
    invoices = [
        {
            "id": "INV-101",
            "amount": 5000,
            "customer_name": "Amina Bello",
            "customer_email": "amina.bello@example.com",
            "description": "Monthly Cloud Subscription",
            "status": "outstanding"
        },
        {
            "id": "INV-102",
            "amount": 12500,
            "customer_name": "Chidi Okonkwo",
            "customer_email": "chidi.okonkwo@techcorp.ng",
            "description": "Custom API Integration Consulting",
            "status": "outstanding"
        },
        {
            "id": "INV-103",
            "amount": 8000,
            "customer_name": "Tunde Bakare",
            "customer_email": "tunde.bakare@enterprises.com",
            "customer_phone": "+2348033333333",
            "description": "Annual Maintenance Fee",
            "status": "outstanding"
        },
    ]
    for inv in invoices:
        store.save_invoice(inv["id"], inv)
        print(f"  ✓ Created Invoice: {inv['id']} | Amount: ₦{inv['amount']:,} | Customer: {inv['customer_name']}")


def run_simulation():
    print("=" * 70)
    print("🚀 PAYBRIDGE RECONCILIATION AGENT — FULL CYCLE DEMO")
    print("=" * 70)

    # 1. Seed
    seed_invoices()

    # 2. Run Reconciliation Cycle
    print("\n🤖 Running Agent Reconciliation Cycle...")
    mock_client = MockPaystackClient()
    summary = agent.run_reconciliation_cycle(client=mock_client)

    print("\n📊 Cycle Execution Summary:")
    print(json.dumps(summary, indent=2))

    # 3. Inspect Store States
    print("\n📋 Match State in Store:")
    for txn_id in ["txn_1001", "txn_1002", "txn_1003"]:
        state = store.get_match_state(txn_id)
        print(f"  • {txn_id}: {state}")

    # 4. Simulate Inbound WhatsApp Webhook
    print("\n💬 Simulating Customer WhatsApp Reply...")
    print("  Customer (+2348033333333) replies: 'Hi, I paid for invoice INV-103'")

    webhook_payload = {
        "From": "whatsapp:+2348033333333",
        "Body": "Hi, I paid for invoice INV-103"
    }
    response_body, status, _ = main.handle_whatsapp_webhook(webhook_payload)
    print(f"  Webhook Response (HTTP {status}): {response_body}")

    # 5. Final State Verification
    print("\n✅ Final State Verification:")
    final_state = store.get_match_state("txn_1003")
    final_invoice = store.get_invoice("INV-103")
    print(f"  • Transaction txn_1003 status: {final_state.get('status')} (Resolved by: {final_state.get('resolved_by')})")
    print(f"  • Invoice INV-103 status: {final_invoice.get('status')}")

    print("\n" + "=" * 70)
    print("🎉 DEMO SIMULATION COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_simulation()
