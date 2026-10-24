"""
tinyfish_client.py
------------------
TinyFish SDK workflow engine for MedVerify (Team Nexora — HackIIITD 2026 / ESYA '26).

End-to-End Agentic Workflow (https://medverify-tpa-portal.vercel.app/):
1. Restrict automation to explicitly authorized mock TPA portal domains.
2. Open the portal and navigate to Policy Search.
3. Search for the supplied Policy ID and open the matching policy record.
4. Extract policy coverage details (patient_name, insurer_name, policy_status,
   room_rent_limit, copay_percentage).
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
   (staged_diagnosis, staged_estimated_cost, staged_room_category, document_uploaded),
   and STOP without clicking 'Submit Pre-Authorization'.
8. Cross-check extracted policy data against authoritative synthetic fixtures (when available)
   and cross-check staged review-screen fields against the submitted case inputs. Never overwrite
   raw extracted values with expected values; report any mismatch as FIELD_MISMATCH (success = False).
"""

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse
from tinyfish import TinyFish, RunStatus

DEFAULT_PORTAL_URL = "https://medverify-tpa-portal.vercel.app/"
_ENV_FILE = Path(__file__).resolve().parent / ".env"

# Explicitly authorized mock TPA portal domains (Problem 4: domain restriction)
AUTHORIZED_PORTAL_HOSTS = {
    "medverify-tpa-portal.vercel.app",
}

# Authoritative synthetic fixture data from Arush's deployed mock portal (Problem 3)
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
        "policy_status",
        "room_rent_limit",
        "copay_percentage",
        "fields_prepared",
        "stopped_at_review",
        "notes",
    ],
}


def _build_failure_response(
    policy_id: str,
    portal_url: str,
    error_message: str,
    run_status: str = "FAILED",
    elapsed_seconds: float = 0.0,
    raw_result: Any = None,
) -> Dict[str, Any]:
    """Return a clean failure dictionary without inventing successful policy results."""
    return {
        "success": False,
        "run_status": run_status,
        "policy_id": policy_id,
        "portal_url": portal_url,
        "manual_fallback_url": portal_url or DEFAULT_PORTAL_URL,
        "elapsed_seconds": elapsed_seconds,
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
        "field_accuracy": {
            "verified": False,
            "fixture_source": "none",
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


def _evaluate_field_accuracy(
    policy_id: str,
    input_diagnosis: str,
    input_cost: str,
    input_room_category: str,
    expect_sample_doc: bool,
    extracted: Dict[str, Any],
    is_active_flow: bool,
) -> Dict[str, Any]:
    """
    Independently cross-check:
    1. Extracted policy values (patient_name, policy_status, room_rent_limit, copay_percentage)
       against AUTHORITATIVE_PORTAL_FIXTURES (when policy_id is in the known fixture set).
    2. Staged pre-authorization values on the Review & Verify screen (staged_diagnosis,
       staged_estimated_cost, staged_room_category, document_uploaded) against the
       submitted case inputs (when is_active_flow is True).

    Never overwrites raw extracted values with expected values. Any missing or mismatched
    value is recorded in discrepancies.
    """
    matched: List[str] = []
    policy_discrepancies: List[str] = []
    staging_discrepancies: List[str] = []

    pid_upper = policy_id.strip().upper()
    fixture = AUTHORITATIVE_PORTAL_FIXTURES.get(pid_upper)
    fixture_source = (
        f"AUTHORITATIVE_PORTAL_FIXTURES[{pid_upper}]"
        if fixture
        else "unlisted_policy_id (checked for non-empty extraction)"
    )

    ext_name = str(extracted.get("patient_name") or "").strip()
    ext_status = str(extracted.get("policy_status") or "").strip()
    ext_room = str(extracted.get("room_rent_limit") or "").strip()
    ext_copay = str(extracted.get("copay_percentage") or extracted.get("co_payment") or "").strip()

    if fixture:
        # 1. Patient Name check
        if ext_name and fixture["patient_name"].lower() in ext_name.lower():
            matched.append(f"patient_name == '{fixture['patient_name']}'")
        else:
            policy_discrepancies.append(
                f"patient_name mismatch: expected '{fixture['patient_name']}', extracted '{ext_name or 'None'}'"
            )

        # 2. Policy Status check
        if ext_status and fixture["policy_status"].lower() == ext_status.lower():
            matched.append(f"policy_status == '{fixture['policy_status']}'")
        else:
            policy_discrepancies.append(
                f"policy_status mismatch: expected '{fixture['policy_status']}', extracted '{ext_status or 'None'}'"
            )

        # 3. Room-Rent Limit check
        if ext_room and all(tok in ext_room.lower() for tok in fixture["room_rent_tokens"]):
            matched.append(f"room_rent_limit matches fixture ('{ext_room}')")
        else:
            policy_discrepancies.append(
                f"room_rent_limit mismatch: expected '{fixture['room_rent_limit']}', extracted '{ext_room or 'None'}'"
            )

        # 4. Co-Payment Percentage check
        if ext_copay and all(tok in ext_copay.lower() for tok in fixture["copay_tokens"]):
            matched.append(f"copay_percentage matches fixture ('{ext_copay}')")
        else:
            policy_discrepancies.append(
                f"copay_percentage mismatch: expected '{fixture['copay_percentage']}', extracted '{ext_copay or 'None'}'"
            )
    else:
        # For any custom policy ID that was reported found, require non-empty coverage fields
        for field_label, val in (
            ("patient_name", ext_name),
            ("policy_status", ext_status),
            ("room_rent_limit", ext_room),
            ("copay_percentage", ext_copay),
        ):
            if val:
                matched.append(f"{field_label} extracted ('{val}')")
            else:
                policy_discrepancies.append(f"{field_label} was not extracted from the portal")

    # Stage 2: Cross-check Review & Verify staged values against submitted case inputs
    if is_active_flow:
        staged_diag = str(extracted.get("staged_diagnosis") or "").strip()
        if staged_diag and (
            input_diagnosis.lower() in staged_diag.lower()
            or staged_diag.lower() in input_diagnosis.lower()
        ):
            matched.append(f"staged_diagnosis matches input ('{staged_diag}')")
        else:
            staging_discrepancies.append(
                f"staged_diagnosis mismatch: submitted '{input_diagnosis}', review screen showed '{staged_diag or 'None'}'"
            )

        staged_cost = str(extracted.get("staged_estimated_cost") or "").strip()
        if (
            staged_cost
            and _normalize_digits(staged_cost)
            and _normalize_digits(staged_cost) == _normalize_digits(input_cost)
        ):
            matched.append(f"staged_estimated_cost matches input ('{staged_cost}')")
        else:
            staging_discrepancies.append(
                f"staged_estimated_cost mismatch: submitted '{input_cost}', review screen showed '{staged_cost or 'None'}'"
            )

        staged_room_cat = str(extracted.get("staged_room_category") or "").strip()
        if staged_room_cat and staged_room_cat.lower() == input_room_category.lower():
            matched.append(f"staged_room_category matches input ('{staged_room_cat}')")
        else:
            staging_discrepancies.append(
                f"staged_room_category mismatch: submitted '{input_room_category}', review screen showed '{staged_room_cat or 'None'}'"
            )

        doc_up = str(extracted.get("document_uploaded") or "").strip()
        if expect_sample_doc:
            if doc_up and "sample_clinical_document.pdf" in doc_up.lower():
                matched.append(f"document_uploaded verified ('{doc_up}')")
            else:
                staging_discrepancies.append(
                    f"document_uploaded mismatch: expected 'sample_clinical_document.pdf', review screen showed '{doc_up or 'None'}'"
                )

    all_discrepancies = policy_discrepancies + staging_discrepancies
    return {
        "verified": len(all_discrepancies) == 0 and len(matched) > 0,
        "fixture_source": fixture_source,
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
) -> Dict[str, Any]:
    """
    Execute the confirmed MedVerify TinyFish workflow against the authorized mock TPA portal
    and perform independent verification of extracted policy coverage and staged review-screen fields.
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
        )

    url_error, url_status = _validate_portal_url(portal_url_clean)
    if url_error:
        return _build_failure_response(
            policy_id=policy_id_clean,
            portal_url=portal_url_clean,
            error_message=url_error,
            run_status=url_status,
            elapsed_seconds=round(time.perf_counter() - start_ts, 2),
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
        "blocks access, STOP immediately, set access_or_auth_blocked to true, policy_found to false, and explain in notes.\n"
        "1. Open the portal and navigate to 'Policy Search' (click 'Proceed to Policy Search' or 'Policy Search').\n"
        f"2. Enter Policy ID '{policy_id_clean}' into the Policy ID search input and click 'Search Policy'.\n"
        f"3. If an error alert appears stating Policy ID '{policy_id_clean}' was not found in TPA records, "
        "stop immediately on the Policy Search screen: set policy_found to false, policy_status to 'Not Found', "
        "current_portal_step to 'Policy Search', stopped_at_review to false, submitted_or_receipt_visible to false, "
        "access_or_auth_blocked to false, and do not invent any policy details.\n"
        "4. When the matching policy opens on 'Policy Details & Coverage Verification', extract the exact text shown on page for: "
        "patient_name, insurer_name, policy_status ('Active' or 'Lapsed'), room_rent_limit ('Room Rent Limit'), "
        "and copay_percentage ('Co-Payment Clause').\n"
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
        "'Review & Verify' screen into staged_diagnosis ('Diagnosis / ICD Code'), staged_estimated_cost ('Estimated Cost'), "
        "staged_room_category ('Room Category'), and document_uploaded ('Uploaded document name'), and set "
        "current_portal_step to 'Review & Verify'.\n"
        "10. STOP THERE on the 'Review & Verify' screen. Do NOT click 'Submit Pre-Authorization' under any circumstances. "
        "Set stopped_at_review to true, submitted_or_receipt_visible to false, and access_or_auth_blocked to false."
    )

    # 4. Run the TinyFish agent following the workshop guide pattern
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
        )

    elapsed_seconds = round(time.perf_counter() - start_ts, 2)

    # 5. Verify the run completed and returned a dictionary matching our schema
    status_name = getattr(run.status, "name", str(run.status))
    if run.status != RunStatus.COMPLETED:
        return _build_failure_response(
            policy_id=policy_id_clean,
            portal_url=portal_url_clean,
            error_message=f"TinyFish run did not complete (status: {status_name}).",
            run_status=status_name,
            elapsed_seconds=elapsed_seconds,
            raw_result=getattr(run, "result", None),
        )

    if not isinstance(run.result, dict):
        return _build_failure_response(
            policy_id=policy_id_clean,
            portal_url=portal_url_clean,
            error_message="TinyFish run completed, but did not return structured JSON.",
            run_status="INVALID_SCHEMA",
            elapsed_seconds=elapsed_seconds,
            raw_result=getattr(run, "result", None),
        )

    result = run.result
    policy_found = bool(result.get("policy_found", False))
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
    submitted_flag = bool(result.get("submitted_or_receipt_visible", False))
    access_blocked = bool(result.get("access_or_auth_blocked", False))
    notes = result.get("notes")

    fields_prepared = result.get("fields_prepared")
    if not isinstance(fields_prepared, list):
        fields_prepared = []

    # Check for authentication / CAPTCHA / MFA / access restriction (Problem 4)
    combined_notes = f"{notes or ''} {current_portal_step or ''}".lower()
    if access_blocked or any(
        tok in combined_notes
        for tok in ("captcha", "login required", "mfa", "two-factor", "access denied", "403 forbidden")
    ):
        return {
            "success": False,
            "run_status": "ACCESS_OR_AUTH_BLOCKED",
            "policy_id": policy_id_clean,
            "portal_url": portal_url_clean,
            "manual_fallback_url": portal_url_clean,
            "elapsed_seconds": elapsed_seconds,
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
            "field_accuracy": {
                "verified": False,
                "fixture_source": "none",
                "matched_checks": [],
                "policy_discrepancies": [],
                "staging_discrepancies": [],
                "discrepancies": ["Portal access or authentication barrier detected."],
            },
            "notes": notes,
            "error": (
                "Portal requires authentication, CAPTCHA, or restricted access. "
                "MedVerify never bypasses access controls; please use the manual portal fallback."
            ),
            "raw_result": result,
        }

    # Safety Gate 0: Check that the agent NEVER clicked Submit Pre-Authorization
    if submitted_flag:
        return {
            "success": False,
            "run_status": "SUBMISSION_VIOLATION",
            "policy_id": policy_id_clean,
            "portal_url": portal_url_clean,
            "manual_fallback_url": portal_url_clean,
            "elapsed_seconds": elapsed_seconds,
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
            "field_accuracy": {
                "verified": False,
                "fixture_source": "none",
                "matched_checks": [],
                "policy_discrepancies": [],
                "staging_discrepancies": ["Agent reported submitted_or_receipt_visible=True."],
                "discrepancies": ["Agent reported submitted_or_receipt_visible=True."],
            },
            "notes": notes,
            "error": "Safety violation: Agent reported that submission receipt screen was reached.",
            "raw_result": result,
        }

    # Case A: Unknown / Not Found Policy ID -> Must NOT appear as successful verification
    if not policy_found or (policy_status and policy_status.strip().lower() == "not found"):
        pid_upper = policy_id_clean.upper()
        known_fixture = AUTHORITATIVE_PORTAL_FIXTURES.get(pid_upper)
        if known_fixture:
            # A known policy ID was unexpectedly reported as Not Found!
            return {
                "success": False,
                "run_status": "FIELD_MISMATCH",
                "policy_id": policy_id_clean,
                "portal_url": portal_url_clean,
                "manual_fallback_url": portal_url_clean,
                "elapsed_seconds": elapsed_seconds,
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
                "field_accuracy": {
                    "verified": False,
                    "fixture_source": f"AUTHORITATIVE_PORTAL_FIXTURES[{pid_upper}]",
                    "matched_checks": [],
                    "policy_discrepancies": [
                        f"Known policy '{pid_upper}' ({known_fixture['patient_name']}) was reported as Not Found."
                    ],
                    "staging_discrepancies": [],
                    "discrepancies": [
                        f"Known policy '{pid_upper}' ({known_fixture['patient_name']}) was reported as Not Found."
                    ],
                },
                "notes": notes,
                "error": f"Extraction mismatch: Known policy '{pid_upper}' was reported as Not Found.",
                "raw_result": result,
            }

        return {
            "success": False,
            "run_status": "NOT_FOUND",
            "policy_id": policy_id_clean,
            "portal_url": portal_url_clean,
            "manual_fallback_url": portal_url_clean,
            "elapsed_seconds": elapsed_seconds,
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
            "field_accuracy": {
                "verified": True,
                "fixture_source": "unknown_policy_rule",
                "matched_checks": ["unknown_policy_correctly_rejected"],
                "policy_discrepancies": [],
                "staging_discrepancies": [],
                "discrepancies": [],
            },
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
            is_active_flow=False,
        )
        # If a lapsed policy had a field mismatch against its fixture, surface FIELD_MISMATCH
        run_code = "POLICY_LAPSED" if accuracy_report["verified"] else "FIELD_MISMATCH"
        err_msg = (
            f"Policy '{policy_id_clean}' status is {policy_status}. "
            "Cashless pre-authorization cannot be initiated for a lapsed policy."
            if accuracy_report["verified"]
            else "Policy extraction mismatch on lapsed policy: " + "; ".join(accuracy_report["discrepancies"])
        )
        return {
            "success": False,
            "run_status": run_code,
            "policy_id": policy_id_clean,
            "portal_url": portal_url_clean,
            "manual_fallback_url": portal_url_clean,
            "elapsed_seconds": elapsed_seconds,
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
            "field_accuracy": accuracy_report,
            "notes": notes or (
                f"Policy '{policy_id_clean}' is {policy_status}. "
                "Cashless pre-authorization is prohibited and form staging was halted."
            ),
            "error": err_msg,
            "raw_result": result,
        }

    # Case C: Active policy — check workflow completion evidence FIRST, then field accuracy
    accuracy_report = _evaluate_field_accuracy(
        policy_id=policy_id_clean,
        input_diagnosis=diagnosis_clean,
        input_cost=cost_clean,
        input_room_category=room_cat_clean,
        expect_sample_doc=use_sample_document,
        extracted=result,
        is_active_flow=True,
    )

    has_required_coverage = bool(
        _is_active_status(policy_status) and room_rent_limit and copay_val
    )
    form_prepared = len(fields_prepared) > 0
    step_ok = bool(current_portal_step and "review" in current_portal_step.lower())
    doc_ok = bool(not use_sample_document or (document_uploaded and "sample_clinical_document.pdf" in document_uploaded.lower()))

    if not has_required_coverage or not form_prepared or not stopped_at_review or not step_ok or not doc_ok:
        missing_reasons = []
        if not _is_active_status(policy_status):
            missing_reasons.append(f"unexpected policy_status '{policy_status}'")
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

        reason_str = ", ".join(missing_reasons)
        return {
            "success": False,
            "run_status": "INCOMPLETE_WORKFLOW",
            "policy_id": policy_id_clean,
            "portal_url": portal_url_clean,
            "manual_fallback_url": portal_url_clean,
            "elapsed_seconds": elapsed_seconds,
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
            "field_accuracy": accuracy_report,
            "notes": notes,
            "error": f"Incomplete verification workflow ({reason_str}). Manual coordinator review required.",
            "raw_result": result,
        }

    # Case D: Check for any policy extraction mismatch or staged form field mismatch (Problem 3 & 5)
    if not accuracy_report["verified"]:
        mismatch_summary = "; ".join(accuracy_report["discrepancies"])
        return {
            "success": False,
            "run_status": "FIELD_MISMATCH",
            "policy_id": policy_id_clean,
            "portal_url": portal_url_clean,
            "manual_fallback_url": portal_url_clean,
            "elapsed_seconds": elapsed_seconds,
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
            "stopped_at_review": stopped_at_review,
            "submitted": False,
            "field_accuracy": accuracy_report,
            "notes": notes,
            "error": f"Field verification mismatch detected: {mismatch_summary}",
            "raw_result": result,
        }

    # Case E: Genuine Success — Policy found, Active, coverage & staged fields verified,
    # synthetic document staged, Review & Verify reached, and no submission occurred.
    return {
        "success": True,
        "run_status": status_name,
        "policy_id": policy_id_clean,
        "portal_url": portal_url_clean,
        "manual_fallback_url": portal_url_clean,
        "elapsed_seconds": elapsed_seconds,
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
        "field_accuracy": accuracy_report,
        "notes": notes,
        "error": None,
        "raw_result": result,
    }
