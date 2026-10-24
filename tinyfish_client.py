"""
tinyfish_client.py
------------------
TinyFish SDK workflow engine for MedVerify (Team Nexora — HackIIITD 2026 / ESYA '26).

End-to-End Agentic Workflow (https://medverify-tpa-portal.vercel.app/):
1. Restrict automation to explicitly authorized mock TPA portal domains.
2. Open the portal and navigate to Policy Search.
3. Search for the supplied Policy ID and open the matching policy record.
4. Extract policy coverage details (extracted_policy_id, patient_name, insurer_name,
   policy_status, room_rent_limit, copay_percentage).
5. Let extracted policy status drive the workflow:
   - If Not Found: Stop on Policy Search (run_status = NOT_FOUND, success = False).
   - If Lapsed / Inactive: Stop on Policy Details without initiating pre-authorization
     (run_status = POLICY_LAPSED, success = False).
   - If Active: Click 'Initiate Pre-Authorization' and reuse the coordinator's submitted
     clinical/treatment case inputs (Hospital Name, Treating Doctor, Provisional Diagnosis,
     Estimated Cost, Room Category) to populate the Pre-Authorization Form.
6. Continue to Clinical Document Upload, attach the synthetic clinical document
   (sample_clinical_document.pdf), and click 'Proceed to Review'.
7. Reach 'Review & Verify', read back the actual staged values displayed on the review screen
   (extracted_policy_id, staged_diagnosis, staged_estimated_cost, staged_room_category,
   document_uploaded), and STOP without clicking 'Submit Pre-Authorization'.
8. Build a transparent, field-by-field audit table comparing each extracted and staged value
   against expected fixture / case-input values with PASS, MISMATCH, or NOT VERIFIED status.
"""

import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List
from urllib.parse import urlparse
from tinyfish import TinyFish, RunStatus
from playwright_fallback import (
    DEFAULT_HUMAN_CHECK_TIMEOUT_SECONDS,
    DEFAULT_POLL_INTERVAL_SECONDS,
    run_headed_playwright_fallback,
)

DEFAULT_PORTAL_URL = "https://medverify-tpa-portal.vercel.app/"
_ENV_FILE = Path(__file__).resolve().parent / ".env"

# Explicitly authorized mock TPA portal domains
AUTHORIZED_PORTAL_HOSTS = {
    "medverify-tpa-portal.vercel.app",
}

# Authoritative synthetic fixture data from Arush's deployed mock portal
# Used ONLY for independent post-extraction verification — never used to fabricate or overwrite results.
AUTHORITATIVE_PORTAL_FIXTURES: Dict[str, Dict[str, Any]] = {
    "POL-100245": {
        "patient_name": "Rahul Sharma",
        "insurer_name": "CareShield General Insurance",
        "policy_status": "Active",
        "room_rent_limit": "₹5,000 / day (Single Standard AC Room)",
        "room_rent_tokens": ["5,000", "single standard ac"],
        "copay_percentage": "0% (Nil)",
        "copay_tokens": ["0%"],
    },
    "POL-205118": {
        "patient_name": "Sunita Verma",
        "insurer_name": "Heritage Life & Health Assurance",
        "policy_status": "Active",
        "room_rent_limit": "Single Private AC Room (up to 1% of Sum Insured)",
        "room_rent_tokens": ["single private ac", "1%"],
        "copay_percentage": "10% Co-Pay applicable on total admitted claim amount",
        "copay_tokens": ["10%"],
    },
    "POL-309872": {
        "patient_name": "Priya Nair",
        "insurer_name": "Universal Alliance Health",
        "policy_status": "Active",
        "room_rent_limit": "No Capping / Actuals (Any category up to Deluxe)",
        "room_rent_tokens": ["no capping", "actuals"],
        "copay_percentage": "0% (Waived under Corporate GMC)",
        "copay_tokens": ["0%"],
    },
    "POL-999001": {
        "patient_name": "Vikram Malhotra",
        "insurer_name": "SecureLife Mediclaim Co.",
        "policy_status": "Lapsed",
        "room_rent_limit": "₹3,000 / day",
        "room_rent_tokens": ["3,000"],
        "copay_percentage": "20%",
        "copay_tokens": ["20%"],
    },
}

TIMING_START_BOUNDARY = "Backend verify_policy() entry immediately prior to TinyFish SDK dispatch"
TIMING_END_BOUNDARY = "TinyFish SDK response receipt and post-extraction field audit completion"


def load_env_file() -> None:
    """Load TINYFISH_API_KEY (and optional MOCK_PORTAL_URL) from local .env if present."""
    if not _ENV_FILE.is_file():
        return
    try:
        for raw_line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and val and not os.getenv(key):
                os.environ[key] = val
    except Exception:
        pass


load_env_file()


# Structured JSON schema for TinyFish output extraction
# Note: TinyFish API schema validator prohibits 'description' keys inside properties.
POLICY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "policy_found": {"type": "boolean"},
        "extracted_policy_id": {"type": "string"},
        "patient_name": {"type": "string"},
        "insurer_name": {"type": "string"},
        "policy_status": {"type": "string"},
        "room_rent_limit": {"type": "string"},
        "copay_percentage": {"type": "string"},
        "fields_prepared": {
            "type": "array",
            "items": {"type": "string"},
        },
        "document_uploaded": {"type": "string"},
        "current_portal_step": {"type": "string"},
        "staged_diagnosis": {"type": "string"},
        "staged_estimated_cost": {"type": "string"},
        "staged_room_category": {"type": "string"},
        "stopped_at_review": {"type": "boolean"},
        "submitted_or_receipt_visible": {"type": "boolean"},
        "access_or_auth_blocked": {"type": "boolean"},
        "notes": {"type": "string"},
    },
    "required": [
        "policy_found",
        "extracted_policy_id",
        "policy_status",
        "room_rent_limit",
        "copay_percentage",
        "fields_prepared",
        "stopped_at_review",
        "submitted_or_receipt_visible",
        "notes",
    ],
}


def _build_timing_metadata(elapsed_seconds: float, is_measured_live_run: bool) -> Dict[str, Any]:
    """Return transparent timing metadata without fabricating a manual baseline."""
    return {
        "elapsed_seconds": elapsed_seconds,
        "is_measured_live_run": is_measured_live_run,
        "start_boundary": TIMING_START_BOUNDARY,
        "end_boundary": TIMING_END_BOUNDARY,
        "observation_label": (
            "Single-run observation (live SDK)"
            if is_measured_live_run
            else "Pre-dispatch guardrail / non-live check"
        ),
        "manual_baseline_note": "No manual baseline measured in this environment",
    }


def _build_failure_response(
    policy_id: str,
    portal_url: str,
    error_message: str,
    run_status: str = "FAILED",
    elapsed_seconds: float = 0.0,
    is_measured_live_run: bool = False,
    raw_result: Any = None,
    checks: List[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    """Return a clean failure dictionary without inventing successful policy results."""
    audit_checks = checks if checks is not None else []
    pass_cnt = sum(1 for c in audit_checks if c.get("status") == "PASS")
    mismatch_cnt = sum(1 for c in audit_checks if c.get("status") == "MISMATCH")
    unverified_cnt = sum(1 for c in audit_checks if c.get("status") == "NOT VERIFIED")

    return {
        "success": False,
        "run_status": run_status,
        "policy_id": policy_id,
        "extracted_policy_id": None,
        "portal_url": portal_url,
        "manual_fallback_url": portal_url or DEFAULT_PORTAL_URL,
        "elapsed_seconds": elapsed_seconds,
        "timing": _build_timing_metadata(elapsed_seconds, is_measured_live_run),
        "policy_found": False,
        "patient_name": None,
        "insurer_name": None,
        "policy_status": None,
        "room_rent_limit": None,
        "copay_percentage": None,
        "co_payment": None,
        "fields_prepared": [],
        "document_uploaded": None,
        "current_portal_step": None,
        "staged_diagnosis": None,
        "staged_estimated_cost": None,
        "staged_room_category": None,
        "form_prepared": False,
        "stopped_at_review": False,
        "submitted": False,
        "submission_safeguard_verified": False,
        "field_accuracy": {
            "verified": False,
            "fixture_source": "none",
            "total_checks": len(audit_checks),
            "passed_count": pass_cnt,
            "mismatch_count": mismatch_cnt,
            "not_verified_count": unverified_cnt,
            "checks": audit_checks,
            "matched_checks": [],
            "policy_discrepancies": [],
            "staging_discrepancies": [],
            "discrepancies": [error_message],
        },
        "notes": None,
        "error": error_message,
        "raw_result": raw_result,
    }


def _get_allowed_portal_hosts() -> set[str]:
    extra = os.getenv("MEDVERIFY_ALLOWED_HOSTS", "")
    extra_hosts = {h.strip().lower() for h in extra.split(",") if h.strip()}
    return AUTHORIZED_PORTAL_HOSTS | extra_hosts


def _validate_portal_url(portal_url: str) -> tuple[str | None, str]:
    """
    Validate that portal_url is:
    1. A valid HTTP/HTTPS URL,
    2. Not a localhost/loopback address unreachable by TinyFish cloud, and
    3. Hosted on an explicitly authorized mock TPA portal domain.
    Returns (error_message_or_None, error_status_code).
    """
    parsed = urlparse(portal_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return (
            "Invalid portal_url. Please enter a full URL starting with 'https://' or 'http://'.",
            "INVALID_URL",
        )

    hostname = (parsed.hostname or "").lower()
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return (
            "Localhost URLs are not reachable by the TinyFish cloud browser. "
            f"Please provide the deployed mock portal URL ({DEFAULT_PORTAL_URL}).",
            "INVALID_URL",
        )

    allowed_hosts = _get_allowed_portal_hosts()
    if hostname not in allowed_hosts:
        allowed_list = ", ".join(sorted(allowed_hosts))
        return (
            f"Portal domain '{hostname}' is not in the authorized mock TPA portal allowlist "
            f"({allowed_list}). MedVerify restricts automation to authorized sandbox portals.",
            "UNAUTHORIZED_PORTAL",
        )

    return None, "OK"


def _is_inactive_status(status: str | None) -> bool:
    if not status:
        return False
    lowered = status.strip().lower()
    return any(
        token in lowered
        for token in ("lapsed", "expired", "inactive", "cancelled", "canceled", "suspended")
    )


def _is_active_status(status: str | None) -> bool:
    if not status:
        return False
    lowered = status.strip().lower()
    if _is_inactive_status(lowered):
        return False
    return "active" in lowered or "valid" in lowered


def _normalize_digits(val: Any) -> str:
    """Extract digits from a numeric/currency string (e.g. '₹85,000' -> '85000')."""
    if val is None:
        return ""
    return re.sub(r"[^\d]", "", str(val))


def _has_contradictory_submission_evidence(extracted: Dict[str, Any]) -> tuple[bool, str | None]:
    """
    Detect if submission evidence is violated or contradictory even when stopped_at_review is reported.
    Checks:
    1. submitted_or_receipt_visible is True
    2. current_portal_step mentions 'receipt' or 'submitted'
    3. notes contain a generated TPA claim reference (e.g. 'CLM-') or 'submission receipt'
    """
    submitted_raw = extracted.get("submitted_or_receipt_visible")
    step_str = str(extracted.get("current_portal_step") or "").strip()
    notes_str = str(extracted.get("notes") or "").strip()

    if submitted_raw is True:
        return True, "Agent reported submitted_or_receipt_visible=True."
    if any(tok in step_str.lower() for tok in ("receipt", "submitted", "submission complete")):
        return (
            True,
            f"Contradictory portal step '{step_str}' indicates Submission Receipt screen was reached.",
        )
    if re.search(r"\bclm-\d+\b", notes_str.lower()) or "submission receipt" in notes_str.lower():
        return (
            True,
            "Contradictory notes indicate a submission receipt or claim reference (CLM-*) was generated.",
        )
    return False, None


def _evaluate_field_accuracy(
    policy_id: str,
    input_diagnosis: str,
    input_cost: str,
    input_room_category: str,
    expect_sample_doc: bool,
    extracted: Dict[str, Any],
    workflow_mode: str,
) -> Dict[str, Any]:
    """
    Build a transparent, field-by-field audit table for the executed workflow mode:
    - workflow_mode == 'active': Evaluates all 11 checks (policy_id, patient_name,
      policy_status, room_rent_limit, co_payment, diagnosis, estimated_cost,
      room_category, supporting_document, review_screen_arrival, submission_safeguard).
    - workflow_mode == 'lapsed': Evaluates the 7 applicable checks for a Lapsed policy
      (policy_id, patient_name, policy_status, room_rent_limit, co_payment,
      preauth_halt_on_lapsed, submission_safeguard).
    - workflow_mode == 'not_found': Evaluates the 3 applicable checks for a Not Found policy
      (policy_id, policy_status, submission_safeguard).

    Each check entry contains:
      {"field": str, "label": str, "expected": str, "actual": str, "status": "PASS" | "MISMATCH" | "NOT VERIFIED"}

    Never overwrites raw extracted values with expected values. Missing evidence produces
    NOT VERIFIED, never PASS.
    """
    checks: List[Dict[str, str]] = []
    matched: List[str] = []
    policy_discrepancies: List[str] = []
    staging_discrepancies: List[str] = []

    pid_upper = policy_id.strip().upper()
    fixture = AUTHORITATIVE_PORTAL_FIXTURES.get(pid_upper)
    fixture_source = (
        f"AUTHORITATIVE_PORTAL_FIXTURES[{pid_upper}]"
        if fixture
        else ("unknown_policy_rule" if workflow_mode == "not_found" else "unlisted_policy_id")
    )

    ext_pid = str(extracted.get("extracted_policy_id") or "").strip()
    ext_name = str(extracted.get("patient_name") or "").strip()
    ext_status = str(extracted.get("policy_status") or "").strip()
    ext_room = str(extracted.get("room_rent_limit") or "").strip()
    ext_copay = str(extracted.get("copay_percentage") or extracted.get("co_payment") or "").strip()
    current_step = str(extracted.get("current_portal_step") or "").strip()
    stopped_raw = extracted.get("stopped_at_review")
    submitted_raw = extracted.get("submitted_or_receipt_visible")
    fields_prepared = extracted.get("fields_prepared")
    if not isinstance(fields_prepared, list):
        fields_prepared = []

    contradictory_sub, contradiction_reason = _has_contradictory_submission_evidence(extracted)

    # -------------------------------------------------------------------------
    # WORKFLOW MODE: NOT FOUND (Unknown policy ID)
    # -------------------------------------------------------------------------
    if workflow_mode == "not_found":
        if fixture:
            # Known active/lapsed policy was erroneously reported as Not Found
            checks.append({
                "field": "policy_id",
                "label": "Policy ID Lookup",
                "expected": f"{pid_upper} ({fixture['patient_name']} — Known Fixture)",
                "actual": "Reported as Not Found on Policy Search",
                "status": "MISMATCH",
            })
            policy_discrepancies.append(
                f"Known policy '{pid_upper}' ({fixture['patient_name']}) was reported as Not Found."
            )
            checks.append({
                "field": "policy_status",
                "label": "Policy Status",
                "expected": fixture["policy_status"],
                "actual": ext_status or "Not Found",
                "status": "MISMATCH",
            })
            policy_discrepancies.append(
                f"policy_status mismatch: expected '{fixture['policy_status']}', extracted '{ext_status or 'Not Found'}'"
            )
        else:
            checks.append({
                "field": "policy_id",
                "label": "Policy ID Lookup",
                "expected": f"{pid_upper} (Unlisted / Unknown Policy ID)",
                "actual": "Rejected on Policy Search (policy_found = false)",
                "status": "PASS",
            })
            matched.append("unknown_policy_correctly_rejected")

            status_ok = ext_status.lower() == "not found"
            checks.append({
                "field": "policy_status",
                "label": "Policy Status",
                "expected": "Not Found",
                "actual": ext_status or "Not extracted",
                "status": "PASS" if status_ok else ("NOT VERIFIED" if not ext_status else "MISMATCH"),
            })
            if status_ok:
                matched.append("policy_status == 'Not Found'")
            else:
                policy_discrepancies.append(
                    f"policy_status expected 'Not Found', got '{ext_status or 'None'}'"
                )

        if contradictory_sub:
            checks.append({
                "field": "submission_safeguard",
                "label": "Submission Status (Safeguard)",
                "expected": "Not Submitted (submitted_or_receipt_visible = false)",
                "actual": contradiction_reason or "Submission violation",
                "status": "MISMATCH",
            })
            staging_discrepancies.append(contradiction_reason or "Submission violation")
        elif submitted_raw is False:
            checks.append({
                "field": "submission_safeguard",
                "label": "Submission Status (Safeguard)",
                "expected": "Not Submitted (submitted_or_receipt_visible = false)",
                "actual": "Not Submitted (submitted_or_receipt_visible = false)",
                "status": "PASS",
            })
            matched.append("submission_safeguard == False")
        else:
            checks.append({
                "field": "submission_safeguard",
                "label": "Submission Status (Safeguard)",
                "expected": "Not Submitted (submitted_or_receipt_visible = false)",
                "actual": "Submission state not explicitly confirmed (submitted_or_receipt_visible = None)",
                "status": "NOT VERIFIED",
            })
            staging_discrepancies.append("Missing explicit submission_safeguard evidence.")

    # -------------------------------------------------------------------------
    # WORKFLOW MODE: ACTIVE OR LAPSED POLICY FOUND ON PORTAL
    # -------------------------------------------------------------------------
    else:
        # 1. Policy ID check
        if not ext_pid:
            checks.append({
                "field": "policy_id",
                "label": "Policy ID",
                "expected": pid_upper,
                "actual": "Not extracted",
                "status": "NOT VERIFIED",
            })
            policy_discrepancies.append("extracted_policy_id was not returned from the portal.")
        elif ext_pid.upper() == pid_upper:
            checks.append({
                "field": "policy_id",
                "label": "Policy ID",
                "expected": pid_upper,
                "actual": ext_pid,
                "status": "PASS",
            })
            matched.append(f"policy_id == '{pid_upper}'")
        else:
            checks.append({
                "field": "policy_id",
                "label": "Policy ID",
                "expected": pid_upper,
                "actual": ext_pid,
                "status": "MISMATCH",
            })
            policy_discrepancies.append(
                f"policy_id mismatch: expected '{pid_upper}', extracted '{ext_pid}'"
            )

        # 2. Patient Name check
        expected_name = fixture["patient_name"] if fixture else "Non-empty portal patient name"
        if not ext_name:
            checks.append({
                "field": "patient_name",
                "label": "Patient Name",
                "expected": expected_name,
                "actual": "Not extracted",
                "status": "NOT VERIFIED",
            })
            policy_discrepancies.append("patient_name was not extracted from the portal.")
        elif not fixture or fixture["patient_name"].lower() in ext_name.lower():
            checks.append({
                "field": "patient_name",
                "label": "Patient Name",
                "expected": expected_name,
                "actual": ext_name,
                "status": "PASS",
            })
            matched.append(f"patient_name == '{ext_name}'")
        else:
            checks.append({
                "field": "patient_name",
                "label": "Patient Name",
                "expected": expected_name,
                "actual": ext_name,
                "status": "MISMATCH",
            })
            policy_discrepancies.append(
                f"patient_name mismatch: expected '{expected_name}', extracted '{ext_name}'"
            )

        # 3. Policy Status check
        expected_status = (
            fixture["policy_status"]
            if fixture
            else ("Active" if workflow_mode == "active" else "Lapsed")
        )
        if not ext_status:
            checks.append({
                "field": "policy_status",
                "label": "Policy Status",
                "expected": expected_status,
                "actual": "Not extracted",
                "status": "NOT VERIFIED",
            })
            policy_discrepancies.append("policy_status was not extracted from the portal.")
        elif (fixture and fixture["policy_status"].lower() == ext_status.lower()) or (
            not fixture
            and (
                (workflow_mode == "active" and _is_active_status(ext_status))
                or (workflow_mode == "lapsed" and _is_inactive_status(ext_status))
            )
        ):
            checks.append({
                "field": "policy_status",
                "label": "Policy Status",
                "expected": expected_status,
                "actual": ext_status,
                "status": "PASS",
            })
            matched.append(f"policy_status == '{ext_status}'")
        else:
            checks.append({
                "field": "policy_status",
                "label": "Policy Status",
                "expected": expected_status,
                "actual": ext_status,
                "status": "MISMATCH",
            })
            policy_discrepancies.append(
                f"policy_status mismatch: expected '{expected_status}', extracted '{ext_status}'"
            )

        # 4. Room-Rent Limit check
        expected_room = fixture["room_rent_limit"] if fixture else "Non-empty room-rent limit"
        if not ext_room:
            checks.append({
                "field": "room_rent_limit",
                "label": "Room-Rent Limit",
                "expected": expected_room,
                "actual": "Not extracted",
                "status": "NOT VERIFIED",
            })
            policy_discrepancies.append("room_rent_limit was not extracted from the portal.")
        elif not fixture or all(tok in ext_room.lower() for tok in fixture["room_rent_tokens"]):
            checks.append({
                "field": "room_rent_limit",
                "label": "Room-Rent Limit",
                "expected": expected_room,
                "actual": ext_room,
                "status": "PASS",
            })
            matched.append(f"room_rent_limit matches fixture ('{ext_room}')")
        else:
            checks.append({
                "field": "room_rent_limit",
                "label": "Room-Rent Limit",
                "expected": expected_room,
                "actual": ext_room,
                "status": "MISMATCH",
            })
            policy_discrepancies.append(
                f"room_rent_limit mismatch: expected '{expected_room}', extracted '{ext_room}'"
            )

        # 5. Co-Payment Percentage check
        expected_copay = fixture["copay_percentage"] if fixture else "Non-empty co-payment clause"
        if not ext_copay:
            checks.append({
                "field": "co_payment",
                "label": "Co-Payment",
                "expected": expected_copay,
                "actual": "Not extracted",
                "status": "NOT VERIFIED",
            })
            policy_discrepancies.append("copay_percentage was not extracted from the portal.")
        elif not fixture or all(tok in ext_copay.lower() for tok in fixture["copay_tokens"]):
            checks.append({
                "field": "co_payment",
                "label": "Co-Payment",
                "expected": expected_copay,
                "actual": ext_copay,
                "status": "PASS",
            })
            matched.append(f"copay_percentage matches fixture ('{ext_copay}')")
        else:
            checks.append({
                "field": "co_payment",
                "label": "Co-Payment",
                "expected": expected_copay,
                "actual": ext_copay,
                "status": "MISMATCH",
            })
            policy_discrepancies.append(
                f"copay_percentage mismatch: expected '{expected_copay}', extracted '{ext_copay}'"
            )

        # Stage 2 checks for ACTIVE vs LAPSED workflow
        if workflow_mode == "active":
            # 6. Staged Diagnosis check
            staged_diag = str(extracted.get("staged_diagnosis") or "").strip()
            if not staged_diag:
                checks.append({
                    "field": "diagnosis",
                    "label": "Diagnosis (Review & Verify)",
                    "expected": input_diagnosis,
                    "actual": "Not read back from Review & Verify",
                    "status": "NOT VERIFIED",
                })
                staging_discrepancies.append("staged_diagnosis was not read back from Review & Verify.")
            elif (
                input_diagnosis.lower() in staged_diag.lower()
                or staged_diag.lower() in input_diagnosis.lower()
            ):
                checks.append({
                    "field": "diagnosis",
                    "label": "Diagnosis (Review & Verify)",
                    "expected": input_diagnosis,
                    "actual": staged_diag,
                    "status": "PASS",
                })
                matched.append(f"staged_diagnosis matches input ('{staged_diag}')")
            else:
                checks.append({
                    "field": "diagnosis",
                    "label": "Diagnosis (Review & Verify)",
                    "expected": input_diagnosis,
                    "actual": staged_diag,
                    "status": "MISMATCH",
                })
                staging_discrepancies.append(
                    f"staged_diagnosis mismatch: submitted '{input_diagnosis}', review screen showed '{staged_diag}'"
                )

            # 7. Staged Estimated Cost check
            staged_cost = str(extracted.get("staged_estimated_cost") or "").strip()
            if not staged_cost:
                checks.append({
                    "field": "estimated_cost",
                    "label": "Estimated Cost (Review & Verify)",
                    "expected": str(input_cost),
                    "actual": "Not read back from Review & Verify",
                    "status": "NOT VERIFIED",
                })
                staging_discrepancies.append("staged_estimated_cost was not read back from Review & Verify.")
            elif (
                _normalize_digits(staged_cost)
                and _normalize_digits(staged_cost) == _normalize_digits(input_cost)
            ):
                checks.append({
                    "field": "estimated_cost",
                    "label": "Estimated Cost (Review & Verify)",
                    "expected": str(input_cost),
                    "actual": staged_cost,
                    "status": "PASS",
                })
                matched.append(f"staged_estimated_cost matches input ('{staged_cost}')")
            else:
                checks.append({
                    "field": "estimated_cost",
                    "label": "Estimated Cost (Review & Verify)",
                    "expected": str(input_cost),
                    "actual": staged_cost,
                    "status": "MISMATCH",
                })
                staging_discrepancies.append(
                    f"staged_estimated_cost mismatch: submitted '{input_cost}', review screen showed '{staged_cost}'"
                )

            # 8. Staged Room Category check
            staged_room_cat = str(extracted.get("staged_room_category") or "").strip()
            if not staged_room_cat:
                checks.append({
                    "field": "room_category",
                    "label": "Room Category (Review & Verify)",
                    "expected": input_room_category,
                    "actual": "Not read back from Review & Verify",
                    "status": "NOT VERIFIED",
                })
                staging_discrepancies.append("staged_room_category was not read back from Review & Verify.")
            elif staged_room_cat.lower() == input_room_category.lower():
                checks.append({
                    "field": "room_category",
                    "label": "Room Category (Review & Verify)",
                    "expected": input_room_category,
                    "actual": staged_room_cat,
                    "status": "PASS",
                })
                matched.append(f"staged_room_category matches input ('{staged_room_cat}')")
            else:
                checks.append({
                    "field": "room_category",
                    "label": "Room Category (Review & Verify)",
                    "expected": input_room_category,
                    "actual": staged_room_cat,
                    "status": "MISMATCH",
                })
                staging_discrepancies.append(
                    f"staged_room_category mismatch: submitted '{input_room_category}', review screen showed '{staged_room_cat}'"
                )

            # 9. Supporting Document check
            doc_up = str(extracted.get("document_uploaded") or "").strip()
            expected_doc = "sample_clinical_document.pdf" if expect_sample_doc else "Clinical document verified"
            if expect_sample_doc:
                if not doc_up:
                    checks.append({
                        "field": "supporting_document",
                        "label": "Supporting Clinical Document",
                        "expected": expected_doc,
                        "actual": "Not staged / Not read back",
                        "status": "NOT VERIFIED",
                    })
                    staging_discrepancies.append("document_uploaded was not reported from Review & Verify.")
                elif "sample_clinical_document.pdf" in doc_up.lower():
                    checks.append({
                        "field": "supporting_document",
                        "label": "Supporting Clinical Document",
                        "expected": expected_doc,
                        "actual": doc_up,
                        "status": "PASS",
                    })
                    matched.append(f"document_uploaded verified ('{doc_up}')")
                else:
                    checks.append({
                        "field": "supporting_document",
                        "label": "Supporting Clinical Document",
                        "expected": expected_doc,
                        "actual": doc_up,
                        "status": "MISMATCH",
                    })
                    staging_discrepancies.append(
                        f"document_uploaded mismatch: expected 'sample_clinical_document.pdf', review screen showed '{doc_up}'"
                    )
            else:
                checks.append({
                    "field": "supporting_document",
                    "label": "Supporting Clinical Document",
                    "expected": expected_doc,
                    "actual": doc_up or "Optional",
                    "status": "PASS",
                })

            # 10. Review-Screen Arrival check
            arrived_ok = bool(
                current_step
                and "review" in current_step.lower()
                and stopped_raw is True
                and not contradictory_sub
            )
            checks.append({
                "field": "review_screen_arrival",
                "label": "Review-Screen Arrival",
                "expected": "Review & Verify (stopped_at_review = true)",
                "actual": f"{current_step or 'Not reported'} (stopped_at_review = {str(stopped_raw).lower()})",
                "status": "PASS" if arrived_ok else "NOT VERIFIED",
            })
            if arrived_ok:
                matched.append("review_screen_arrival == 'Review & Verify'")
            else:
                staging_discrepancies.append(
                    f"Review-screen arrival not verified (step='{current_step or 'None'}', stopped_at_review={stopped_raw})."
                )

            # 11. Submission Safeguard check
            if contradictory_sub:
                checks.append({
                    "field": "submission_safeguard",
                    "label": "Submission Status (Safeguard)",
                    "expected": "Not Submitted (submitted_or_receipt_visible = false, stopped_at_review = true)",
                    "actual": contradiction_reason or "Submission violation",
                    "status": "MISMATCH",
                })
                staging_discrepancies.append(contradiction_reason or "Submission violation")
            elif submitted_raw is False and arrived_ok:
                checks.append({
                    "field": "submission_safeguard",
                    "label": "Submission Status (Safeguard)",
                    "expected": "Not Submitted (submitted_or_receipt_visible = false, stopped_at_review = true)",
                    "actual": "Not Submitted (submitted_or_receipt_visible = false, halted at Review & Verify)",
                    "status": "PASS",
                })
                matched.append("submission_safeguard == False")
            else:
                checks.append({
                    "field": "submission_safeguard",
                    "label": "Submission Status (Safeguard)",
                    "expected": "Not Submitted (submitted_or_receipt_visible = false, stopped_at_review = true)",
                    "actual": (
                        f"Unverified safeguard state (submitted_or_receipt_visible = {submitted_raw}, "
                        f"stopped_at_review = {stopped_raw})"
                    ),
                    "status": "NOT VERIFIED",
                })
                staging_discrepancies.append(
                    "Submission safeguard could not be verified from available evidence."
                )

        elif workflow_mode == "lapsed":
            # 6. Lapsed-Policy Pre-Auth Halt check
            halted_properly = bool(
                len(fields_prepared) == 0
                and stopped_raw is False
                and current_step
                and "detail" in current_step.lower()
            )
            halt_status = (
                "PASS"
                if halted_properly
                else ("MISMATCH" if (len(fields_prepared) > 0 or stopped_raw is True) else "NOT VERIFIED")
            )
            checks.append({
                "field": "preauth_halt_on_lapsed",
                "label": "Lapsed-Policy Pre-Auth Halt",
                "expected": "Policy Details (fields_prepared = [], stopped_at_review = false)",
                "actual": (
                    f"{current_step or 'Not reported'} (fields_prepared = {len(fields_prepared)}, "
                    f"stopped_at_review = {str(stopped_raw).lower()})"
                ),
                "status": halt_status,
            })
            if halted_properly:
                matched.append("lapsed_policy_halted_at_policy_details")
            else:
                staging_discrepancies.append(
                    f"Lapsed policy did not halt cleanly at Policy Details (step='{current_step}', fields={fields_prepared})."
                )

            # 7. Submission Safeguard check
            if contradictory_sub:
                checks.append({
                    "field": "submission_safeguard",
                    "label": "Submission Status (Safeguard)",
                    "expected": "Not Submitted (submitted_or_receipt_visible = false)",
                    "actual": contradiction_reason or "Submission violation",
                    "status": "MISMATCH",
                })
                staging_discrepancies.append(contradiction_reason or "Submission violation")
            elif submitted_raw is False:
                checks.append({
                    "field": "submission_safeguard",
                    "label": "Submission Status (Safeguard)",
                    "expected": "Not Submitted (submitted_or_receipt_visible = false)",
                    "actual": "Not Submitted (submitted_or_receipt_visible = false)",
                    "status": "PASS",
                })
                matched.append("submission_safeguard == False")
            else:
                checks.append({
                    "field": "submission_safeguard",
                    "label": "Submission Status (Safeguard)",
                    "expected": "Not Submitted (submitted_or_receipt_visible = false)",
                    "actual": f"Unverified (submitted_or_receipt_visible = {submitted_raw})",
                    "status": "NOT VERIFIED",
                })
                staging_discrepancies.append("Missing explicit submission_safeguard evidence.")

    passed_count = sum(1 for c in checks if c["status"] == "PASS")
    mismatch_count = sum(1 for c in checks if c["status"] == "MISMATCH")
    not_verified_count = sum(1 for c in checks if c["status"] == "NOT VERIFIED")
    total_checks = len(checks)

    all_discrepancies = policy_discrepancies + staging_discrepancies
    verified = total_checks > 0 and mismatch_count == 0 and not_verified_count == 0

    return {
        "verified": verified,
        "fixture_source": fixture_source,
        "total_checks": total_checks,
        "passed_count": passed_count,
        "mismatch_count": mismatch_count,
        "not_verified_count": not_verified_count,
        "checks": checks,
        "matched_checks": matched,
        "policy_discrepancies": policy_discrepancies,
        "staging_discrepancies": staging_discrepancies,
        "discrepancies": all_discrepancies,
    }


def verify_policy(
    policy_id: str,
    diagnosis: str,
    estimated_cost: float | int | str,
    portal_url: str = DEFAULT_PORTAL_URL,
    room_category: str = "Semi-Private",
    hospital_name: str = "Apollo Care Superspecialty Hospital",
    doctor_name: str = "Dr. Rajesh K. Mehta",
    use_sample_document: bool = True,
    enable_playwright_fallback: bool = False,
    human_check_timeout_seconds: float = DEFAULT_HUMAN_CHECK_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    status_callback: Callable[[str, str], None] | None = None,
    playwright_stub_page: Any = None,
) -> Dict[str, Any]:
    """
    Execute the confirmed MedVerify TinyFish workflow against the authorized mock TPA portal
    and perform transparent, field-by-field verification of extracted policy coverage and
    staged review-screen fields.
    """
    start_ts = time.perf_counter()

    policy_id_clean = str(policy_id).strip() if policy_id is not None else ""
    diagnosis_clean = str(diagnosis).strip() if diagnosis is not None else ""
    cost_clean = str(estimated_cost).strip() if estimated_cost is not None else ""
    portal_url_clean = str(portal_url).strip() if portal_url is not None else ""
    room_cat_clean = str(room_category).strip() if room_category else "Semi-Private"
    hosp_clean = str(hospital_name).strip() if hospital_name else "Apollo Care Superspecialty Hospital"
    doc_clean = str(doctor_name).strip() if doctor_name else "Dr. Rajesh K. Mehta"

    # 1. Validate required inputs first (0 credits consumed)
    if not policy_id_clean or not diagnosis_clean or not cost_clean or not portal_url_clean:
        return _build_failure_response(
            policy_id=policy_id_clean,
            portal_url=portal_url_clean,
            error_message=(
                "All arguments (policy_id, diagnosis, estimated_cost, portal_url) "
                "must be provided."
            ),
            run_status="INVALID_INPUT",
            elapsed_seconds=round(time.perf_counter() - start_ts, 2),
            is_measured_live_run=False,
        )

    url_error, url_status = _validate_portal_url(portal_url_clean)
    if url_error:
        return _build_failure_response(
            policy_id=policy_id_clean,
            portal_url=portal_url_clean,
            error_message=url_error,
            run_status=url_status,
            elapsed_seconds=round(time.perf_counter() - start_ts, 2),
            is_measured_live_run=False,
        )

    # 2. Check that TINYFISH_API_KEY is set in the environment (or .env file)
    load_env_file()
    if not os.getenv("TINYFISH_API_KEY"):
        return _build_failure_response(
            policy_id=policy_id_clean,
            portal_url=portal_url_clean,
            error_message=(
                "TINYFISH_API_KEY environment variable is not set. "
                "Set it in your terminal or local .env file before running live TinyFish verification."
            ),
            run_status="MISSING_API_KEY",
            elapsed_seconds=round(time.perf_counter() - start_ts, 2),
            is_measured_live_run=False,
        )

    doc_instruction = (
        "Ensure 'Use Sample Document' (attaching sample_clinical_document.pdf) is checked/selected"
        if use_sample_document
        else "Verify the clinical document upload state"
    )

    # 3. Build the confirmed step-by-step goal for the TinyFish web agent
    goal = (
        "Follow this exact workflow on the ApexCare Health TPA portal:\n"
        "SECURITY & ACCESS RULE: Do NOT attempt to log in, enter credentials, or bypass any login screen, "
        "CAPTCHA, MFA challenge, or access control. If the page requires authentication, CAPTCHA, MFA, or "
        "blocks access, STOP immediately, set access_or_auth_blocked to true, policy_found to false, "
        "extracted_policy_id to '', and explain in notes.\n"
        "1. Open the portal and navigate to 'Policy Search' (click 'Proceed to Policy Search' or 'Policy Search').\n"
        f"2. Enter Policy ID '{policy_id_clean}' into the Policy ID search input and click 'Search Policy'.\n"
        f"3. If an error alert appears stating Policy ID '{policy_id_clean}' was not found in TPA records, "
        "stop immediately on the Policy Search screen: set policy_found to false, extracted_policy_id to '', "
        "policy_status to 'Not Found', current_portal_step to 'Policy Search', stopped_at_review to false, "
        "submitted_or_receipt_visible to false, access_or_auth_blocked to false, and do not invent any policy details.\n"
        "4. When the matching policy opens on 'Policy Details & Coverage Verification', extract the exact text shown on page for: "
        "extracted_policy_id (the Policy ID displayed on the policy record), patient_name, insurer_name, "
        "policy_status ('Active' or 'Lapsed'), room_rent_limit ('Room Rent Limit'), and copay_percentage ('Co-Payment Clause').\n"
        "5. Use the extracted policy_status to drive the next action:\n"
        "   - If policy_status is 'Lapsed' (or inactive/expired), STOP immediately on the Policy Details screen. "
        "Do NOT initiate Pre-Authorization. Return the extracted details with current_portal_step as 'Policy Details', "
        "fields_prepared as [], stopped_at_review as false, and submitted_or_receipt_visible as false.\n"
        "   - If policy_status is 'Active', click 'Initiate Pre-Authorization' to open the Pre-Authorization Form.\n"
        f"6. On the Pre-Authorization Form, populate: 'Hospital Name' = '{hosp_clean}', "
        f"'Treating Doctor' = '{doc_clean}', 'Provisional Diagnosis / ICD Code' = '{diagnosis_clean}', "
        f"'Estimated Cost' = '{cost_clean}', and select 'Room Category' = '{room_cat_clean}'.\n"
        "7. Click 'Next: Document Upload' to proceed to the Clinical Document Upload step.\n"
        f"8. {doc_instruction}, then click 'Proceed to Review'.\n"
        "9. Wait until the 'Review & Verify' screen is visible. Read back the actual values displayed on the "
        "'Review & Verify' screen into extracted_policy_id ('Policy ID'), staged_diagnosis ('Diagnosis / ICD Code'), "
        "staged_estimated_cost ('Estimated Cost'), staged_room_category ('Room Category'), and document_uploaded "
        "('Uploaded document name'), and set current_portal_step to 'Review & Verify'.\n"
        "10. STOP THERE on the 'Review & Verify' screen. Do NOT click 'Submit Pre-Authorization' under any circumstances. "
        "Set stopped_at_review to true, submitted_or_receipt_visible to false, and access_or_auth_blocked to false."
    )

    # 4. Run the TinyFish agent
    try:
        client = TinyFish()
        run = client.agent.run(
            url=portal_url_clean,
            goal=goal,
            output_schema=POLICY_SCHEMA,
        )
    except Exception as exc:
        elapsed_seconds = round(time.perf_counter() - start_ts, 2)
        exc_text = str(exc)
        is_timeout = any(tok in exc_text.lower() for tok in ("timeout", "timed out", "deadline"))
        return _build_failure_response(
            policy_id=policy_id_clean,
            portal_url=portal_url_clean,
            error_message=(
                f"TinyFish automation timed out ({exc_text}). Use the manual fallback link to access the portal."
                if is_timeout
                else f"TinyFish SDK error: {exc_text}"
            ),
            run_status="TIMEOUT" if is_timeout else "EXCEPTION",
            elapsed_seconds=elapsed_seconds,
            is_measured_live_run=True,
        )

    elapsed_seconds = round(time.perf_counter() - start_ts, 2)
    timing_meta = _build_timing_metadata(elapsed_seconds, is_measured_live_run=True)

    # 5. Verify the run completed and returned a dictionary matching our schema
    status_name = getattr(run.status, "name", str(run.status))
    if run.status != RunStatus.COMPLETED:
        return _build_failure_response(
            policy_id=policy_id_clean,
            portal_url=portal_url_clean,
            error_message=f"TinyFish run did not complete (status: {status_name}).",
            run_status=status_name,
            elapsed_seconds=elapsed_seconds,
            is_measured_live_run=True,
            raw_result=getattr(run, "result", None),
        )

    if not isinstance(run.result, dict):
        return _build_failure_response(
            policy_id=policy_id_clean,
            portal_url=portal_url_clean,
            error_message="TinyFish run completed, but did not return structured JSON.",
            run_status="INVALID_SCHEMA",
            elapsed_seconds=elapsed_seconds,
            is_measured_live_run=True,
            raw_result=getattr(run, "result", None),
        )

    result = run.result
    policy_found = bool(result.get("policy_found", False))
    extracted_policy_id = result.get("extracted_policy_id")
    policy_status = result.get("policy_status")
    patient_name = result.get("patient_name")
    insurer_name = result.get("insurer_name")
    room_rent_limit = result.get("room_rent_limit")
    copay_val = result.get("copay_percentage") or result.get("co_payment")
    document_uploaded = result.get("document_uploaded")
    current_portal_step = result.get("current_portal_step")
    staged_diagnosis = result.get("staged_diagnosis")
    staged_estimated_cost = result.get("staged_estimated_cost")
    staged_room_category = result.get("staged_room_category")
    stopped_at_review = bool(result.get("stopped_at_review", False))
    submitted_raw = result.get("submitted_or_receipt_visible")
    access_blocked = bool(result.get("access_or_auth_blocked", False))
    notes = result.get("notes")

    fields_prepared = result.get("fields_prepared")
    if not isinstance(fields_prepared, list):
        fields_prepared = []

    # Check for authentication / CAPTCHA / MFA / access restriction
    fallback_used: str | None = None
    paused_for_human_check: bool = False
    human_check_status_history: List[str] = []

    combined_notes = f"{notes or ''} {current_portal_step or ''}".lower()
    if access_blocked or any(
        tok in combined_notes
        for tok in ("captcha", "login required", "mfa", "two-factor", "access denied", "403 forbidden")
    ):
        if enable_playwright_fallback:
            # Optional local headed-Chromium fallback on the allowlisted portal URL ONLY
            fb_out = run_headed_playwright_fallback(
                portal_url=portal_url_clean,
                policy_id=policy_id_clean,
                diagnosis=diagnosis_clean,
                estimated_cost=cost_clean,
                room_category=room_cat_clean,
                hospital_name=hosp_clean,
                doctor_name=doc_clean,
                use_sample_document=use_sample_document,
                human_check_timeout_seconds=human_check_timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                status_callback=status_callback,
                stub_page=playwright_stub_page,
            )
            elapsed_seconds = round(time.perf_counter() - start_ts, 2)
            timing_meta = _build_timing_metadata(elapsed_seconds, is_measured_live_run=True)
            fallback_used = "playwright_headed_chromium"
            paused_for_human_check = bool(fb_out.get("paused_for_human", False))
            human_check_status_history = list(fb_out.get("status_history") or [])

            if fb_out.get("timed_out") or fb_out.get("run_status") == "HUMAN_CHECK_TIMEOUT":
                timeout_err = fb_out.get("error") or (
                    f"Human verification check timed out after {human_check_timeout_seconds}s."
                )
                return {
                    "success": False,
                    "run_status": "HUMAN_CHECK_TIMEOUT",
                    "fallback_used": fallback_used,
                    "paused_for_human_check": paused_for_human_check,
                    "human_check_status_history": human_check_status_history,
                    "policy_id": policy_id_clean,
                    "extracted_policy_id": None,
                    "portal_url": portal_url_clean,
                    "manual_fallback_url": portal_url_clean,
                    "elapsed_seconds": elapsed_seconds,
                    "timing": timing_meta,
                    "policy_found": False,
                    "patient_name": None,
                    "insurer_name": None,
                    "policy_status": None,
                    "room_rent_limit": None,
                    "copay_percentage": None,
                    "co_payment": None,
                    "fields_prepared": [],
                    "document_uploaded": None,
                    "current_portal_step": "Waiting for human check (Timed Out)",
                    "staged_diagnosis": None,
                    "staged_estimated_cost": None,
                    "staged_room_category": None,
                    "form_prepared": False,
                    "stopped_at_review": False,
                    "submitted": False,
                    "submission_safeguard_verified": False,
                    "field_accuracy": {
                        "verified": False,
                        "fixture_source": "none",
                        "total_checks": 1,
                        "passed_count": 0,
                        "mismatch_count": 0,
                        "not_verified_count": 1,
                        "checks": [
                            {
                                "field": "human_verification_check",
                                "label": "Human Verification Check (Local Headed Chromium)",
                                "expected": f"Human completes check within {human_check_timeout_seconds}s and 'Policy Search' appears",
                                "actual": f"Timed out after {fb_out.get('waited_seconds', human_check_timeout_seconds)}s (HUMAN_CHECK_TIMEOUT)",
                                "status": "NOT VERIFIED",
                            }
                        ],
                        "matched_checks": [],
                        "policy_discrepancies": [],
                        "staging_discrepancies": [],
                        "discrepancies": [timeout_err],
                    },
                    "notes": timeout_err,
                    "error": timeout_err,
                    "raw_result": fb_out,
                }

            if not isinstance(fb_out.get("extracted"), dict):
                fb_err = fb_out.get("error") or "Local Playwright fallback did not return extracted data."
                return _build_failure_response(
                    policy_id=policy_id_clean,
                    portal_url=portal_url_clean,
                    error_message=fb_err,
                    run_status=str(fb_out.get("run_status") or "PLAYWRIGHT_FALLBACK_FAILED"),
                    elapsed_seconds=elapsed_seconds,
                    is_measured_live_run=True,
                    raw_result=fb_out,
                )

            # Reuse the exact same post-extraction validation & 11-check audit pipeline!
            result = fb_out["extracted"]
            policy_found = bool(result.get("policy_found", False))
            extracted_policy_id = result.get("extracted_policy_id")
            policy_status = result.get("policy_status")
            patient_name = result.get("patient_name")
            insurer_name = result.get("insurer_name")
            room_rent_limit = result.get("room_rent_limit")
            copay_val = result.get("copay_percentage") or result.get("co_payment")
            document_uploaded = result.get("document_uploaded")
            current_portal_step = result.get("current_portal_step")
            staged_diagnosis = result.get("staged_diagnosis")
            staged_estimated_cost = result.get("staged_estimated_cost")
            staged_room_category = result.get("staged_room_category")
            stopped_at_review = bool(result.get("stopped_at_review", False))
            submitted_raw = result.get("submitted_or_receipt_visible")
            access_blocked = bool(result.get("access_or_auth_blocked", False))
            notes = result.get("notes")
            fields_prepared = result.get("fields_prepared")
            if not isinstance(fields_prepared, list):
                fields_prepared = []
        else:
            return {
                "success": False,
                "run_status": "ACCESS_OR_AUTH_BLOCKED",
                "policy_id": policy_id_clean,
                "extracted_policy_id": extracted_policy_id,
                "portal_url": portal_url_clean,
                "manual_fallback_url": portal_url_clean,
                "elapsed_seconds": elapsed_seconds,
                "timing": timing_meta,
                "policy_found": False,
                "patient_name": None,
                "insurer_name": None,
                "policy_status": None,
                "room_rent_limit": None,
                "copay_percentage": None,
                "co_payment": None,
                "fields_prepared": [],
                "document_uploaded": None,
                "current_portal_step": current_portal_step,
                "staged_diagnosis": None,
                "staged_estimated_cost": None,
                "staged_room_category": None,
                "form_prepared": False,
                "stopped_at_review": False,
                "submitted": False,
                "submission_safeguard_verified": False,
                "field_accuracy": {
                    "verified": False,
                    "fixture_source": "none",
                    "total_checks": 1,
                    "passed_count": 0,
                    "mismatch_count": 0,
                    "not_verified_count": 1,
                    "checks": [
                        {
                            "field": "portal_access",
                            "label": "Portal Access & Auth Check",
                            "expected": "Open sandbox portal without login/CAPTCHA barrier",
                            "actual": notes or "Access or authentication barrier detected",
                            "status": "NOT VERIFIED",
                        }
                    ],
                    "matched_checks": [],
                    "policy_discrepancies": [],
                    "staging_discrepancies": [],
                    "discrepancies": ["Portal access or authentication barrier detected."],
                },
                "notes": notes,
                "error": (
                    "Portal requires authentication, CAPTCHA, or restricted access. "
                    "MedVerify never bypasses access controls; enable the optional local headed-Chromium "
                    "fallback or use the manual portal link."
                ),
                "raw_result": result,
            }

    # Safety Gate 0: Check for direct or contradictory submission evidence
    contradictory_sub, contradiction_reason = _has_contradictory_submission_evidence(result)
    if contradictory_sub:
        wf_mode = "active" if _is_active_status(policy_status) else ("lapsed" if _is_inactive_status(policy_status) else "not_found")
        acc_viol = _evaluate_field_accuracy(
            policy_id=policy_id_clean,
            input_diagnosis=diagnosis_clean,
            input_cost=cost_clean,
            input_room_category=room_cat_clean,
            expect_sample_doc=use_sample_document,
            extracted=result,
            workflow_mode=wf_mode,
        )
        return {
            "success": False,
            "run_status": "SUBMISSION_VIOLATION",
            "policy_id": policy_id_clean,
            "extracted_policy_id": extracted_policy_id,
            "portal_url": portal_url_clean,
            "manual_fallback_url": portal_url_clean,
            "elapsed_seconds": elapsed_seconds,
            "timing": timing_meta,
            "policy_found": policy_found,
            "patient_name": patient_name,
            "insurer_name": insurer_name,
            "policy_status": policy_status,
            "room_rent_limit": room_rent_limit,
            "copay_percentage": copay_val,
            "co_payment": copay_val,
            "fields_prepared": fields_prepared,
            "document_uploaded": document_uploaded,
            "current_portal_step": current_portal_step,
            "staged_diagnosis": staged_diagnosis,
            "staged_estimated_cost": staged_estimated_cost,
            "staged_room_category": staged_room_category,
            "form_prepared": len(fields_prepared) > 0,
            "stopped_at_review": False,
            "submitted": True,
            "submission_safeguard_verified": False,
            "field_accuracy": acc_viol,
            "notes": notes,
            "error": f"Safety violation: {contradiction_reason}",
            "raw_result": result,
        }

    # Case A: Unknown / Not Found Policy ID -> Must NOT appear as successful verification
    if not policy_found or (policy_status and policy_status.strip().lower() == "not found"):
        acc_nf = _evaluate_field_accuracy(
            policy_id=policy_id_clean,
            input_diagnosis=diagnosis_clean,
            input_cost=cost_clean,
            input_room_category=room_cat_clean,
            expect_sample_doc=use_sample_document,
            extracted=result,
            workflow_mode="not_found",
        )
        pid_upper = policy_id_clean.upper()
        known_fixture = AUTHORITATIVE_PORTAL_FIXTURES.get(pid_upper)
        if known_fixture:
            return {
                "success": False,
                "run_status": "FIELD_MISMATCH",
                "policy_id": policy_id_clean,
                "extracted_policy_id": extracted_policy_id,
                "portal_url": portal_url_clean,
                "manual_fallback_url": portal_url_clean,
                "elapsed_seconds": elapsed_seconds,
                "timing": timing_meta,
                "policy_found": False,
                "patient_name": None,
                "insurer_name": None,
                "policy_status": "Not Found",
                "room_rent_limit": None,
                "copay_percentage": None,
                "co_payment": None,
                "fields_prepared": [],
                "document_uploaded": None,
                "current_portal_step": current_portal_step or "Policy Search",
                "staged_diagnosis": None,
                "staged_estimated_cost": None,
                "staged_room_category": None,
                "form_prepared": False,
                "stopped_at_review": False,
                "submitted": False,
                "submission_safeguard_verified": submitted_raw is False,
                "field_accuracy": acc_nf,
                "notes": notes,
                "error": f"Extraction mismatch: Known policy '{pid_upper}' was reported as Not Found.",
                "raw_result": result,
            }

        return {
            "success": False,
            "run_status": "NOT_FOUND",
            "policy_id": policy_id_clean,
            "extracted_policy_id": extracted_policy_id,
            "portal_url": portal_url_clean,
            "manual_fallback_url": portal_url_clean,
            "elapsed_seconds": elapsed_seconds,
            "timing": timing_meta,
            "policy_found": False,
            "patient_name": None,
            "insurer_name": None,
            "policy_status": "Not Found",
            "room_rent_limit": None,
            "copay_percentage": None,
            "co_payment": None,
            "fields_prepared": [],
            "document_uploaded": None,
            "current_portal_step": current_portal_step or "Policy Search",
            "staged_diagnosis": None,
            "staged_estimated_cost": None,
            "staged_room_category": None,
            "form_prepared": False,
            "stopped_at_review": False,
            "submitted": False,
            "submission_safeguard_verified": submitted_raw is False,
            "field_accuracy": acc_nf,
            "notes": notes or f"Policy '{policy_id_clean}' was not found in TPA portal records.",
            "error": f"Policy '{policy_id_clean}' was not found in TPA portal records.",
            "raw_result": result,
        }

    # Case B: Lapsed / Expired / Inactive Policy -> Must NOT enter active preparation flow
    if _is_inactive_status(policy_status):
        accuracy_report = _evaluate_field_accuracy(
            policy_id=policy_id_clean,
            input_diagnosis=diagnosis_clean,
            input_cost=cost_clean,
            input_room_category=room_cat_clean,
            expect_sample_doc=use_sample_document,
            extracted=result,
            workflow_mode="lapsed",
        )
        run_code = (
            "FIELD_MISMATCH"
            if accuracy_report["mismatch_count"] > 0
            else ("INCOMPLETE_WORKFLOW" if accuracy_report["not_verified_count"] > 0 else "POLICY_LAPSED")
        )
        err_msg = (
            f"Policy '{policy_id_clean}' status is {policy_status}. "
            "Cashless pre-authorization cannot be initiated for a lapsed policy."
            if accuracy_report["verified"]
            else "Policy audit issue on lapsed policy: " + "; ".join(accuracy_report["discrepancies"])
        )
        return {
            "success": False,
            "run_status": run_code,
            "policy_id": policy_id_clean,
            "extracted_policy_id": extracted_policy_id,
            "portal_url": portal_url_clean,
            "manual_fallback_url": portal_url_clean,
            "elapsed_seconds": elapsed_seconds,
            "timing": timing_meta,
            "policy_found": True,
            "patient_name": patient_name,
            "insurer_name": insurer_name,
            "policy_status": policy_status,
            "room_rent_limit": room_rent_limit,
            "copay_percentage": copay_val,
            "co_payment": copay_val,
            "fields_prepared": [],
            "document_uploaded": None,
            "current_portal_step": current_portal_step or "Policy Details",
            "staged_diagnosis": None,
            "staged_estimated_cost": None,
            "staged_room_category": None,
            "form_prepared": False,
            "stopped_at_review": False,
            "submitted": False,
            "submission_safeguard_verified": submitted_raw is False,
            "field_accuracy": accuracy_report,
            "notes": notes or (
                f"Policy '{policy_id_clean}' is {policy_status}. "
                "Cashless pre-authorization is prohibited and form staging was halted."
            ),
            "error": err_msg,
            "raw_result": result,
        }

    # Case C: Active policy — run full 11-check audit and enforce genuine success criteria
    accuracy_report = _evaluate_field_accuracy(
        policy_id=policy_id_clean,
        input_diagnosis=diagnosis_clean,
        input_cost=cost_clean,
        input_room_category=room_cat_clean,
        expect_sample_doc=use_sample_document,
        extracted=result,
        workflow_mode="active",
    )

    has_required_coverage = bool(
        _is_active_status(policy_status) and room_rent_limit and copay_val and patient_name and extracted_policy_id
    )
    form_prepared = len(fields_prepared) > 0
    step_ok = bool(current_portal_step and "review" in current_portal_step.lower())
    doc_ok = bool(
        not use_sample_document
        or (document_uploaded and "sample_clinical_document.pdf" in document_uploaded.lower())
    )
    safeguard_ok = bool(submitted_raw is False and stopped_at_review and step_ok)

    # 1. Any explicit value mismatch (PASS vs MISMATCH) -> FIELD_MISMATCH
    if accuracy_report["mismatch_count"] > 0:
        mismatch_summary = "; ".join(accuracy_report["discrepancies"])
        return {
            "success": False,
            "run_status": "FIELD_MISMATCH",
            "policy_id": policy_id_clean,
            "extracted_policy_id": extracted_policy_id,
            "portal_url": portal_url_clean,
            "manual_fallback_url": portal_url_clean,
            "elapsed_seconds": elapsed_seconds,
            "timing": timing_meta,
            "policy_found": True,
            "patient_name": patient_name,
            "insurer_name": insurer_name,
            "policy_status": policy_status,
            "room_rent_limit": room_rent_limit,
            "copay_percentage": copay_val,
            "co_payment": copay_val,
            "fields_prepared": fields_prepared,
            "document_uploaded": document_uploaded,
            "current_portal_step": current_portal_step,
            "staged_diagnosis": staged_diagnosis,
            "staged_estimated_cost": staged_estimated_cost,
            "staged_room_category": staged_room_category,
            "form_prepared": form_prepared,
            "stopped_at_review": stopped_at_review,
            "submitted": False,
            "submission_safeguard_verified": safeguard_ok,
            "field_accuracy": accuracy_report,
            "notes": notes,
            "error": f"Field verification mismatch detected: {mismatch_summary}",
            "raw_result": result,
        }

    # 2. Any missing / NOT VERIFIED check or incomplete workflow step -> INCOMPLETE_WORKFLOW
    if (
        not has_required_coverage
        or not form_prepared
        or not stopped_at_review
        or not step_ok
        or not doc_ok
        or not safeguard_ok
        or accuracy_report["not_verified_count"] > 0
        or not accuracy_report["verified"]
    ):
        missing_reasons = []
        if not _is_active_status(policy_status):
            missing_reasons.append(f"unexpected policy_status '{policy_status}'")
        if not extracted_policy_id:
            missing_reasons.append("missing extracted_policy_id")
        if not patient_name:
            missing_reasons.append("missing patient_name")
        if not room_rent_limit:
            missing_reasons.append("missing room_rent_limit")
        if not copay_val:
            missing_reasons.append("missing copay_percentage")
        if not form_prepared:
            missing_reasons.append("pre-authorization fields were not staged")
        if not doc_ok:
            missing_reasons.append("synthetic clinical document was not staged")
        if not stopped_at_review or not step_ok:
            missing_reasons.append(
                f"agent did not confirm stopping at Review & Verify (current_portal_step='{current_portal_step}')"
            )
        if submitted_raw is not False:
            missing_reasons.append(
                "submission safeguard evidence (submitted_or_receipt_visible=False) was not explicitly confirmed"
            )
        for chk in accuracy_report["checks"]:
            if chk["status"] == "NOT VERIFIED":
                reason_item = f"{chk['field']} is NOT VERIFIED"
                if reason_item not in missing_reasons:
                    missing_reasons.append(reason_item)

        reason_str = ", ".join(missing_reasons) if missing_reasons else "unverified required checks"
        return {
            "success": False,
            "run_status": "INCOMPLETE_WORKFLOW",
            "policy_id": policy_id_clean,
            "extracted_policy_id": extracted_policy_id,
            "portal_url": portal_url_clean,
            "manual_fallback_url": portal_url_clean,
            "elapsed_seconds": elapsed_seconds,
            "timing": timing_meta,
            "policy_found": True,
            "patient_name": patient_name,
            "insurer_name": insurer_name,
            "policy_status": policy_status,
            "room_rent_limit": room_rent_limit,
            "copay_percentage": copay_val,
            "co_payment": copay_val,
            "fields_prepared": fields_prepared,
            "document_uploaded": document_uploaded,
            "current_portal_step": current_portal_step,
            "staged_diagnosis": staged_diagnosis,
            "staged_estimated_cost": staged_estimated_cost,
            "staged_room_category": staged_room_category,
            "form_prepared": form_prepared,
            "stopped_at_review": stopped_at_review,
            "submitted": False,
            "submission_safeguard_verified": safeguard_ok,
            "field_accuracy": accuracy_report,
            "notes": notes,
            "error": f"Incomplete verification workflow ({reason_str}). Manual coordinator review required.",
            "raw_result": result,
        }

    # Case D: Genuine Success — All 11 checks are PASS, 0 MISMATCH, 0 NOT VERIFIED,
    # Review & Verify reached, and human-review safeguard confirmed.
    return {
        "success": True,
        "run_status": status_name,
        "fallback_used": fallback_used,
        "paused_for_human_check": paused_for_human_check,
        "human_check_status_history": human_check_status_history,
        "policy_id": policy_id_clean,
        "extracted_policy_id": extracted_policy_id,
        "portal_url": portal_url_clean,
        "manual_fallback_url": portal_url_clean,
        "elapsed_seconds": elapsed_seconds,
        "timing": timing_meta,
        "policy_found": True,
        "patient_name": patient_name,
        "insurer_name": insurer_name,
        "policy_status": policy_status,
        "room_rent_limit": room_rent_limit,
        "copay_percentage": copay_val,
        "co_payment": copay_val,
        "fields_prepared": fields_prepared,
        "document_uploaded": document_uploaded,
        "current_portal_step": current_portal_step,
        "staged_diagnosis": staged_diagnosis,
        "staged_estimated_cost": staged_estimated_cost,
        "staged_room_category": staged_room_category,
        "form_prepared": True,
        "stopped_at_review": True,
        "submitted": False,
        "submission_safeguard_verified": True,
        "field_accuracy": accuracy_report,
        "notes": notes,
        "error": None,
        "raw_result": result,
    }
