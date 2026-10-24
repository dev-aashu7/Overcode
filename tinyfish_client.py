"""
tinyfish_client.py
------------------
Beginner-friendly TinyFish SDK helper for the MedVerify Streamlit app.

Follows the TinyFish Workshop Guide pattern:
- Reads TINYFISH_API_KEY from the environment.
- Uses TinyFish().agent.run(url=..., goal=..., output_schema=...).
- Checks RunStatus.COMPLETED before reading run.result.
- Never fabricates policy data on failure and never auto-submits forms.
"""

import os
from typing import Any, Dict
from tinyfish import TinyFish, RunStatus


# Structured JSON template so every TinyFish run returns consistent fields
POLICY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "policy_found": {
            "type": "boolean",
            "description": "True if the synthetic policy ID was found on the portal.",
        },
        "policy_status": {
            "type": "string",
            "description": "Extracted policy status (for example: Active, Expired, Inactive, or Not Found).",
        },
        "room_rent_limit": {
            "type": "string",
            "description": "Extracted room-rent limit or cap from the policy details.",
        },
        "copay_percentage": {
            "type": "string",
            "description": "Extracted co-payment percentage from the policy details.",
        },
        "fields_prepared": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of pre-authorization form fields that were filled in.",
        },
        "stopped_at_review": {
            "type": "boolean",
            "description": "True if the agent stopped at the review screen without submitting the form.",
        },
        "notes": {
            "type": "string",
            "description": "Brief summary of what was found and prepared on the portal.",
        },
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
        "policy_status": None,
        "room_rent_limit": None,
        "copay_percentage": None,
        "fields_prepared": [],
        "stopped_at_review": False,
        "submitted": False,
        "notes": None,
        "error": error_message,
        "raw_result": raw_result,
    }


def verify_policy(
    policy_id: str,
    diagnosis: str,
    estimated_cost: float | int | str,
    portal_url: str,
) -> Dict[str, Any]:
    """
    Look up a synthetic insurance policy on the given portal URL, extract coverage
    details, pre-fill supported pre-authorization form fields, and stop at the
    review screen without submitting.

    Parameters:
        policy_id (str): Synthetic policy ID to look up (e.g., "POL-1001").
        diagnosis (str): Diagnosis description or ICD-10 code.
        estimated_cost (float | int | str): Estimated treatment cost.
        portal_url (str): URL of the sandbox/test insurance portal.

    Returns:
        dict: Structured dictionary suitable for display in Streamlit (app.py).
    """
    policy_id_clean = str(policy_id).strip() if policy_id is not None else ""
    diagnosis_clean = str(diagnosis).strip() if diagnosis is not None else ""
    cost_clean = str(estimated_cost).strip() if estimated_cost is not None else ""
    portal_url_clean = str(portal_url).strip() if portal_url is not None else ""

    # 1. Check that TINYFISH_API_KEY is set in the environment
    if not os.getenv("TINYFISH_API_KEY"):
        return _build_failure_response(
            policy_id=policy_id_clean,
            portal_url=portal_url_clean,
            error_message=(
                "TINYFISH_API_KEY environment variable is not set. "
                "Set it in your terminal before running MedVerify."
            ),
            run_status="MISSING_API_KEY",
        )

    # 2. Validate required inputs
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

    # 3. Build a clear plain-English goal for the TinyFish web agent
    goal = (
        f"1. Look up the synthetic insurance policy ID '{policy_id_clean}' on this portal. "
        "2. Extract the policy status, room-rent limit, and co-payment percentage. "
        "3. If the policy is found and a pre-authorization form is available, fill in the "
        f"supported pre-authorization fields using Policy ID '{policy_id_clean}', "
        f"Diagnosis '{diagnosis_clean}', and Estimated Cost '{cost_clean}'. "
        "4. Proceed to the pre-authorization review screen and STOP there. "
        "5. NEVER click the final submit button or submit the form. "
        "6. If the policy ID is not found or an error occurs on the page, report "
        "policy_found as false and do not invent policy details."
    )

    # 4. Run the TinyFish agent following the workshop guide pattern
    try:
        client = TinyFish()  # Reads TINYFISH_API_KEY from environment
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
            run_status=status_name,
            raw_result=getattr(run, "result", None),
        )

    result = run.result
    policy_found = bool(result.get("policy_found", False))

    # If the policy wasn't found on the portal, report cleanly without inventing data
    if not policy_found:
        return {
            "success": False,
            "run_status": status_name,
            "policy_id": policy_id_clean,
            "portal_url": portal_url_clean,
            "policy_found": False,
            "policy_status": result.get("policy_status") or "Not Found",
            "room_rent_limit": None,
            "copay_percentage": None,
            "fields_prepared": [],
            "stopped_at_review": False,
            "submitted": False,
            "notes": result.get("notes") or f"Policy '{policy_id_clean}' was not found on the portal.",
            "error": f"Policy '{policy_id_clean}' was not found on the portal.",
            "raw_result": result,
        }

    fields_prepared = result.get("fields_prepared")
    if not isinstance(fields_prepared, list):
        fields_prepared = []

    return {
        "success": True,
        "run_status": status_name,
        "policy_id": policy_id_clean,
        "portal_url": portal_url_clean,
        "policy_found": True,
        "policy_status": result.get("policy_status"),
        "room_rent_limit": result.get("room_rent_limit"),
        "copay_percentage": result.get("copay_percentage"),
        "fields_prepared": fields_prepared,
        "stopped_at_review": bool(result.get("stopped_at_review", False)),
        "submitted": False,
        "notes": result.get("notes"),
        "error": None,
        "raw_result": result,
    }
