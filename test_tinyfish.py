"""
test_tinyfish.py
----------------
Local test suite and CLI runner for MedVerify's TinyFish integration.

Tests (0 TinyFish credits consumed with --check):
1. Input & URL guardrails (blank URL, missing scheme, localhost blocked).
2. All 4 confirmed portal policies on https://medverify-tpa-portal.vercel.app/:
   - POL-100245 (Rahul Sharma — Active) -> Staged & Stopped at Review & Verify (success = True)
   - POL-205118 (Sunita Verma — Active) -> Staged & Stopped at Review & Verify (success = True)
   - POL-309872 (Priya Nair — Active)   -> Staged & Stopped at Review & Verify (success = True)
   - POL-999001 (Vikram Malhotra — Lapsed) -> Halted at Policy Details (success = False, run_status = POLICY_LAPSED)
3. Unknown Policy ID (POL-999999) -> Rejected cleanly (success = False, run_status = NOT_FOUND)
4. Incomplete Workflow (Active policy but stopped_at_review = False) -> Flagged (success = False, run_status = INCOMPLETE_WORKFLOW)

Usage (PowerShell):
    # 1. Run all local guardrail & mocked policy checks (0 TinyFish credits):
    python test_tinyfish.py --check

    # 2. Run a live TinyFish verification (ONLY when explicitly approved):
    $env:TINYFISH_API_KEY="paste-your-key"
    python test_tinyfish.py https://medverify-tpa-portal.vercel.app/ POL-100245
"""

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

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
        "stopped_at_review": True,
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
        "stopped_at_review": True,
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
        "stopped_at_review": True,
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
        "stopped_at_review": False,
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
        "stopped_at_review": False,
        "notes": "Policy ID 'POL-999999' not found in TPA records.",
    },
}


def run_local_checks() -> None:
    """Verify input guardrails and all confirmed policy scenarios using 0 TinyFish credits."""
    print("=== MedVerify Local Guardrail & Mocked Policy Checks (0 Credits Used) ===\n")

    guardrail_cases = [
        (
            "1. Blank portal_url rejected",
            {
                "policy_id": "POL-100245",
                "diagnosis": "Acute Cholecystitis (K81.0)",
                "estimated_cost": 85000,
                "portal_url": "",
            },
            "INVALID_INPUT",
        ),
        (
            "2. Missing http/https scheme rejected",
            {
                "policy_id": "POL-100245",
                "diagnosis": "Acute Cholecystitis (K81.0)",
                "estimated_cost": 85000,
                "portal_url": "medverify-tpa-portal.vercel.app",
            },
            "INVALID_URL",
        ),
        (
            "3. Unreachable localhost URL blocked",
            {
                "policy_id": "POL-100245",
                "diagnosis": "Acute Cholecystitis (K81.0)",
                "estimated_cost": 85000,
                "portal_url": "http://localhost:8000",
            },
            "INVALID_URL",
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

    # Test the 4 confirmed portal policies + 1 unknown policy + 1 incomplete workflow via mocked SDK
    policy_test_cases = [
        ("4. Confirmed Active Policy POL-100245 (Rahul Sharma)", "POL-100245", True, "COMPLETED", True),
        ("5. Confirmed Active Policy POL-205118 (Sunita Verma)", "POL-205118", True, "COMPLETED", True),
        ("6. Confirmed Active Policy POL-309872 (Priya Nair)", "POL-309872", True, "COMPLETED", True),
        ("7. Confirmed Lapsed Policy POL-999001 (Vikram Malhotra) — Must NOT succeed", "POL-999001", False, "POLICY_LAPSED", False),
        ("8. Unknown Policy ID POL-999999 — Must NOT succeed", "POL-999999", False, "NOT_FOUND", False),
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
                    portal_url=DEFAULT_PORTAL_URL,
                )

            passed = (
                res.get("success") is expected_success
                and res.get("run_status") == expected_run_status
                and res.get("stopped_at_review") is expected_stopped
                and res.get("submitted") is False
            )
            all_passed = all_passed and passed
            print(f"[{'PASS' if passed else 'FAIL'}] {title}")
            print(
                f"       success: {res.get('success')} | run_status: {res.get('run_status')} | "
                f"policy_status: {res.get('policy_status')} | stopped_at_review: {res.get('stopped_at_review')} | "
                f"submitted: {res.get('submitted')}\n"
            )

        # Test 9: Incomplete workflow (Active policy but stopped_at_review = False) must fail verification
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
        print(f"[{'PASS' if inc_passed else 'FAIL'}] 9. Incomplete Workflow (stopped_at_review=False) rejected")
        print(f"       success: {inc_res.get('success')} | run_status: {inc_res.get('run_status')} | error: {inc_res.get('error')}\n")

    if not all_passed:
        sys.exit(1)
    print("All 9 local guardrail and mocked portal verification checks passed (0 TinyFish credits used).")


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
