"""
playwright_fallback.py
----------------------
Optional local headed-Chromium Playwright fallback for MedVerify.

STRICT OPERATING RULES:
1. Invoked ONLY when the TinyFish cloud run returns ACCESS_OR_AUTH_BLOCKED and the
   coordinator has enabled the local fallback.
2. Target URL must pass the authorized mock TPA portal allowlist check.
3. Launches standard headed Chromium (headless=False). NEVER uses stealth plugins,
   fingerprint spoofing, user-agent tampering, or proxies.
4. When a CAPTCHA, login, MFA, or verification check is detected, the script pauses
   and emits status 'Waiting for human check' so a human coordinator can complete the
   check in the visible browser window. It NEVER attempts to solve, bypass, or evade
   any verification challenge.
5. Automatically resumes once a known post-check portal element appears (e.g., the
   'Policy Search' heading or 'Proceed to Policy Search' button). If the configurable
   timeout (default 300s / 5 minutes) expires first, halts with run_status = 'HUMAN_CHECK_TIMEOUT'.
6. Reuses the exact same case inputs and stops at 'Review & Verify'. NEVER clicks
   'Submit Pre-Authorization'.
"""

import os
import time
from typing import Any, Callable, Dict

DEFAULT_HUMAN_CHECK_TIMEOUT_SECONDS = float(
    os.getenv("MEDVERIFY_HUMAN_CHECK_TIMEOUT", "300")
)
DEFAULT_POLL_INTERVAL_SECONDS = 1.0

# Known challenge / verification tokens that require a human in the visible browser window
HUMAN_CHECK_INDICATORS = (
    "captcha",
    "verify you are human",
    "security check",
    "checking your browser",
    "just a moment",
    "attention required",
    "cloudflare",
    "login required",
    "two-factor",
    "mfa challenge",
    "human verification",
)

# Known post-check portal landmarks on the authorized mock TPA portal
POST_CHECK_PORTAL_MARKERS = (
    "policy search",
    "proceed to policy search",
    "apexcare health tpa",
    "cashless insurance pre-authorization",
)


def _get_page_text_lower(page: Any) -> str:
    """Safely read visible text content from a Playwright Page or stubbed page."""
    try:
        if hasattr(page, "get_visible_text"):
            return str(page.get_visible_text() or "").lower()
        if hasattr(page, "content"):
            return str(page.content() or "").lower()
    except Exception:
        pass
    return ""


def _is_verification_check_present(page: Any) -> bool:
    """
    Return True if the page currently displays a CAPTCHA, human verification, or auth check.
    Never interacts with or attempts to bypass the check.
    """
    if hasattr(page, "is_check_present") and callable(page.is_check_present):
        return bool(page.is_check_present())

    text_lower = _get_page_text_lower(page)
    return any(token in text_lower for token in HUMAN_CHECK_INDICATORS)


def _is_post_check_portal_ready(page: Any) -> bool:
    """
    Return True when a known post-check element from the authorized mock TPA portal
    (such as the 'Policy Search' heading or 'Proceed to Policy Search' action) is present
    and no verification challenge is blocking the page.
    """
    if _is_verification_check_present(page):
        return False

    if hasattr(page, "is_post_check_ready") and callable(page.is_post_check_ready):
        return bool(page.is_post_check_ready())

    try:
        if hasattr(page, "locator"):
            heading_loc = page.locator("text=/Policy Search|Proceed to Policy Search/i")
            if hasattr(heading_loc, "count") and heading_loc.count() > 0:
                if hasattr(heading_loc.first, "is_visible"):
                    if heading_loc.first.is_visible():
                        return True
                else:
                    return True
    except Exception:
        pass

    text_lower = _get_page_text_lower(page)
    return any(marker in text_lower for marker in POST_CHECK_PORTAL_MARKERS)


def wait_for_human_check_if_needed(
    page: Any,
    timeout_seconds: float = DEFAULT_HUMAN_CHECK_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    status_callback: Callable[[str, str], None] | None = None,
) -> Dict[str, Any]:
    """
    Check whether the page is blocked by a human verification / CAPTCHA check.
    - If no check is present and the portal landmark ('Policy Search') is ready,
      returns immediately with {'paused_for_human': False, 'timed_out': False}.
    - If a check is detected (or portal landmark is not yet accessible due to a check),
      emits status 'Waiting for human check' via status_callback and pauses without
      touching the page until a human completes the check and the post-check element
      ('Policy Search' heading) appears.
    - If timeout_seconds expires before the post-check element appears, returns
      {'paused_for_human': True, 'timed_out': True, 'run_status': 'HUMAN_CHECK_TIMEOUT'}.
    """
    if _is_post_check_portal_ready(page):
        return {
            "paused_for_human": False,
            "timed_out": False,
            "waited_seconds": 0.0,
            "status_history": ["PORTAL_READY"],
        }

    # A verification check is present (or blocking the post-check portal element)
    status_history = [" Waiting for human check".strip()]
    if status_callback:
        status_callback(
            "WAITING_FOR_HUMAN_CHECK",
            "Waiting for human check",
        )

    start_wait = time.perf_counter()
    deadline = start_wait + max(float(timeout_seconds), 0.01)

    while True:
        if _is_post_check_portal_ready(page):
            waited = round(time.perf_counter() - start_wait, 2)
            status_history.append("RESUMED_AFTER_HUMAN_CHECK")
            if status_callback:
                status_callback(
                    "RUNNING_PLAYWRIGHT_FALLBACK",
                    "Human check completed; resuming portal workflow",
                )
            return {
                "paused_for_human": True,
                "timed_out": False,
                "waited_seconds": waited,
                "status_history": status_history,
            }

        now = time.perf_counter()
        if now >= deadline:
            waited = round(now - start_wait, 2)
            status_history.append("HUMAN_CHECK_TIMEOUT")
            return {
                "paused_for_human": True,
                "timed_out": True,
                "waited_seconds": waited,
                "run_status": "HUMAN_CHECK_TIMEOUT",
                "status_history": status_history,
            }

        sleep_for = min(poll_interval_seconds, max(0.01, deadline - now))
        if hasattr(page, "wait_for_timeout"):
            page.wait_for_timeout(int(sleep_for * 1000))
        else:
            time.sleep(sleep_for)


def execute_playwright_workflow_on_page(
    page: Any,
    policy_id: str,
    diagnosis: str,
    estimated_cost: float | int | str,
    room_category: str = "Semi-Private",
    hospital_name: str = "Apollo Care Superspecialty Hospital",
    doctor_name: str = "Dr. Rajesh K. Mehta",
    use_sample_document: bool = True,
    human_check_timeout_seconds: float = DEFAULT_HUMAN_CHECK_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    status_callback: Callable[[str, str], None] | None = None,
) -> Dict[str, Any]:
    """
    Execute the portal workflow on a Playwright Page (or stubbed test page):
    1. Pause if a verification/CAPTCHA check is present ('Waiting for human check');
       resume automatically when a post-check element ('Policy Search' heading) appears,
       or return HUMAN_CHECK_TIMEOUT if timeout expires.
    2. Navigate Policy Search -> Policy Details -> Pre-Authorization Form ->
       Document Upload -> Review & Verify using the supplied case inputs.
    3. Stop at Review & Verify and NEVER click 'Submit Pre-Authorization'.
    """
    wait_outcome = wait_for_human_check_if_needed(
        page=page,
        timeout_seconds=human_check_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        status_callback=status_callback,
    )

    if wait_outcome.get("timed_out"):
        return {
            "timed_out": True,
            "run_status": "HUMAN_CHECK_TIMEOUT",
            "paused_for_human": True,
            "waited_seconds": wait_outcome.get("waited_seconds", 0.0),
            "status_history": wait_outcome.get("status_history", []),
            "error": (
                f"Human verification check was not completed within the configured timeout "
                f"({human_check_timeout_seconds}s). Halting safely without bypassing access controls."
            ),
            "extracted": None,
        }

    # If the page is a test stub providing execute_portal_steps(), delegate the DOM step simulation
    if hasattr(page, "execute_portal_steps") and callable(page.execute_portal_steps):
        extracted = page.execute_portal_steps(
            policy_id=policy_id,
            diagnosis=diagnosis,
            estimated_cost=estimated_cost,
            room_category=room_category,
            hospital_name=hospital_name,
            doctor_name=doctor_name,
            use_sample_document=use_sample_document,
        )
        return {
            "timed_out": False,
            "run_status": "COMPLETED",
            "paused_for_human": wait_outcome.get("paused_for_human", False),
            "waited_seconds": wait_outcome.get("waited_seconds", 0.0),
            "status_history": wait_outcome.get("status_history", []),
            "error": None,
            "extracted": extracted,
        }

    # Real Playwright Page DOM interaction against https://medverify-tpa-portal.vercel.app/
    # Step 1: Navigate to Policy Search if currently on Home screen
    proceed_btn = page.locator("button:has-text('Proceed to Policy Search'), a:has-text('Policy Search')")
    if proceed_btn.count() > 0 and proceed_btn.first.is_visible():
        proceed_btn.first.click()

    page.locator("text=/Policy Search/i").first.wait_for(state="visible", timeout=15000)

    # Step 2: Enter Policy ID and click Search Policy
    search_input = page.locator("#policy-search-input, input[placeholder*='POL-'], input[type='text']").first
    search_input.fill(str(policy_id).strip())
    search_btn = page.locator("#btn-search-policy, button:has-text('Search Policy')").first
    search_btn.click()

    page.wait_for_timeout(600)

    # Step 3: Check for Not Found alert on Policy Search
    body_text = _get_page_text_lower(page)
    if "not found" in body_text and "policy details" not in body_text:
        return {
            "timed_out": False,
            "run_status": "COMPLETED",
            "paused_for_human": wait_outcome.get("paused_for_human", False),
            "waited_seconds": wait_outcome.get("waited_seconds", 0.0),
            "status_history": wait_outcome.get("status_history", []),
            "error": None,
            "extracted": {
                "policy_found": False,
                "extracted_policy_id": "",
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
                "notes": f"Playwright local fallback: Policy ID '{policy_id}' not found on Policy Search.",
            },
        }

    # Step 4: Extract Policy Details
    def _read_selector_text(sel: str, default: str = "") -> str:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                return str(loc.first.inner_text()).strip()
        except Exception:
            pass
        return default

    extracted_pid = _read_selector_text("#detail-policy-id, [data-testid='policy-id']", str(policy_id).strip())
    patient_name = _read_selector_text("#detail-patient-name, [data-testid='patient-name']")
    insurer_name = _read_selector_text("#detail-insurer-name, [data-testid='insurer-name']")
    policy_status = _read_selector_text("#detail-policy-status, [data-testid='policy-status']")
    room_rent_limit = _read_selector_text("#detail-room-rent, [data-testid='room-rent-limit']")
    copay_percentage = _read_selector_text("#detail-copay, [data-testid='copay-percentage']")

    if "lapsed" in policy_status.lower() or "inactive" in policy_status.lower():
        return {
            "timed_out": False,
            "run_status": "COMPLETED",
            "paused_for_human": wait_outcome.get("paused_for_human", False),
            "waited_seconds": wait_outcome.get("waited_seconds", 0.0),
            "status_history": wait_outcome.get("status_history", []),
            "error": None,
            "extracted": {
                "policy_found": True,
                "extracted_policy_id": extracted_pid,
                "patient_name": patient_name,
                "insurer_name": insurer_name,
                "policy_status": policy_status,
                "room_rent_limit": room_rent_limit,
                "copay_percentage": copay_percentage,
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
                    f"Playwright local fallback: Policy {extracted_pid} is {policy_status}; "
                    "stopped at Policy Details without initiating pre-authorization."
                ),
            },
        }

    # Step 5: Active policy -> Click Initiate Pre-Authorization
    init_btn = page.locator("#btn-initiate-preauth, button:has-text('Initiate Pre-Authorization')").first
    init_btn.click()

    # Step 6: Fill Pre-Authorization Form using the exact same case inputs
    hosp_input = page.locator("#input-hospital-name, input[name='hospitalName']")
    if hosp_input.count() > 0:
        hosp_input.first.fill(str(hospital_name))

    doc_input = page.locator("#input-doctor-name, input[name='doctorName']")
    if doc_input.count() > 0:
        doc_input.first.fill(str(doctor_name))

    diag_input = page.locator("#input-diagnosis, input[name='diagnosis'], textarea[name='diagnosis']").first
    diag_input.fill(str(diagnosis))

    cost_input = page.locator("#input-estimated-cost, input[name='estimatedCost'], input[type='number']").first
    cost_input.fill(str(estimated_cost))

    room_select = page.locator("#select-room-category, select[name='roomCategory']")
    if room_select.count() > 0:
        room_select.first.select_option(label=str(room_category))

    next_doc_btn = page.locator("#btn-next-doc-upload, button:has-text('Next: Document Upload'), button:has-text('Document Upload')").first
    next_doc_btn.click()

    # Step 7: Document Upload -> attach sample_clinical_document.pdf and Proceed to Review
    if use_sample_document:
        sample_chk = page.locator("#chk-sample-doc, input[type='checkbox'], button:has-text('Use Sample Document')")
        if sample_chk.count() > 0:
            first_chk = sample_chk.first
            try:
                if hasattr(first_chk, "is_checked") and not first_chk.is_checked():
                    first_chk.check()
            except Exception:
                first_chk.click()

    proceed_review_btn = page.locator("#btn-proceed-review, button:has-text('Proceed to Review')").first
    proceed_review_btn.click()

    # Step 8: Wait for Review & Verify screen and read back staged values
    page.locator("text=/Review & Verify/i").first.wait_for(state="visible", timeout=15000)

    review_pid = _read_selector_text("#review-policy-id", extracted_pid)
    staged_diag = _read_selector_text("#review-diagnosis", str(diagnosis))
    staged_cost = _read_selector_text("#review-estimated-cost", str(estimated_cost))
    staged_room = _read_selector_text("#review-room-category", str(room_category))
    staged_doc = _read_selector_text(
        "#review-document-name",
        "sample_clinical_document.pdf" if use_sample_document else "",
    )

    # Step 9: STOP at Review & Verify. NEVER click #btn-submit-preauth ('Submit Pre-Authorization').
    return {
        "timed_out": False,
        "run_status": "COMPLETED",
        "paused_for_human": wait_outcome.get("paused_for_human", False),
        "waited_seconds": wait_outcome.get("waited_seconds", 0.0),
        "status_history": wait_outcome.get("status_history", []),
        "error": None,
        "extracted": {
            "policy_found": True,
            "extracted_policy_id": review_pid,
            "patient_name": patient_name,
            "insurer_name": insurer_name,
            "policy_status": policy_status or "Active",
            "room_rent_limit": room_rent_limit,
            "copay_percentage": copay_percentage,
            "fields_prepared": [
                "hospital_name",
                "doctor_name",
                "diagnosis",
                "estimated_cost",
                "room_category",
                "sample_clinical_document.pdf",
            ],
            "document_uploaded": staged_doc,
            "current_portal_step": "Review & Verify",
            "staged_diagnosis": staged_diag,
            "staged_estimated_cost": staged_cost,
            "staged_room_category": staged_room,
            "stopped_at_review": True,
            "submitted_or_receipt_visible": False,
            "access_or_auth_blocked": False,
            "notes": (
                "Playwright headed-Chromium local fallback completed after human check gate; "
                "staged pre-authorization fields and stopped at Review & Verify without submitting."
            ),
        },
    }


def run_headed_playwright_fallback(
    portal_url: str,
    policy_id: str,
    diagnosis: str,
    estimated_cost: float | int | str,
    room_category: str = "Semi-Private",
    hospital_name: str = "Apollo Care Superspecialty Hospital",
    doctor_name: str = "Dr. Rajesh K. Mehta",
    use_sample_document: bool = True,
    human_check_timeout_seconds: float = DEFAULT_HUMAN_CHECK_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    status_callback: Callable[[str, str], None] | None = None,
    stub_page: Any = None,
) -> Dict[str, Any]:
    """
    Launch headed Chromium via Playwright (no stealth plugins, no fingerprint spoofing,
    no proxies) or use an injected stub_page for unit tests, navigate to the allowlisted
    portal_url, pause if a verification check is present, and execute the portal workflow.
    """
    if stub_page is not None:
        return execute_playwright_workflow_on_page(
            page=stub_page,
            policy_id=policy_id,
            diagnosis=diagnosis,
            estimated_cost=estimated_cost,
            room_category=room_category,
            hospital_name=hospital_name,
            doctor_name=doctor_name,
            use_sample_document=use_sample_document,
            human_check_timeout_seconds=human_check_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            status_callback=status_callback,
        )

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {
            "timed_out": False,
            "run_status": "PLAYWRIGHT_UNAVAILABLE",
            "paused_for_human": False,
            "waited_seconds": 0.0,
            "status_history": [],
            "error": (
                f"Local Playwright fallback could not start because 'playwright' is not installed ({exc}). "
                "Install with: pip install playwright && playwright install chromium"
            ),
            "extracted": None,
        }

    with sync_playwright() as pw:
        # Launch standard headed Chromium without stealth plugins, spoofing, or proxies
        browser = pw.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(portal_url, wait_until="domcontentloaded", timeout=30000)
            return execute_playwright_workflow_on_page(
                page=page,
                policy_id=policy_id,
                diagnosis=diagnosis,
                estimated_cost=estimated_cost,
                room_category=room_category,
                hospital_name=hospital_name,
                doctor_name=doctor_name,
                use_sample_document=use_sample_document,
                human_check_timeout_seconds=human_check_timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                status_callback=status_callback,
            )
        finally:
            try:
                browser.close()
            except Exception:
                pass
