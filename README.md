# PayBridge Reconciliation Agent — Taskmaster Track

> **All Things Agentic Hackathon — Taskmaster Track**
> An autonomous, cost-optimized financial reconciliation agent that ingests Paystack transactions, matches them against invoices using **Gemini 3.5 via Vertex AI / Google ADK**, and executes an automated human-in-the-loop WhatsApp outreach loop to resolve unmatched payments.

---

## 💡 Inspiration

In 2023, I tried to book a flight for my mother from Lagos to Gombe. The payment went out — but then it just hung. Nobody could tell me where it was stuck: the merchant agent, PalmPay, Air Peace, or Fidelity Bank's PayGate all pointed elsewhere, and there was no single source of truth to check against. What should have taken minutes turned into hours of calls and follow-ups just to confirm whether money had actually moved.

That experience stuck with me. Multiply it across a business processing hundreds of transactions a day — customers paying via bank transfer, POS, or transfer apps with metadata that never quite matches an invoice — and you get finance teams spending their week doing exactly what I did that day: manually chasing down what happened to a payment. PayBridge is built so that chase happens automatically.

## 🎯 The Problem

In emerging markets (and payment gateways like Paystack), direct bank transfers and POS payments often lack clean invoice IDs in transaction metadata. Finance teams waste hours manually cross-referencing payer names, transaction timestamps, and partial email addresses, or messaging customers one by one on WhatsApp to verify what they paid for.

## 🏗️ Architecture

![PayBridge architecture — Cloud Scheduler triggers a Cloud Run agent that checks Paystack, Firestore, and Vertex AI, then escalates unresolved payments to Twilio WhatsApp]


<img width="647" height="311" alt="architecture" src="https://github.com/user-attachments/assets/0d650279-e809-493a-b19f-a35599fd85be" />


```
Cloud Scheduler (Periodic Cron) --------> Cloud Run (ADK / Gemini Agent)
                                              |--> Paystack API (Fetch Transactions)
                                              |--> Cloud Firestore (Invoices & State Ledger)
                                              |--> Vertex AI (Gemini 3.5 Reasoning)
                                              |--> Twilio API (Automated WhatsApp Outreach)
                                                      ^
Customer Replies on WhatsApp -------------------------| (Inbound Webhook: /webhook/whatsapp)
```

## 💡 The Solution: PayBridge 3-Tier Agent

PayBridge is an autonomous background taskmaster built on Google Cloud that resolves reconciliation bottlenecks:

1. **Tier 1: Fast Deterministic Pre-Filter (0 cost)**
   Instantly matches transactions with exact invoice reference matches without spending model tokens.
2. **Tier 2: Gemini 3.5 Flash Reasoning Engine**
   Analyzes ambiguous transactions (fuzzy customer names, mismatched domains, kobo/Naira unit discrepancies). Scores match confidence and extracts matching rationale.
3. **Tier 3: Autonomous WhatsApp Outreach & Two-Way Resolution**
   If confidence is below threshold (< 0.85), triggers an automated WhatsApp message to the customer asking for their invoice ID. When the customer replies, an inbound webhook parses the natural language reply, validates the invoice, marks the transaction resolved, and sends an immediate receipt confirmation.

<img width="622" height="831" alt="Paybridge Repository" src="https://github.com/user-attachments/assets/54b07a55-3453-4098-859a-741cba62e770" />

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
│   └── main.tf            # Terraform definition for Cloud Run, Firestore, & Scheduler
├── LICENSE
└── requirements.txt
```

---

## 🚀 Quickstart & Demo

### 1. Run the Full-Cycle Local Simulation (Zero Setup)

Demonstrates the entire lifecycle in under a second (Deterministic Match → Gemini AI reasoning → WhatsApp outreach → Customer reply resolution). Uses seeded/mock transaction data:

```
.venv/bin/python scripts/simulate_demo.py
```

### 2. Run Test Suite

```
.venv/bin/python -m unittest tests/test_agent.py
```

### 3. Test Live WhatsApp Notification to Your Phone

```
.venv/bin/python scripts/test_whatsapp.py [phone_number]
```

### 4. Run the Webhook Server Locally

```
.venv/bin/functions-framework --target=handle_request --port=8080 --source=src/main.py --debug
```

---

## ☁️ Deploying to Google Cloud

### Step 1: Deploy Cloud Run Service

```
gcloud run deploy paybridge-reconciler \
  --source . \
  --region us-central1 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,TWILIO_ACCOUNT_SID=$TWILIO_ACCOUNT_SID,TWILIO_AUTH_TOKEN=$TWILIO_AUTH_TOKEN,TWILIO_WHATSAPP_FROM=$TWILIO_WHATSAPP_FROM,TWILIO_CONTENT_SID=$TWILIO_CONTENT_SID \
  --allow-unauthenticated
```

### Step 2: Configure Twilio Inbound Webhook

In your Twilio Console, set the WhatsApp webhook to: `https://<YOUR-CLOUD-RUN-URL>/webhook/whatsapp` (HTTP POST).

### Step 3: Provision Infrastructure with Terraform

```
cd infra
terraform init
terraform apply -var="project_id=$GOOGLE_CLOUD_PROJECT" -var="container_image=gcr.io/$GOOGLE_CLOUD_PROJECT/paybridge-reconciler:latest"
```

---

## About

Autonomous financial reconciliation Taskmaster agent that matches Paystack transactions against invoices using Gemini 3.5 reasoning with automated WhatsApp human-in-the-loop resolution.
