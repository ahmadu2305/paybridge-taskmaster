import json
import os
import sys
import unittest
from pathlib import Path

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["USE_IN_MEMORY_STORE"] = "true"
os.environ["MATCH_CONFIDENCE_THRESHOLD"] = "0.85"

from src import agent, main, store


class TestPayBridgeAgent(unittest.TestCase):

    def setUp(self):
        """Reset store state before each test."""
        store._memory_invoices.clear()
        store._memory_match_state.clear()

    def test_exact_match_major_units(self):
        txn = {"amount": 5000, "reference": "INV-123-ref"}
        invoices = [{"id": "INV-123", "amount": 5000}, {"id": "INV-999", "amount": 5000}]
        result = agent.match_transaction(txn, invoices)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "INV-123")

    def test_exact_match_kobo_units(self):
        # 5,000 NGN = 500,000 kobo
        txn = {"amount": 500000, "reference": "PAY-INV-123-ONLINE"}
        invoices = [{"id": "INV-123", "amount": 5000}]
        result = agent.match_transaction(txn, invoices)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "INV-123")

    def test_no_match_returns_none(self):
        txn = {"amount": 5000, "reference": "no-ref-here"}
        invoices = [{"id": "INV-123", "amount": 7000}]
        self.assertIsNone(agent.match_transaction(txn, invoices))

    def test_amount_mismatch_not_matched(self):
        txn = {"amount": 4999, "reference": "INV-123"}
        invoices = [{"id": "INV-123", "amount": 5000}]
        self.assertIsNone(agent.match_transaction(txn, invoices))

    def test_reason_ambiguous_match_success(self):
        """Test LLM reasoning when reference is missing but customer identity matches."""
        txn = {
            "id": "txn_201",
            "amount": 1000000,  # 10,000 NGN in kobo
            "reference": "NIP/TRANSFER/GENERIC_REF",
            "customer": {
                "first_name": "Bola",
                "last_name": "Ahmed",
                "email": "bola.ahmed@example.com"
            }
        }
        invoices = [
            {
                "id": "INV-401",
                "amount": 10000,
                "customer_name": "Bola Ahmed",
                "customer_email": "bola.ahmed@example.com",
                "status": "outstanding"
            }
        ]

        result = agent.reason_ambiguous_match(txn, invoices)
        self.assertEqual(result["matched_invoice_id"], "INV-401")
        self.assertGreaterEqual(result["confidence"], 0.85)

    def test_reason_ambiguous_match_low_confidence(self):
        """Test that ambiguous transactions with unknown payers return low confidence."""
        txn = {
            "id": "txn_202",
            "amount": 1000000,
            "reference": "UNKNOWN_POS_TRANSACTION",
            "customer": {
                "first_name": "Stranger",
                "last_name": "Person",
                "email": "stranger@unknown.com"
            }
        }
        invoices = [
            {
                "id": "INV-501",
                "amount": 10000,
                "customer_name": "Different Client",
                "customer_email": "different@company.com",
                "status": "outstanding"
            }
        ]

        result = agent.reason_ambiguous_match(txn, invoices)
        self.assertTrue(result["matched_invoice_id"] is None or result["confidence"] < 0.85)

    def test_invoice_id_parsing_from_text(self):
        self.assertEqual(main.parse_invoice_id_from_text("My invoice number is INV-102 thanks"), "INV-102")
        self.assertEqual(main.parse_invoice_id_from_text("Payment for #INV_990"), "INV_990")
        self.assertEqual(main.parse_invoice_id_from_text("Invoice: INV-456"), "INV-456")
        self.assertEqual(main.parse_invoice_id_from_text("inv123"), "INV123")

    def test_whatsapp_webhook_resolution(self):
        """Test resolving a pending transaction when customer replies via WhatsApp."""
        store.save_invoice("INV-777", {
            "id": "INV-777",
            "amount": 25000,
            "customer_name": "Kemi Adeleke",
            "status": "outstanding"
        })
        store.set_match_state(
            "txn_999",
            "awaiting_reply",
            customer_phone="+2348099999999",
            customer_name="Kemi",
            amount="25000"
        )

        webhook_payload = {
            "From": "whatsapp:+2348099999999",
            "Body": "Hello, I made payment for invoice INV-777"
        }

        body, status, _ = main.handle_whatsapp_webhook(webhook_payload)
        self.assertEqual(status, 200)
        res = json.loads(body)
        self.assertEqual(res["status"], "resolved")
        self.assertEqual(res["invoice_id"], "INV-777")

        # Verify store updates
        updated_txn = store.get_match_state("txn_999")
        self.assertEqual(updated_txn["status"], "resolved")
        self.assertEqual(updated_txn["invoice_id"], "INV-777")

        updated_inv = store.get_invoice("INV-777")
        self.assertEqual(updated_inv["status"], "paid")

    def test_full_reconciliation_cycle(self):
        """Test full cycle execution with mixed deterministic and ambiguous transactions."""
        store.save_invoice("INV-1", {"id": "INV-1", "amount": 5000, "customer_name": "User 1", "status": "outstanding"})
        store.save_invoice("INV-2", {"id": "INV-2", "amount": 10000, "customer_name": "User 2", "customer_email": "u2@test.com", "status": "outstanding"})
        store.save_invoice("INV-3", {"id": "INV-3", "amount": 15000, "customer_name": "User 3", "status": "outstanding"})

        class MockClient:
            def fetch_recent_transactions(self, lookback_minutes=1440):
                return [
                    {"id": "t1", "amount": 5000, "reference": "INV-1", "customer": {"phone": "+101"}},
                    {"id": "t2", "amount": 10000, "reference": "NO_REF", "customer": {"first_name": "User", "last_name": "2", "email": "u2@test.com", "phone": "+102"}},
                    {"id": "t3", "amount": 15000, "reference": "UNKNOWN", "customer": {"first_name": "Anon", "phone": "+103"}},
                ]

        summary = agent.run_reconciliation_cycle(client=MockClient())
        self.assertEqual(summary["total_processed"], 3)
        self.assertEqual(summary["matched_deterministic"], 1)
        self.assertEqual(summary["matched_by_agent"], 1)
        self.assertEqual(summary["followed_up"], 1)


if __name__ == "__main__":
    unittest.main()
