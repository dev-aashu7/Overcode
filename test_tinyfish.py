"""
test_tinyfish.py
----------------
Comprehensive local evaluation & verification suite for MedVerify (Team Nexora — HackIIITD 2026).

Tests all 6 product-logic & safety requirements using 0 TinyFish credits (--check):
1. Input, Localhost & Authorized Portal Domain Guardrails:
   - Blank inputs (INVALID_INPUT), missing scheme (INVALID_URL), localhost (INVALID_URL),
     and unauthorized external domains (UNAUTHORIZED_PORTAL) are blocked before calling the SDK.
2. Active Policies & End-to-End Workflow (POL-100245, POL-205118, POL-309872):
   - Verifies policy extraction, pre-authorization form staging (diagnosis, estimated_cost,
     room_category), sample_clinical_document.pdf upload, and halting at 'Review & Verify'.
3. Lapsed & Unknown Policies (POL-999001, POL-999999):
   - Lapsed policy stops at 'Policy Details' (run_status = POLICY_LAPSED, success = False).
   - Unknown policy stops at 'Policy Search' (run_status = NOT_FOUND, success = False).
4. Independent Policy Extraction & Staged Field Mismatch Detection (FIELD_MISMATCH):
   - Wrong extracted room-rent limit or co-pay percentage vs AUTHORITATIVE_PORTAL_FIXTURES
     is flagged as FIELD_MISMATCH (success = False) without overwriting raw values.
   - Wrong staged diagnosis, estimated cost, or room category on the Review & Verify screen
     vs submitted case inputs is flagged as FIELD_MISMATCH (success = False).
5. Login / CAPTCHA / Access Restrictions, Timeouts & Incomplete Workflows:
   - access_or_auth_blocked = True -> ACCESS_OR_AUTH_BLOCKED (success = False).
   - SDK timeout exception -> TIMEOUT (success = False, manual_fallback_url provided).
   - stopped_at_review = False or missing document -> INCOMPLETE_WORKFLOW (success = False).
   - submitted_or_receipt_visible = True -> SUBMISSION_VIOLATION (success = False).
6. 20-Run Synthetic Reproducibility Harness:
   - 20 mocked runs across the test suite verifying 0 auto-submissions and 100% schema consistency.
"""

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tinyfish import RunStatus
from tinyfish_client import DEFAULT_PORTAL_URL, verify_policy


MOCK_PORTAL_RESPONSES = {
    "POL-100245": {
        "policy_found": True,
        "patient_name": "Rahul Sharma",
        "insurer_name": "CareShield General Insurance — Optima Health Platinum Individual",
        "policy_status": "Active",
        "room_rent_limit": "₹5,000 / day (Single Standard AC Room)",
        "copay_percentage": "0% (Nil)",
        "fields_prepared": [
            "hospital_name",
            "doctor_name",
            "diagnosis",
            "admission_date",
            "estimated_cost",
            "room_category",
            "sample_clinical_document.pdf",
        ],
        "document_uploaded": "sample_clinical_document.pdf",
        "current_portal_step": "Review & Verify",
        "staged_diagnosis": "Acute Cholecystitis / ICD-10 K81.0",
        "staged_estimated_cost": "₹85,000",
        "staged_room_category": "Semi-Private",
        "stopped_at_review": True,
        "submitted_or_receipt_visible": False,
        "access_or_auth_blocked": False,
        "notes": (
            "Verified Active policy for Rahul Sharma, filled Pre-Authorization Form, "
            "selected Use Sample Document (sample_clinical_document.pdf), navigated to "
            "Review & Verify, and stopped without clicking Submit Pre-Authorization."
        ),
    },
    "POL-205118": {
        "policy_found": True,
        "patient_name": "Sunita Verma",
        "insurer_name": "Heritage Life & Health Assurance — Senior Citizen Comprehensive Health",
        "policy_status": "Active",
        "room_rent_limit": "Single Private AC Room (up to 1% of Sum Insured)",
        "copay_percentage": "10% Co-Pay applicable on total admitted claim amount",
        "fields_prepared": [
            "hospital_name",
            "doctor_name",
            "diagnosis",
            "admission_date",
            "estimated_cost",
            "room_category",
            "sample_clinical_document.pdf",
        ],
        "document_uploaded": "sample_clinical_document.pdf",
        "current_portal_step": "Review & Verify",
        "staged_diagnosis": "Acute Cholecystitis / ICD-10 K81.0",
        "staged_estimated_cost": "₹85,000",
        "staged_room_category": "Semi-Private",
        "stopped_at_review": True,
        "submitted_or_receipt_visible": False,
        "access_or_auth_blocked": False,
        "notes": (
            "Verified Active policy for Sunita Verma, filled Pre-Authorization Form, "
            "attached sample_clinical_document.pdf, and stopped at Review & Verify."
        ),
    },
    "POL-309872": {
        "policy_found": True,
        "patient_name": "Priya Nair",
        "insurer_name": "Universal Alliance Health — Corporate Group Mediclaim (GMC)",
        "policy_status": "Active",
        "room_rent_limit": "No Capping / Actuals (Any category up to Deluxe)",
        "copay_percentage": "0% (Waived under Corporate GMC)",
        "fields_prepared": [
            "hospital_name",
            "doctor_name",
            "diagnosis",
            "admission_date",
            "estimated_cost",
            "room_category",
            "sample_clinical_document.pdf",
        ],
        "document_uploaded": "sample_clinical_document.pdf",
        "current_portal_step": "Review & Verify",
        "staged_diagnosis": "Acute Cholecystitis / ICD-10 K81.0",
        "staged_estimated_cost": "₹85,000",
        "staged_room_category": "Semi-Private",
        "stopped_at_review": True,
        "submitted_or_receipt_visible": False,
        "access_or_auth_blocked": False,
        "notes": (
            "Verified Active corporate GMC policy for Priya Nair, staged form and "
            "sample clinical document, and stopped at Review & Verify."
        ),
    },
    "POL-999001": {
        "policy_found": True,
        "patient_name": "Vikram Malhotra",
        "insurer_name": "SecureLife Mediclaim Co. — Basic Hospitalization Floater",
        "policy_status": "Lapsed",
        "room_rent_limit": "₹3,000 / day",
        "copay_percentage": "20%",
        "fields_prepared": [],
        "document_uploaded": None,
        "current_portal_step": "Policy Details",
        "staged_diagnosis": None,
        "staged_estimated_cost": None,
        "staged_room_category": None,
        "stopped_at_review": False,
        "submitted_or_receipt_visible": False,
        "access_or_auth_blocked": False,
        "notes": (
            "Policy POL-999001 for Vikram Malhotra has status Lapsed (expired 2024-12-31). "
            "Pre-Authorization button is disabled; workflow stopped at Policy Details."
        ),
    },
    "POL-999999": {
        "policy_found": False,
        "patient_name": None,
        "insurer_name": None,
        "policy_status": "Not Found",
        "room_rent_limit": None,
        "copay_percentage": None,
        "fields_prepared": [],
        "document_uploaded": None,
        "current_portal_step": "Policy Search",
        "staged_diagnosis": None,
        "staged_estimated_cost": None,
        "staged_room_category": None,
        "stopped_at_review": False,
        "submitted_or_receipt_visible": False,
        "access_or_auth_blocked": False,
        "notes": "Policy ID 'POL-999999' not found in TPA records.",
    },
}


def run_local_checks() -> None:
    """Verify guardrails, policy/form cross-checks, access failures, and reproducibility (0 credits)."""
    print("=== MedVerify Product Logic & End-to-End Verification Suite (0 Credits Used) ===\n")

    guardrail_cases = [
        (
            "1. Blank portal_url rejected",
            {
                "policy_id": "POL-100245",
                "diagnosis": "Acute Cholecystitis / ICD-10 K81.0",
                "estimated_cost": 85000,
                "portal_url": "",
            },
            "INVALID_INPUT",
        ),
        (
            "2. Missing http/https scheme rejected",
            {
                "policy_id": "POL-100245",
                "diagnosis": "Acute Cholecystitis / ICD-10 K81.0",
                "estimated_cost": 85000,
                "portal_url": "medverify-tpa-portal.vercel.app",
            },
            "INVALID_URL",
        ),
        (
            "3. Unreachable localhost URL blocked",
            {
                "policy_id": "POL-100245",
                "diagnosis": "Acute Cholecystitis / ICD-10 K81.0",
                "estimated_cost": 85000,
                "portal_url": "http://localhost:8000",
            },
            "INVALID_URL",
        ),
        (
            "4. Unauthorized external portal domain blocked",
            {
                "policy_id": "POL-100245",
                "diagnosis": "Acute Cholecystitis / ICD-10 K81.0",
                "estimated_cost": 85000,
                "portal_url": "https://unapproved-insurer-portal.example.com/",
            },
            "UNAUTHORIZED_PORTAL",
        ),
    ]

    all_passed = True
    for title, kwargs, expected_status in guardrail_cases:
        res = verify_policy(**kwargs)
        actual_status = res.get("run_status")
        passed = (
            res.get("success") is False
            and actual_status == expected_status
            and res.get("policy_status") is None
            and res.get("submitted") is False
        )
        all_passed = all_passed and passed
        print(f"[{'PASS' if passed else 'FAIL'}] {title}")
        print(f"       run_status: {actual_status} | error: {res.get('error')}\n")

    policy_test_cases = [
        ("5. Confirmed Active Policy POL-100245 (Rahul Sharma)", "POL-100245", True, "COMPLETED", True),
        ("6. Confirmed Active Policy POL-205118 (Sunita Verma)", "POL-205118", True, "COMPLETED", True),
        ("7. Confirmed Active Policy POL-309872 (Priya Nair)", "POL-309872", True, "COMPLETED", True),
        ("8. Confirmed Lapsed Policy POL-999001 (Vikram Malhotra) — Halts at Policy Details", "POL-999001", False, "POLICY_LAPSED", False),
        ("9. Unknown Policy ID POL-999999 — Halts at Policy Search", "POL-999999", False, "NOT_FOUND", False),
    ]

    with patch.dict(os.environ, {"TINYFISH_API_KEY": "mock-test-key-0-credits"}):
        for title, pid, expected_success, expected_run_status, expected_stopped in policy_test_cases:
            mock_payload = MOCK_PORTAL_RESPONSES[pid]
            fake_run = SimpleNamespace(status=RunStatus.COMPLETED, result=mock_payload)

            with patch("tinyfish_client.TinyFish") as mock_tf_cls:
                mock_tf_cls.return_value.agent.run.return_value = fake_run
                res = verify_policy(
                    policy_id=pid,
                    diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                    estimated_cost=85000,
                    room_category="Semi-Private",
                    portal_url=DEFAULT_PORTAL_URL,
                )

            acc_verified = (res.get("field_accuracy") or {}).get("verified") is True
            passed = (
                res.get("success") is expected_success
                and res.get("run_status") == expected_run_status
                and res.get("stopped_at_review") is expected_stopped
                and res.get("submitted") is False
                and acc_verified
            )
            all_passed = all_passed and passed
            print(f"[{'PASS' if passed else 'FAIL'}] {title}")
            print(
                f"       success: {res.get('success')} | run_status: {res.get('run_status')} | "
                f"policy_status: {res.get('policy_status')} | stopped_at_review: {res.get('stopped_at_review')} | "
                f"field_accuracy.verified: {acc_verified}\n"
            )

        # Test 10: Policy Extraction Mismatch (wrong room_rent_limit vs authoritative fixture)
        bad_policy_payload = dict(
            MOCK_PORTAL_RESPONSES["POL-100245"],
            room_rent_limit="₹99,000 / day (Wrong Extracted Value)",
        )
        fake_bad_pol_run = SimpleNamespace(status=RunStatus.COMPLETED, result=bad_policy_payload)
        with patch("tinyfish_client.TinyFish") as mock_tf_cls:
            mock_tf_cls.return_value.agent.run.return_value = fake_bad_pol_run
            bad_pol_res = verify_policy(
                policy_id="POL-100245",
                diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                estimated_cost=85000,
                room_category="Semi-Private",
                portal_url=DEFAULT_PORTAL_URL,
            )
        pol_mismatch_passed = (
            bad_pol_res.get("success") is False
            and bad_pol_res.get("run_status") == "FIELD_MISMATCH"
            and bad_pol_res.get("room_rent_limit") == "₹99,000 / day (Wrong Extracted Value)"
            and (bad_pol_res.get("field_accuracy") or {}).get("verified") is False
        )
        all_passed = all_passed and pol_mismatch_passed
        print(f"[{'PASS' if pol_mismatch_passed else 'FAIL'}] 10. Policy Extraction Mismatch (room_rent_limit) rejected without overwriting raw value")
        print(f"       success: {bad_pol_res.get('success')} | run_status: {bad_pol_res.get('run_status')} | error: {bad_pol_res.get('error')}\n")

        # Test 11: Staged Form Field Mismatch (staged_estimated_cost differs from submitted case input)
        bad_form_payload = dict(
            MOCK_PORTAL_RESPONSES["POL-100245"],
            staged_estimated_cost="₹12,000",
        )
        fake_bad_form_run = SimpleNamespace(status=RunStatus.COMPLETED, result=bad_form_payload)
        with patch("tinyfish_client.TinyFish") as mock_tf_cls:
            mock_tf_cls.return_value.agent.run.return_value = fake_bad_form_run
            bad_form_res = verify_policy(
                policy_id="POL-100245",
                diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                estimated_cost=85000,
                room_category="Semi-Private",
                portal_url=DEFAULT_PORTAL_URL,
            )
        form_mismatch_passed = (
            bad_form_res.get("success") is False
            and bad_form_res.get("run_status") == "FIELD_MISMATCH"
            and bad_form_res.get("staged_estimated_cost") == "₹12,000"
            and (bad_form_res.get("field_accuracy") or {}).get("verified") is False
        )
        all_passed = all_passed and form_mismatch_passed
        print(f"[{'PASS' if form_mismatch_passed else 'FAIL'}] 11. Staged Form Field Mismatch (staged_estimated_cost != input) rejected")
        print(f"       success: {bad_form_res.get('success')} | run_status: {bad_form_res.get('run_status')} | error: {bad_form_res.get('error')}\n")

        # Test 12: Incomplete workflow (stopped_at_review=False or missing document) rejected
        incomplete_payload = dict(MOCK_PORTAL_RESPONSES["POL-100245"], stopped_at_review=False)
        fake_incomplete_run = SimpleNamespace(status=RunStatus.COMPLETED, result=incomplete_payload)
        with patch("tinyfish_client.TinyFish") as mock_tf_cls:
            mock_tf_cls.return_value.agent.run.return_value = fake_incomplete_run
            inc_res = verify_policy(
                policy_id="POL-100245",
                diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                estimated_cost=85000,
                portal_url=DEFAULT_PORTAL_URL,
            )
        inc_passed = (
            inc_res.get("success") is False
            and inc_res.get("run_status") == "INCOMPLETE_WORKFLOW"
            and inc_res.get("submitted") is False
        )
        all_passed = all_passed and inc_passed
        print(f"[{'PASS' if inc_passed else 'FAIL'}] 12. Incomplete Workflow (stopped_at_review=False) rejected")
        print(f"       success: {inc_res.get('success')} | run_status: {inc_res.get('run_status')}\n")

        # Test 13: Login / CAPTCHA / Access Restriction Detected (ACCESS_OR_AUTH_BLOCKED)
        auth_blocked_payload = dict(
            MOCK_PORTAL_RESPONSES["POL-100245"],
            policy_found=False,
            access_or_auth_blocked=True,
            notes="Portal displayed a login required / CAPTCHA screen.",
        )
        fake_auth_run = SimpleNamespace(status=RunStatus.COMPLETED, result=auth_blocked_payload)
        with patch("tinyfish_client.TinyFish") as mock_tf_cls:
            mock_tf_cls.return_value.agent.run.return_value = fake_auth_run
            auth_res = verify_policy(
                policy_id="POL-100245",
                diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                estimated_cost=85000,
                portal_url=DEFAULT_PORTAL_URL,
            )
        auth_passed = (
            auth_res.get("success") is False
            and auth_res.get("run_status") == "ACCESS_OR_AUTH_BLOCKED"
            and auth_res.get("manual_fallback_url") == DEFAULT_PORTAL_URL
        )
        all_passed = all_passed and auth_passed
        print(f"[{'PASS' if auth_passed else 'FAIL'}] 13. Login / CAPTCHA / Access Barrier Detected (ACCESS_OR_AUTH_BLOCKED)")
        print(f"       success: {auth_res.get('success')} | run_status: {auth_res.get('run_status')}\n")

        # Test 14: Timeout Exception Handling (TIMEOUT + manual fallback URL)
        with patch("tinyfish_client.TinyFish") as mock_tf_cls:
            mock_tf_cls.return_value.agent.run.side_effect = TimeoutError("Browser navigation timed out after 90s")
            timeout_res = verify_policy(
                policy_id="POL-100245",
                diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                estimated_cost=85000,
                portal_url=DEFAULT_PORTAL_URL,
            )
        timeout_passed = (
            timeout_res.get("success") is False
            and timeout_res.get("run_status") == "TIMEOUT"
            and timeout_res.get("manual_fallback_url") == DEFAULT_PORTAL_URL
        )
        all_passed = all_passed and timeout_passed
        print(f"[{'PASS' if timeout_passed else 'FAIL'}] 14. Timeout Exception Handled Safely (TIMEOUT + manual_fallback_url)")
        print(f"       success: {timeout_res.get('success')} | run_status: {timeout_res.get('run_status')}\n")

        # Test 15: Auto-Submission Safety Violation Gate (SUBMISSION_VIOLATION)
        violation_payload = dict(MOCK_PORTAL_RESPONSES["POL-100245"], submitted_or_receipt_visible=True)
        fake_violation_run = SimpleNamespace(status=RunStatus.COMPLETED, result=violation_payload)
        with patch("tinyfish_client.TinyFish") as mock_tf_cls:
            mock_tf_cls.return_value.agent.run.return_value = fake_violation_run
            viol_res = verify_policy(
                policy_id="POL-100245",
                diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                estimated_cost=85000,
                portal_url=DEFAULT_PORTAL_URL,
            )
        viol_passed = (
            viol_res.get("success") is False
            and viol_res.get("run_status") == "SUBMISSION_VIOLATION"
            and viol_res.get("stopped_at_review") is False
        )
        all_passed = all_passed and viol_passed
        print(f"[{'PASS' if viol_passed else 'FAIL'}] 15. Auto-Submission Safety Gate (SUBMISSION_VIOLATION) enforced")
        print(f"       success: {viol_res.get('success')} | run_status: {viol_res.get('run_status')}\n")

        # Test 16: 20-Run Mocked Reproducibility Harness (0 credits)
        repro_pids = ["POL-100245", "POL-205118", "POL-309872", "POL-999001", "POL-999999"] * 4
        repro_ok = True
        for pid in repro_pids:
            fake_r = SimpleNamespace(status=RunStatus.COMPLETED, result=MOCK_PORTAL_RESPONSES[pid])
            with patch("tinyfish_client.TinyFish") as mock_tf_cls:
                mock_tf_cls.return_value.agent.run.return_value = fake_r
                r_out = verify_policy(
                    policy_id=pid,
                    diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                    estimated_cost=85000,
                    room_category="Semi-Private",
                    portal_url=DEFAULT_PORTAL_URL,
                )
            if r_out.get("submitted") is not False or not (r_out.get("field_accuracy") or {}).get("verified"):
                repro_ok = False
                break
        all_passed = all_passed and repro_ok
        print(f"[{'PASS' if repro_ok else 'FAIL'}] 16. 20-Run Mocked Reproducibility & Schema-Consistency Harness (20/20 runs)")
        print("       0 auto-submissions, 100% field accuracy audit consistency across 20 mocked runs.\n")

    if not all_passed:
        sys.exit(1)
    print("All 16 local product-logic, cross-check, safety-gate, and reproducibility checks passed (0 TinyFish credits used).")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("--check", "--self-test"):
        run_local_checks()
        return

    if not os.getenv("TINYFISH_API_KEY"):
        sys.exit(
            "Error: TINYFISH_API_KEY is not set.\n"
            "To test local guardrails and mocked portal scenarios without an API key, run:\n"
            "  python test_tinyfish.py --check\n\n"
            "To run a live TinyFish test in PowerShell, first set:\n"
            '  $env:TINYFISH_API_KEY="paste-your-key"'
        )

    portal_url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.getenv("MOCK_PORTAL_URL", DEFAULT_PORTAL_URL)
    )
    policy_id = sys.argv[2] if len(sys.argv) > 2 else "POL-100245"
    diagnosis = "Acute Cholecystitis / ICD-10 K81.0"
    estimated_cost = 85000

    print(f"Running live verify_policy for policy_id='{policy_id}' on '{portal_url}'...")
    result = verify_policy(
        policy_id=policy_id,
        diagnosis=diagnosis,
        estimated_cost=estimated_cost,
        portal_url=portal_url,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
