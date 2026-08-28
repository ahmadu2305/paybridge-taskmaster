# PayBridge Reconciliation Agent — Taskmaster Track

> **All Things Agentic Hackathon — Taskmaster Track**  
> An autonomous, cost-optimized financial reconciliation agent that ingests Paystack transactions, matches them against invoices using **Gemini 3.5 via Vertex AI / Google ADK**, and executes an automated human-in-the-loop WhatsApp outreach loop to resolve unmatched payments.

---

## 🎯 The Problem

In emerging markets (and payment gateways like Paystack), direct bank transfers and POS payments often lack clean invoice IDs in transaction metadata. Finance teams waste hours manually cross-referencing payer names, transaction timestamps, and partial email addresses, or messaging customers one by one on WhatsApp to verify what they paid for.

## 💡 The Solution: PayBridge 3-Tier Agent

PayBridge is an autonomous background taskmaster built on Google Cloud that resolves reconciliation bottlenecks:

1. **Tier 1: Fast Deterministic Pre-Filter (0 cost)**  
   Instantly matches transactions with exact invoice reference matches without spending model tokens.
2. **Tier 2: Gemini 3.5 Flash Reasoning Engine**  
   Analyzes ambiguous transactions (fuzzy customer names, mismatched domains, kobo/Naira unit discrepancies). Scores match confidence and extracts matching rationale.
3. **Tier 3: Autonomous WhatsApp Outreach & Two-Way Resolution**  
   If confidence is below threshold (< 0.85), triggers an automated WhatsApp message to the customer asking for their invoice ID. When the customer replies, an inbound webhook parses the natural language reply, validates the invoice, marks the transaction resolved, and sends an immediate receipt confirmation.

---

## 🏗️ Architecture

```
Cloud Scheduler (Periodic Cron) --------> Cloud Run (ADK / Gemini Agent)
                                              |--> Paystack API (Fetch Transactions)
                                              |--> Cloud Firestore (Invoices & State Ledger)
                                              |--> Vertex AI (Gemini 3.5 Reasoning)
                                              |--> Twilio API (Automated WhatsApp Outreach)
                                                      ^
Customer Replies on WhatsApp -------------------------| (Inbound Webhook: /webhook/whatsapp)
```

---

## 🛠️ Tech Stack

- **AI Reasoning**: Gemini 3.5 Flash via Google Vertex AI / Agent Development Kit (ADK) pattern
- **Cloud Infrastructure**: Google Cloud Run, Cloud Firestore (Native), Cloud Scheduler
- **Payment Gateway**: Paystack API (Kobo & Major currency unit normalization)
- **Messaging**: Twilio WhatsApp API (Content Templates & Interactive Webhook)
- **Infrastructure as Code**: Terraform (`infra/main.tf`)

---

## 📁 Project Structure

```
paybridge-taskmaster/
├── src/
│   ├── agent.py          # Deterministic pre-filter + Gemini reasoning agent
│   ├── main.py           # Cloud Run HTTP entrypoint & Twilio webhook router
│   ├── notify.py         # Twilio WhatsApp client (Content Templates + Fallback)
│   ├── paystack.py       # Paystack API client (Sandbox & Live)
│   └── store.py          # Firestore persistence with resilient in-memory fallback
├── scripts/
│   ├── simulate_demo.py  # End-to-end local simulation demo (3 scenarios)
│   └── test_whatsapp.py  # Standalone Twilio WhatsApp connectivity verification
├── tests/
│   └── test_agent.py     # Comprehensive unit test suite (9/9 passing)
├── infra/
│   └── main.tf           # Terraform definition for Cloud Run, Firestore, & Scheduler
└── requirements.txt
```

---

## 🚀 Quickstart & Demo

### 1. Run the Full-Cycle Local Simulation (Zero Setup)

Demonstrates the entire lifecycle in under a second (Deterministic Match $\to$ Gemini AI reasoning $\to$ WhatsApp outreach $\to$ Customer reply resolution):

```bash
.venv/bin/python scripts/simulate_demo.py
```

### 2. Run Test Suite

```bash
.venv/bin/python -m unittest tests/test_agent.py
```

### 3. Test Live WhatsApp Notification to Your Phone

```bash
.venv/bin/python scripts/test_whatsapp.py [phone_number]
```

### 4. Run the Webhook Server Locally

```bash
.venv/bin/functions-framework --target=handle_request --port=8080 --source=src/main.py --debug
```

---

## ☁️ Deploying to Google Cloud

### Step 1: Deploy Cloud Run Service

```bash
gcloud run deploy paybridge-reconciler \
  --source . \
  --region us-central1 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,TWILIO_ACCOUNT_SID=$TWILIO_ACCOUNT_SID,TWILIO_AUTH_TOKEN=$TWILIO_AUTH_TOKEN,TWILIO_WHATSAPP_FROM=$TWILIO_WHATSAPP_FROM,TWILIO_CONTENT_SID=$TWILIO_CONTENT_SID \
  --allow-unauthenticated
```

### Step 2: Configure Twilio Inbound Webhook

In your Twilio Console, set the WhatsApp webhook to:
`https://<YOUR-CLOUD-RUN-URL>/webhook/whatsapp` (HTTP POST).

### Step 3: Provision Infrastructure with Terraform

```bash
cd infra
terraform init
terraform apply -var="project_id=$GOOGLE_CLOUD_PROJECT" -var="container_image=gcr.io/$GOOGLE_CLOUD_PROJECT/paybridge-reconciler:latest"
```

---

## 🎬 2-Minute Demo Recording Walkthrough

When recording your video submission:

1. **Introduction (20s)**: Introduce the problem — lost time and unmatched transactions in payment gateways.
2. **Architecture & Strategy (30s)**: Explain the 3 tiers (Deterministic filter $\to$ Gemini 3.5 reasoning $\to$ WhatsApp customer loop).
3. **Live Execution (40s)**: Run `scripts/simulate_demo.py` in terminal. Point out:
   - `txn_1001`: Deterministic match.
   - `txn_1002`: Gemini matched Chidi Okonkwo based on customer correlation (94% confidence).
   - `txn_1003`: Unmatched POS payment triggered WhatsApp follow-up.
4. **Live WhatsApp Confirmation (30s)**: Show the WhatsApp message received on your phone (`test_whatsapp.py`) and explain how inbound replies automatically resolve the invoice!

