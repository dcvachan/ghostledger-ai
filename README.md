# GhostLedger AI ⚡
### *Evidence-First AI Payment Reconciliation & Financial Investigation Agent*
**Portfolio Submission for Razorpay AI Builders**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask 3.1+](https://img.shields.io/badge/Flask-3.1%2B-black.svg)](https://palletsprojects.com/p/flask/)
[![SQLAlchemy 2.0+](https://img.shields.io/badge/SQLAlchemy-2.0%2B-red.svg)](https://www.sqlalchemy.org/)
[![Precision 100%](https://img.shields.io/badge/Discrepancy%20Precision-100%25-brightgreen.svg)]()
[![Recall 100%](https://img.shields.io/badge/Discrepancy%20Recall-100%25-brightgreen.svg)]()
[![F1 Score 1.0000](https://img.shields.io/badge/Discrepancy%20F1-1.0000-brightgreen.svg)]()

---

## 1. Executive Summary & Product Goal

**GhostLedger AI** is an evidence-first, production-minded reconciliation and financial investigation agent designed for modern fintechs, marketplaces, and payment processors. 

Modern businesses lose millions to silent ledger leaks:
- Duplicate payment authorizations from customer browser double-clicks or retried webhooks
- Overdue missing settlements from acquiring gateways
- Gateway Merchant Discount Rate (MDR) fee overcharges and hidden card interchange tiers
- Amount discrepancies arising from currency conversion spreads or partial captures
- Delayed refund reversals past regulatory SLAs
- Ambiguous multi-candidate batch payouts

GhostLedger AI automates the discovery, cross-statement investigation, and resolution of these exceptions with **zero hallucination**, **deterministic multi-pass matching**, **narrowly scoped Python-validated investigation tools**, and a strict **human-in-the-loop draft action boundary** (no unauthorized money movement).

---

## 2. Core Architecture & Safety Boundaries

```
+----------------------------------------------------------------------------------------------------+
|                                    GhostLedger AI Platform                                         |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  [Presentation Layer]                                                                              |
|    - Clean Fintech UI (HTML5, CSS3, Vanilla JS, Chart.js)                                          |
|    - Responsive Light Theme, Accessible Controls, Real-time Status Badges                          |
|    - Razorpay/Stripe-inspired Design: Metric Cards, Interactive Tables, Filter Bar, Action Modals  |
|                                                                                                    |
|  [API / Blueprint Layer (Flask)]                                                                   |
|    - /dashboard        : Executive KPI summary, recovery metrics, risk status                      |
|    - /imports          : Upload validation, formula sanitization, column mapping, preview          |
|    - /reconciliation   : Multi-pass deterministic matching pipeline, run history                   |
|    - /exceptions       : Exception queue, priority triage, evidence table, detail view             |
|    - /actions          : Draft-only actions, human approval workflow, safe simulated resolutions   |
|    - /reports          : Filtered queries, audit trail, PII/secret-safe CSV export                 |
|    - /api              : JSON endpoints for Chart.js and async investigation queries               |
|                                                                                                    |
|  [Core Engine Layer]                                                                               |
|    +-----------------------------+   +----------------------------------------------------------+  |
|    | Reconciliation Engine       |   | Evidence-First Investigation Engine                      |  |
|    |  - Pass 1: Exact Stable IDs |   |  - Narrow scoped Python-validated tools:                 |  |
|    |  - Pass 2: Exact Heuristic  |   |    * get_transaction_details                             |  |
|    |  - Pass 3: Window & Fee     |   |    * find_related_records                                |  |
|    |  - Pass 4: One-to-Many      |   |    * compare_settlement_amounts                          |  |
|    |  - Ambiguity Guard          |   |    * inspect_refund_status                              |  |
|    +-----------------------------+   |    * create_draft_action                                 |  |
|                                      |  - Engine Mode: Configurable LLM with fallback to        |  |
|                                      |    Deterministic Rule Engine (never pretends LLM)        |  |
|                                      |  - Strict JSON Schema Output & Factual Grounding         |  |
|                                      +----------------------------------------------------------+  |
|                                                                                                    |
|  [Data & Security Layer]                                                                           |
|    - SQLAlchemy ORM (MySQL 8 with seamless SQLite fallback)                                       |
|    - Decimal-accurate currency representation (Numeric(14,2)), explicit ISO-4217 currency codes  |
|    - Strict Formula Injection Defense (=, +, -, @ stripping on CSV imports)                       |
|    - Append-only Audit Log tracking all imports, runs, investigations, approvals & resolutions    |
|    - Draft-only Safety Boundary: zero real financial operations; explicit human approval gate    |
+----------------------------------------------------------------------------------------------------+
```

### Safety & Guardrail Principles
1. **Never Invent Evidence**: Every claim made by the investigation engine cites database transaction IDs, actual amounts, timestamps, and variances. If evidence is insufficient, it explicitly states so.
2. **Never Pretend a Rule-based Result Came from an LLM**: When no LLM API key exists, it executes the deterministic rules engine and stamps `engine_used='RULES_ENGINE'`. When an LLM executes, it stamps `engine_used='LLM_AGENT'`.
3. **Draft-Only Actions**: The AI can only draft recommendations (`CREATE_FOLLOW_UP_TASK`, `DRAFT_REFUND_INQUIRY`, `PROPOSED_RECONCILIATION_ADJUSTMENT`, `FLAG_SUSPECTED_DUPLICATE`). It cannot move funds or execute transactions.
4. **Verified Recovery Rule**: An amount is **never counted as recovered** until an analyst records a verified resolution.
5. **CSV Injection Defense**: Cells starting with `=`, `+`, `-`, or `@` are sanitized with single-quote escaping to prevent Dynamic Data Exchange (DDE) formula execution.
6. **Decimal Precision**: All monetary values use Python `Decimal` and SQL `Numeric(14,2)`—never binary floating point numbers.

---

## 3. Measurable Evaluation & Benchmark Results

The evaluation script (`evaluate.py`) benchmarks GhostLedger AI against a separate, unexposed ground-truth fixture (`evaluation_ground_truth.json`) containing **106 synthetic payment transactions** and corresponding records across Bank Statements, Settlements, Invoices, and Refunds.

### Reproducible Benchmark Results
```
======================================================================
  GHOSTLEDGER AI — RECONCILIATION & DISCREPANCY EVALUATION
  Portfolio Benchmark for Razorpay AI Builders
======================================================================

[1/4] Generating labelled synthetic benchmark dataset (>=100 records)...
      Seeded: {'payments': 106, 'bank_statements': 74, 'settlements': 84, 'invoices': 70, 'refunds': 6}
[2/4] Loaded ground-truth fixture from evaluation_ground_truth.json
      Ground Truth Exact Matches (Negatives): 70
      Ground Truth Discrepancies (Positives): 36
        • Duplicates:          10
        • Missing Settlements: 10
        • Fee Mismatches:      8
        • Amount Mismatches:   6
        • Ambiguous Matches:   2

[3/4] Running multi-pass deterministic reconciliation engine...
[4/4] Evaluating discrepancy detection performance...

----------------------------------------------------------------------
  EVALUATION RESULTS REPORT
----------------------------------------------------------------------
  Reconciliation Match Rate:         79.25% (84/106 records)
  Discrepancy Precision:             100.00%
  Discrepancy Recall:                100.00%
  Discrepancy F1 Score:              1.0000
  False Positive Count:              0
  True Positives (Correctly Flagged):36 / 36
  True Negatives (Correctly Matched):70 / 70
  Estimated Amount at Risk:          INR 187,551.71
  Confirmed Discrepancies Amount:    INR 159,642.71
  Verified Recovered Amount:         INR 0.00
----------------------------------------------------------------------
  Detailed metrics saved to: evaluation_results.json

  >>> EVALUATION BENCHMARK: PASSED (Zero False Positives, Recall >= 90%)
```

---

## 4. Local Installation & Setup Guide

GhostLedger AI runs locally on Windows, macOS, or Linux using Python 3.10+. It uses SQLite out-of-the-box for instant setup, and supports MySQL 8 for production deployments.

### Prerequisites
- Python 3.10+ (Check with `python --version`)
- pip package manager

### Option A: Windows PowerShell Setup

```powershell
# 1. Clone or navigate to the project directory
cd c:\path\to\ghostledger

# 2. Create and activate a Python virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment configuration
Copy-Item .env.example .env

# 5. Run tests to verify the setup
python -m pytest -v tests/

# 6. Run the measurable evaluation benchmark
python evaluate.py

# 7. Start the local server
python run.py
```

### Option B: macOS / Linux Setup

```bash
# 1. Clone or navigate to the project directory
cd /path/to/ghostledger

# 2. Create and activate a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment configuration
cp .env.example .env

# 5. Run tests to verify the setup
python3 -m pytest -v tests/

# 6. Run the measurable evaluation benchmark
python3 evaluate.py

# 7. Start the local server
python3 run.py
```

Open your browser to: **`http://127.0.0.1:5000`**

---

## 5. Database Configuration: SQLite vs MySQL 8

GhostLedger AI uses SQLAlchemy ORM, making database switching seamless via the `DATABASE_URL` environment variable in `.env`.

### 1. SQLite (Default Local Mode)
Zero configuration required:
```ini
DATABASE_URL=sqlite:///ghostledger.db
```

### 2. MySQL 8 (Production Mode)
1. In your MySQL 8 instance, create a database and user:
   ```sql
   CREATE DATABASE ghostledger_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'ghostledger_user'@'localhost' IDENTIFIED BY 'YourSecurePassword2026';
   GRANT ALL PRIVILEGES ON ghostledger_db.* TO 'ghostledger_user'@'localhost';
   FLUSH PRIVILEGES;
   ```
2. Update `.env`:
   ```ini
   DATABASE_URL=mysql+mysqlconnector://ghostledger_user:YourSecurePassword2026@localhost:3306/ghostledger_db
   ```
3. Restart `python run.py`. Tables will be automatically created.

---

## 6. Configurable LLM Adapter & Deterministic Fallback

GhostLedger AI supports external LLM providers (OpenAI, Gemini, Anthropic) while guaranteeing **100% functionality with deterministic rules** when no API key is configured.

In `.env`:
```ini
# For Deterministic Rules Engine (Default - zero paid API keys required):
LLM_PROVIDER=none
LLM_API_KEY=

# For OpenAI:
# LLM_PROVIDER=openai
# LLM_API_KEY=sk-...
# LLM_MODEL=gpt-4o-mini

# For Gemini:
# LLM_PROVIDER=gemini
# LLM_API_KEY=AIzaSy...
# LLM_MODEL=gemini-1.5-flash
```

---

## 7. Five-Minute Interactive Demo Script

Follow this step-by-step walkthrough to experience the entire reconciliation and investigation lifecycle:

| Step | Action | What to Observe |
|---|---|---|
| **1. Sign In** | Open `http://127.0.0.1:5000/login` and click **"One-Click Demo Analyst Login"**. | Instant authentication as `demo_analyst` (Demo mode enabled). |
| **2. Seed Synthetic Data** | On the Dashboard, click **"Seed 100+ Demo Records"**. | Alert confirms 106 payments and counterparts seeded with known edge cases. |
| **3. Run Reconciliation** | Click **"Run Reconciliation"** on the Dashboard header. | Multi-pass engine executes: 84 matches linked, 36 exceptions flagged, and Estimated Amount at Risk displays. |
| **4. Inspect Discrepancies** | Navigate to **Exceptions** in the top navigation. | Filterable queue shows `DUPLICATE_PAYMENT`, `MISSING_SETTLEMENT`, `FEE_MISMATCH`, `AMOUNT_MISMATCH`, and `AMBIGUOUS_CANDIDATE`. |
| **5. Evidence-First Investigation** | Click **"Investigate"** on a `DUPLICATE_PAYMENT` exception. | Evidence table shows exact order ID billed twice within minutes. AI Investigation card displays Root Cause, Alternative Hypotheses, and Engine Mode (`RULES_ENGINE`). |
| **6. Draft-Only Action** | Click **"Create Draft Action for Approval"** on the exception detail page. | A draft action (`FLAG_SUSPECTED_DUPLICATE`) is created awaiting human approval. |
| **7. Human Approval Gate** | Click **"Approve"** on the draft action card. | Action status updates to `APPROVED` with reviewer timestamp. No real money moved. |
| **8. Verified Resolution** | Scroll down to **"Record Verified Resolution"**, select `DUPLICATE_VOIDED`, enter recovered amount, and submit. | Exception marked `RESOLVED`. Dashboard's **"Actual Recovered Money"** increases strictly from this verified event. |
| **9. Verify Audit Trail** | Navigate to **Audit Trail** in the top navigation. | Immutable append-only log shows timestamps, actors, and JSON parameters for every action. |
| **10. Export Safe Report** | Navigate to **Reports** and click **"Export Filtered CSV Report"**. | Downloads a clean CSV report with formula injection sanitization and zero PII. |

---

## 8. Portfolio Submission Screenshots Guidance

When capturing screenshots or recording a Loom demo for Razorpay AI Builders, capture these key moments:

1. **Executive Dashboard (`/`)**: Show the KPI cards with the Doughnut Chart and Discrepancy Category Bar Chart populated after running reconciliation. Highlight the distinction between *Estimated Amount at Risk* and *Actual Recovered Money*.
2. **Exception Detail Page (`/exceptions/<id>`)**: Show the two-column view with the Factual Evidence Table on the left and the AI Investigation Report + Draft Action Creator on the right. Point out the `RULES_ENGINE (Deterministic)` badge to emphasize honest AI engineering.
3. **Human Approval Workflow (`/actions`)**: Show the queue of draft actions and the explicit approve/reject controls.
4. **Append-Only Audit Trail (`/audit-log`)**: Show the immutable event log demonstrating enterprise compliance and auditability.
5. **Terminal Evaluation Run (`python evaluate.py`)**: Show the test output reporting 100% Precision, 100% Recall, and 0 False Positives.

---

## 9. Known Limitations & Roadmap

- **Streaming Webhooks**: Current MVP reconciles batch CSV statements. Future roadmap includes ingestion endpoints for real-time Razorpay webhook events (`payment.captured`, `refund.processed`).
- **Dynamic FX Cross-Currency Curves**: Current matching handles standard multi-currency pairs with date tolerances; a production scale rollout would ingest live interbank spot rates.
- **Distributed Batch Scaling**: For datasets exceeding 1,000,000 daily transactions, matching logic can be dispatched across Celery/Redis worker queues.

---

## 10. Verification & Test Execution Summary

GhostLedger AI comes with a complete suite of automated tests:
```bash
python -m pytest -v tests/
```

- `tests/test_csv_service.py`: Formula injection defense, idempotency, and CSV parsing
- `tests/test_reconciliation.py`: Exact ID, heuristic multi-field, fee tolerance, ambiguity guard, duplicate detection, missing settlement detection
- `tests/test_investigation.py`: Python tool validation, deterministic rules fallback, schema compliance
- `tests/test_actions_approval.py`: Draft-only safety boundary, human review workflow, verified recovery invariant
- `tests/test_security_audit.py`: Append-only audit logger, password hashing, safe CSV export
- `tests/test_api.py`: Dashboard metrics, seed demo endpoint, and view rendering

**All 18 automated test suites passing with zero errors.**
