"""
tinyfish_client.py
------------------
TinyFish SDK helper for the MedVerify application.

Confirmed Portal & Workflow (https://medverify-tpa-portal.vercel.app/):
1. Open the portal.
2. Navigate to Policy Search.
3. Search for the supplied Policy ID and open the matching policy.
4. Extract the policy details (patient_name, policy_status, room_rent_limit, copay_percentage).
5. If Active: Initiate Pre-Authorization.
6. Fill the supported pre-authorization fields (Provisional Diagnosis / ICD Code, Estimated Cost).
7. Continue to Document Upload and select/use the available synthetic sample document.
8. Navigate to Review & Verify.
9. STOP without clicking Submit Pre-Authorization.

Safety & Integrity Guarantees:
- Reads TINYFISH_API_KEY from the environment (never hardcoded).
- Uses TinyFish().agent.run(url=..., goal=..., output_schema=...).
- Never fabricates policy data on failure and never auto-submits forms (submitted = False).
- Lapsed, unknown, failed, or incomplete runs return success = False so they never
  appear as successful verifications.
"""

import os
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse
from tinyfish import TinyFish, RunStatus

DEFAULT_PORTAL_URL = "https://medverify-tpa-portal.vercel.app/"
_ENV_FILE = Path(__file__).resolve().parent / ".env"


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

# Structured JSON schema for TinyFish output extraction (no 'description' keys per TinyFish API validator)
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
        "stopped_at_review": {"type": "boolean"},
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
    raw_result: Any = None,
) -> Dict[str, Any]:
    """Return a clean failure dictionary without inventing successful policy results."""
    return {
        "success": False,
        "run_status": run_status,
        "policy_id": policy_id,
        "portal_url": portal_url,
        "policy_found": False,
        "patient_name": None,
        "insurer_name": None,
        "policy_status": None,
        "room_rent_limit": None,
        "copay_percentage": None,
        "co_payment": None,
        "fields_prepared": [],
        "document_uploaded": None,
        "form_prepared": False,
        "stopped_at_review": False,
        "submitted": False,
        "notes": None,
        "error": error_message,
        "raw_result": raw_result,
    }


def _validate_portal_url(portal_url: str) -> str | None:
    """
    Check that portal_url is a valid HTTP/HTTPS URL and not a local-only address
    that the TinyFish cloud browser cannot reach. Returns an error message or None.
    """
    parsed = urlparse(portal_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return (
            "Invalid portal_url. Please enter a full URL starting with "
            "'https://' or 'http://'."
        )

    hostname = (parsed.hostname or "").lower()
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return (
            "Localhost URLs are not reachable by the TinyFish cloud browser. "
            "Please provide a publicly accessible portal URL such as "
            f"{DEFAULT_PORTAL_URL}"
        )

    return None


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


def verify_policy(
    policy_id: str,
    diagnosis: str,
    estimated_cost: float | int | str,
    portal_url: str = DEFAULT_PORTAL_URL,
) -> Dict[str, Any]:
    """
    Execute the confirmed MedVerify TinyFish workflow against the TPA portal:
    1. Open the portal and navigate to Policy Search.
    2. Search for policy_id and open the matching policy.
    3. Extract policy details (status, room-rent limit, co-payment, patient name).
    4. If Active, initiate Pre-Authorization, fill diagnosis and estimated_cost,
       continue to Document Upload, attach the sample document, navigate to
       Review & Verify, and STOP without clicking Submit Pre-Authorization.
    """
    policy_id_clean = str(policy_id).strip() if policy_id is not None else ""
    diagnosis_clean = str(diagnosis).strip() if diagnosis is not None else ""
    cost_clean = str(estimated_cost).strip() if estimated_cost is not None else ""
    portal_url_clean = str(portal_url).strip() if portal_url is not None else ""

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
        )

    url_error = _validate_portal_url(portal_url_clean)
    if url_error:
        return _build_failure_response(
            policy_id=policy_id_clean,
            portal_url=portal_url_clean,
            error_message=url_error,
            run_status="INVALID_URL",
        )

    # 2. Check that TINYFISH_API_KEY is set in the environment (or .env file)
    load_env_file()
    if not os.getenv("TINYFISH_API_KEY"):
        return _build_failure_response(
            policy_id=policy_id_clean,
            portal_url=portal_url_clean,
            error_message=(
                "TINYFISH_API_KEY environment variable is not set. "
                "Set it in your terminal before running live TinyFish verification."
            ),
            run_status="MISSING_API_KEY",
        )

    # 3. Build the confirmed step-by-step goal for the TinyFish web agent
    goal = (
        "Follow this exact workflow on the ApexCare Health TPA portal:\n"
        "1. Open the portal and navigate to 'Policy Search' (click 'Proceed to Policy Search' or 'Policy Search').\n"
        f"2. Enter Policy ID '{policy_id_clean}' into the Policy ID search input and click 'Search Policy'.\n"
        f"3. If an error alert appears stating Policy ID '{policy_id_clean}' was not found in TPA records, "
        "stop immediately, set policy_found to false, policy_status to 'Not Found', stopped_at_review to false, "
        "and do not invent any policy details.\n"
        "4. When the matching policy opens on the 'Policy Details & Coverage Verification' screen, extract: "
        "patient_name, insurer_name, policy_status ('Active' or 'Lapsed'), room_rent_limit ('Room Rent Limit'), "
        "and copay_percentage ('Co-Payment Clause').\n"
        "5. If policy_status is 'Lapsed' (or inactive/expired), STOP on the Policy Details screen. "
        "Do NOT initiate Pre-Authorization. Return the extracted details with fields_prepared as [] and "
        "stopped_at_review as false.\n"
        "6. If policy_status is 'Active', click 'Initiate Pre-Authorization' to open the Pre-Authorization Form.\n"
        f"7. On the Pre-Authorization Form, fill 'Provisional Diagnosis / ICD Code' with '{diagnosis_clean}' "
        f"and 'Estimated Cost' with '{cost_clean}' (keep the pre-filled Hospital Name, Treating Doctor, "
        "Proposed Admission Date, and Room Category valid).\n"
        "8. Click 'Next: Document Upload' to proceed to the Clinical Document Upload step.\n"
        "9. Ensure 'Use Sample Document' (sample_clinical_document.pdf) is checked/selected, then click 'Proceed to Review'.\n"
        "10. Confirm that the 'Review & Verify' screen is visible and STOP THERE.\n"
        "11. Do NOT click 'Submit Pre-Authorization' under any circumstances. Set stopped_at_review to true."
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
        return _build_failure_response(
            policy_id=policy_id_clean,
            portal_url=portal_url_clean,
            error_message=f"TinyFish SDK error: {exc}",
            run_status="EXCEPTION",
        )

    # 5. Verify the run completed and returned a dictionary matching our schema
    status_name = getattr(run.status, "name", str(run.status))
    if run.status != RunStatus.COMPLETED:
        return _build_failure_response(
            policy_id=policy_id_clean,
            portal_url=portal_url_clean,
            error_message=f"TinyFish run did not complete (status: {status_name}).",
            run_status=status_name,
            raw_result=getattr(run, "result", None),
        )

    if not isinstance(run.result, dict):
        return _build_failure_response(
            policy_id=policy_id_clean,
            portal_url=portal_url_clean,
            error_message="TinyFish run completed, but did not return structured JSON.",
            run_status="INVALID_SCHEMA",
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
    stopped_at_review = bool(result.get("stopped_at_review", False))
    notes = result.get("notes")

    fields_prepared = result.get("fields_prepared")
    if not isinstance(fields_prepared, list):
        fields_prepared = []

    # Case A: Unknown / Not Found Policy ID -> Must NOT appear as successful verification
    if not policy_found or (policy_status and policy_status.strip().lower() == "not found"):
        return {
            "success": False,
            "run_status": "NOT_FOUND",
            "policy_id": policy_id_clean,
            "portal_url": portal_url_clean,
            "policy_found": False,
            "patient_name": None,
            "insurer_name": None,
            "policy_status": "Not Found",
            "room_rent_limit": None,
            "copay_percentage": None,
            "co_payment": None,
            "fields_prepared": [],
            "document_uploaded": None,
            "form_prepared": False,
            "stopped_at_review": False,
            "submitted": False,
            "notes": notes or f"Policy '{policy_id_clean}' was not found in TPA portal records.",
            "error": f"Policy '{policy_id_clean}' was not found in TPA portal records.",
            "raw_result": result,
        }

    # Case B: Lapsed / Expired / Inactive Policy -> Extracted details preserved, but success = False
    if _is_inactive_status(policy_status):
        return {
            "success": False,
            "run_status": "POLICY_LAPSED",
            "policy_id": policy_id_clean,
            "portal_url": portal_url_clean,
            "policy_found": True,
            "patient_name": patient_name,
            "insurer_name": insurer_name,
            "policy_status": policy_status,
            "room_rent_limit": room_rent_limit,
            "copay_percentage": copay_val,
            "co_payment": copay_val,
            "fields_prepared": [],
            "document_uploaded": None,
            "form_prepared": False,
            "stopped_at_review": False,
            "submitted": False,
            "notes": notes or (
                f"Policy '{policy_id_clean}' is {policy_status}. "
                "Cashless pre-authorization is prohibited and form staging was halted."
            ),
            "error": (
                f"Policy '{policy_id_clean}' status is {policy_status}. "
                "Cashless pre-authorization cannot be initiated for a lapsed policy."
            ),
            "raw_result": result,
        }

    # Case C: Incomplete workflow (e.g., missing coverage fields, not Active, or did not halt at Review & Verify)
    has_required_coverage = bool(
        _is_active_status(policy_status) and room_rent_limit and copay_val
    )
    form_prepared = len(fields_prepared) > 0

    if not has_required_coverage or not form_prepared or not stopped_at_review:
        missing_reasons = []
        if not _is_active_status(policy_status):
            missing_reasons.append(f"unexpected policy_status '{policy_status}'")
        if not room_rent_limit:
            missing_reasons.append("missing room_rent_limit")
        if not copay_val:
            missing_reasons.append("missing copay_percentage")
        if not form_prepared:
            missing_reasons.append("pre-authorization fields were not staged")
        if not stopped_at_review:
            missing_reasons.append("agent did not confirm stopping at Review & Verify")

        reason_str = ", ".join(missing_reasons)
        return {
            "success": False,
            "run_status": "INCOMPLETE_WORKFLOW",
            "policy_id": policy_id_clean,
            "portal_url": portal_url_clean,
            "policy_found": True,
            "patient_name": patient_name,
            "insurer_name": insurer_name,
            "policy_status": policy_status,
            "room_rent_limit": room_rent_limit,
            "copay_percentage": copay_val,
            "co_payment": copay_val,
            "fields_prepared": fields_prepared,
            "document_uploaded": document_uploaded,
            "form_prepared": form_prepared,
            "stopped_at_review": stopped_at_review,
            "submitted": False,
            "notes": notes,
            "error": f"Incomplete verification workflow ({reason_str}). Manual coordinator review required.",
            "raw_result": result,
        }

    # Case D: Active policy + coverage extracted + form & sample doc staged + stopped at Review & Verify
    return {
        "success": True,
        "run_status": status_name,
        "policy_id": policy_id_clean,
        "portal_url": portal_url_clean,
        "policy_found": True,
        "patient_name": patient_name,
        "insurer_name": insurer_name,
        "policy_status": policy_status,
        "room_rent_limit": room_rent_limit,
        "copay_percentage": copay_val,
        "co_payment": copay_val,
        "fields_prepared": fields_prepared,
        "document_uploaded": document_uploaded or "sample_clinical_document.pdf",
        "form_prepared": True,
        "stopped_at_review": True,
        "submitted": False,
        "notes": notes,
        "error": None,
        "raw_result": result,
    }
