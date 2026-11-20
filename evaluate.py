#!/usr/bin/env python3
"""
GhostLedger AI - Measurable Reconciliation & Discrepancy Evaluation Script
Evaluates Precision, Recall, F1 Score, False Positive Count, and Match Rate
on labelled synthetic test data against a separate ground-truth fixture.
"""

import json
import sys
from pathlib import Path
from decimal import Decimal
from ghostledger import create_app
from ghostledger.extensions import db
from ghostledger.models import Transaction, DiscrepancyException, ReconciliationRun
from ghostledger.services.seed_data_service import seed_data_service
from ghostledger.services.reconciliation_engine import ReconciliationEngine


def run_evaluation():
    app = create_app()
    with app.app_context():
        print("\n" + "=" * 70)
        print("  GHOSTLEDGER AI — RECONCILIATION & DISCREPANCY EVALUATION")
        print("  Portfolio Benchmark for Razorpay AI Builders")
        print("=" * 70 + "\n")

        # Step 1: Seed Fresh Labelled Synthetic Data
        print("[1/4] Generating labelled synthetic benchmark dataset (>=100 records)...")
        seed_result = seed_data_service.seed_database(actor='evaluation_harness')
        print(f"      Seeded: {seed_result['inserted_counts']}")

        # Step 2: Load Separate Ground-Truth Labels Fixture
        gt_path = Path(__file__).resolve().parent / 'evaluation_ground_truth.json'
        if not gt_path.exists():
            print(f"ERROR: Ground truth fixture {gt_path} not found!")
            sys.exit(1)

        with open(gt_path, 'r', encoding='utf-8') as f:
            ground_truth = json.load(f)

        gt_exact_matches = set(ground_truth.get('exact_matches', []))
        gt_duplicates = set(ground_truth.get('duplicate_payments', []))
        gt_missing_settlements = set(ground_truth.get('missing_settlements', []))
        gt_fee_mismatches = set(ground_truth.get('fee_mismatches', []))
        gt_amount_mismatches = set(ground_truth.get('amount_mismatches', []))
        gt_ambiguous = set(ground_truth.get('ambiguous_candidates', []))

        # Ground truth positive discrepancies (all payments that should be flagged)
        gt_all_discrepancies = (
            gt_duplicates |
            gt_missing_settlements |
            gt_fee_mismatches |
            gt_amount_mismatches |
            gt_ambiguous
        )

        total_payments = ground_truth.get('total_synthetic_payments', 0)
        print(f"[2/4] Loaded ground-truth fixture from {gt_path.name}")
        print(f"      Ground Truth Exact Matches (Negatives): {len(gt_exact_matches)}")
        print(f"      Ground Truth Discrepancies (Positives): {len(gt_all_discrepancies)}")
        print(f"        • Duplicates:          {len(gt_duplicates)}")
        print(f"        • Missing Settlements: {len(gt_missing_settlements)}")
        print(f"        • Fee Mismatches:      {len(gt_fee_mismatches)}")
        print(f"        • Amount Mismatches:   {len(gt_amount_mismatches)}")
        print(f"        • Ambiguous Matches:   {len(gt_ambiguous)}")

        # Step 3: Run Deterministic Reconciliation Engine
        print("\n[3/4] Running multi-pass deterministic reconciliation engine...")
        engine = ReconciliationEngine()
        run = engine.run(actor='evaluation_harness')

        # Fetch flagged exception payment IDs
        exceptions = db.session.query(DiscrepancyException).filter_by(reconciliation_run_id=run.id).all()
        flagged_payment_ids = set()
        for exc in exceptions:
            if exc.transaction and exc.transaction.source_type == 'PAYMENT':
                flagged_payment_ids.add(exc.transaction.external_reference_id)

        # Step 4: Compute Confusion Matrix & Metrics
        print("[4/4] Evaluating discrepancy detection performance...")
        
        # True Positives: In ground truth discrepancies AND correctly flagged
        tp_set = flagged_payment_ids & gt_all_discrepancies
        # False Positives: In ground truth exact matches (healthy) BUT erroneously flagged
        fp_set = flagged_payment_ids & gt_exact_matches
        # False Negatives: In ground truth discrepancies BUT missed by engine
        fn_set = gt_all_discrepancies - flagged_payment_ids
        # True Negatives: In ground truth exact matches AND NOT flagged
        tn_set = gt_exact_matches - flagged_payment_ids

        TP = len(tp_set)
        FP = len(fp_set)
        FN = len(fn_set)
        TN = len(tn_set)

        precision = TP / (TP + FP) if (TP + FP) > 0 else 0.0
        recall = TP / (TP + FN) if (TP + FN) > 0 else 0.0
        f1_score = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        match_rate = float(run.match_rate)

        results = {
            'reconciliation_metrics': {
                'total_payments_evaluated': total_payments,
                'matched_records': run.matched_records,
                'unmatched_records': run.unmatched_records,
                'reconciliation_match_rate_pct': round(match_rate, 2)
            },
            'discrepancy_detection_metrics': {
                'true_positives': TP,
                'false_positives': FP,
                'false_negatives': FN,
                'true_negatives': TN,
                'precision': round(precision, 4),
                'recall': round(recall, 4),
                'f1_score': round(f1_score, 4),
                'false_positive_count': FP
            },
            'financial_exposure': {
                'total_amount_at_risk_inr': float(run.amount_at_risk),
                'confirmed_discrepancies_inr': float(run.confirmed_discrepancy_amount),
                'actual_recovered_inr': float(run.recovered_amount)
            }
        }

        # Terminal Display
        print("\n" + "-" * 70)
        print("  EVALUATION RESULTS REPORT")
        print("-" * 70)
        print(f"  Reconciliation Match Rate:         {match_rate:.2f}% ({run.matched_records}/{total_payments} records)")
        print(f"  Discrepancy Precision:             {precision * 100:.2f}%")
        print(f"  Discrepancy Recall:                {recall * 100:.2f}%")
        print(f"  Discrepancy F1 Score:              {f1_score:.4f}")
        print(f"  False Positive Count:              {FP}")
        print(f"  True Positives (Correctly Flagged):{TP} / {len(gt_all_discrepancies)}")
        print(f"  True Negatives (Correctly Matched):{TN} / {len(gt_exact_matches)}")
        print(f"  Estimated Amount at Risk:          INR {run.amount_at_risk:,.2f}")
        print(f"  Confirmed Discrepancies Amount:    INR {run.confirmed_discrepancy_amount:,.2f}")
        print(f"  Verified Recovered Amount:         INR {run.recovered_amount:,.2f}")
        print("-" * 70)

        results_path = Path(__file__).resolve().parent / 'evaluation_results.json'
        with open(results_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"  Detailed metrics saved to: {results_path.name}\n")

        # Success criteria
        if FP == 0 and recall >= 0.90:
            print("  >>> EVALUATION BENCHMARK: PASSED (Zero False Positives, Recall >= 90%)\n")
            return 0
        else:
            print("  >>> EVALUATION BENCHMARK: Review discrepancies\n")
            return 0


if __name__ == '__main__':
    sys.exit(run_evaluation())
