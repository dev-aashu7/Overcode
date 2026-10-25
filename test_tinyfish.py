"""
test_tinyfish.py
----------------
Comprehensive local evaluation & verification suite for MedVerify (Team Nexora — HackIIITD 2026).

Tests all product-logic, transparent evidence-audit, timing honesty, human-review safeguard,
and state-transition requirements using 0 TinyFish credits (--check):
1-4. Input, Localhost & Authorized Portal Domain Guardrails.
5-9. Active Policies (11-check audit), Lapsed Policy (7-check audit), Unknown Policy (3-check audit).
10-11. Policy Extraction & Staged Review-Screen Field Mismatch Detection (PASS vs MISMATCH, raw values preserved).
12. Incomplete Workflow & Missing Evidence (NOT VERIFIED -> INCOMPLETE_WORKFLOW, never PASS).
13-14. Login/CAPTCHA Access Barriers & Timeout Exception Handling.
15-17. Human-Review Safeguard: Direct Violation, Contradictory Receipt Evidence, and Missing Safeguard Evidence.
18. Preparation-Time Metric Honesty (defined start/end boundaries, single-run observation label, no fabricated manual baseline).
19-24. All 6 Policy & UI State Transitions (verifying no stale patient name, coverage value, prepared badge, or success banner remains):
   - Transition 1: Active policy -> Unknown policy
   - Transition 2: Active policy -> Lapsed policy
   - Transition 3: Successful result -> Field mismatch
   - Transition 4: Previous result -> New verification in progress
   - Transition 5: Incomplete workflow -> Failed result
   - Transition 6: Simulated demo -> Live mode
25. 20-Run Synthetic Reproducibility Harness.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tinyfish import RunStatus
from tinyfish_client import (
    ACTIVE_HITL_SESSIONS,
    DEFAULT_PORTAL_URL,
    POLICY_SCHEMA,
    cancel_verification_session,
    resume_verification_session,
    verify_policy,
)


MOCK_PORTAL_RESPONSES = {
    "POL-100245": {
        "policy_found": True,
        "extracted_policy_id": "POL-100245",
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
        "extracted_policy_id": "POL-205118",
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
        "extracted_policy_id": "POL-309872",
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
        "extracted_policy_id": "POL-999001",
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
        "notes": "Policy ID 'POL-999999' not found in TPA records.",
    },
}


def _run_frontend_transition_tests(
    active_res: dict,
    unknown_res: dict,
    lapsed_res: dict,
    mismatch_res: dict,
    incomplete_res: dict,
    failed_res: dict,
) -> list[tuple[str, bool, str]]:
    """
    Execute frontend/app.js in a lightweight Node.js DOM harness to verify all 6 required
    UI state transitions and confirm zero stale patient names, coverage values, prepared badges,
    or success banners remain visible.
    """
    app_js_path = (Path(__file__).resolve().parent / "frontend" / "app.js").as_posix()
    node_script = f"""
const fs = require('fs');
const vm = require('vm');

const elements = {{}};
function makeEl(id) {{
  let _innerHTML = '';
  return {{
    id,
    textContent: '',
    get innerHTML() {{ return _innerHTML; }},
    set innerHTML(v) {{
      _innerHTML = v;
      if (!v) this.children = [];
    }},
    className: '',
    value: '',
    href: '',
    title: '',
    disabled: false,
    style: {{}},
    children: [],
    classList: {{
      _set: new Set(),
      add(c) {{ this._set.add(c); }},
      remove(c) {{ this._set.delete(c); }},
      toggle(c, force) {{
        if (force === undefined) {{
          if (this._set.has(c)) this._set.delete(c); else this._set.add(c);
        }} else if (force) {{ this._set.add(c); }} else {{ this._set.delete(c); }}
      }},
      contains(c) {{ return this._set.has(c); }}
    }},
    setAttribute() {{}},
    getAttribute() {{ return 'pol100245'; }},
    addEventListener() {{}},
    appendChild(child) {{ this.children.push(child); }}
  }};
}}

const ids = [
  'nav-api-dot', 'nav-telemetry-btn', 'mode-live-btn', 'mode-sim-btn', 'nav-sim-btn',
  'sim-banner', 'preset-select', 'policy-id-input', 'cost-input', 'diagnosis-input',
  'room-category-select', 'sample-doc-select', 'portal-url-input', 'verify-form',
  'verify-submit-btn', 'verify-btn-text', 'guardrail-test-btn', 'result-mode-badge',
  'ws-status-banner', 'hitl-action-bar', 'hitl-title', 'hitl-session-badge',
  'hitl-action-text', 'btn-hitl-resume', 'btn-hitl-cancel', 'hitl-manual-link',
  'chip-status', 'val-status', 'sub-status', 'chip-room', 'val-room',
  'sub-room', 'chip-copay', 'val-copay', 'sub-copay', 'ev-portal-step', 'ev-staged-summary',
  'ev-accuracy', 'ev-prep-time', 'audit-summary-badge', 'audit-table-body', 'tl-step-1',
  'tl-badge-1', 'tl-desc-1', 'tl-step-2', 'tl-badge-2', 'tl-desc-2', 'tl-fields-wrap',
  'tl-step-3', 'tl-badge-3', 'tl-desc-3', 'gate-stopped-val', 'gate-submitted-val',
  'manual-fallback-link', 'raw-json-pre'
];
ids.forEach(id => {{ elements[id] = makeEl(id); }});

const sandbox = {{
  window: {{}},
  document: {{
    getElementById(id) {{
      if (!elements[id]) elements[id] = makeEl(id);
      return elements[id];
    }},
    querySelectorAll() {{ return []; }},
    querySelector() {{ return null; }},
    createElement(tag) {{ return makeEl(tag); }}
  }},
  fetch: async () => ({{ ok: true, json: async () => ({{ api_key_configured: true, default_portal_url: 'https://medverify-tpa-portal.vercel.app/' }}) }}),
  alert: () => {{}},
  setInterval: () => 1,
  clearInterval: () => {{}}
}};

const code = fs.readFileSync({json.dumps(app_js_path)}, 'utf8');
vm.runInNewContext(code, sandbox);
const ws = sandbox.window.MedVerifyWorkspace;

const activeRes = {json.dumps(active_res)};
const unknownRes = {json.dumps(unknown_res)};
const lapsedRes = {json.dumps(lapsed_res)};
const mismatchRes = {json.dumps(mismatch_res)};
const incompleteRes = {json.dumps(incomplete_res)};
const failedRes = {json.dumps(failed_res)};

const results = [];

// 1. Active policy -> Unknown policy
ws.renderVerificationResult(activeRes);
ws.renderVerificationResult(unknownRes);
const t1Ok = (
  !elements['sub-status'].textContent.includes('Rahul Sharma') &&
  elements['val-room'].textContent === '—' &&
  elements['val-copay'].textContent === '—' &&
  elements['tl-fields-wrap'].innerHTML === '' &&
  elements['tl-fields-wrap'].children.length === 0 &&
  !elements['ws-status-banner'].className.includes('tone-ok')
);
results.push(['19. Transition 1: Active policy -> Unknown policy clears patient, coverage, badges & success banner', t1Ok, `sub=${{elements['sub-status'].textContent}}, room=${{elements['val-room'].textContent}}, banner=${{elements['ws-status-banner'].className}}`]);

// 2. Active policy -> Lapsed policy
ws.renderVerificationResult(activeRes);
ws.renderVerificationResult(lapsedRes);
const t2Ok = (
  !elements['sub-status'].textContent.includes('Rahul Sharma') &&
  elements['sub-status'].textContent.includes('Vikram Malhotra') &&
  elements['val-status'].textContent === 'Lapsed' &&
  elements['val-room'].textContent === '₹3,000 / day' &&
  elements['tl-fields-wrap'].children.length === 0 &&
  elements['ws-status-banner'].className.includes('tone-err')
);
results.push(['20. Transition 2: Active policy -> Lapsed policy replaces coverage & clears prepared badges', t2Ok, `sub=${{elements['sub-status'].textContent}}, status=${{elements['val-status'].textContent}}, badges=${{elements['tl-fields-wrap'].children.length}}`]);

// 3. Successful result -> Field mismatch
ws.renderVerificationResult(activeRes);
ws.renderVerificationResult(mismatchRes);
const t3Ok = (
  elements['ws-status-banner'].className.includes('tone-err') &&
  !elements['ws-status-banner'].className.includes('tone-ok') &&
  elements['audit-summary-badge'].textContent.includes('MISMATCH') &&
  elements['tl-fields-wrap'].children.length === 0
);
results.push(['21. Transition 3: Successful result -> Field mismatch removes green banner & flags MISMATCH', t3Ok, `banner=${{elements['ws-status-banner'].className}}, audit=${{elements['audit-summary-badge'].textContent}}`]);

// 4. Previous result -> New verification in progress
ws.renderVerificationResult(activeRes);
ws.resetWorkspaceDisplay('<strong>Dispatching TinyFish Browser Agent...</strong>', 'tone-warn');
const t4Ok = (
  elements['val-status'].textContent === '—' &&
  !elements['sub-status'].textContent.includes('Rahul Sharma') &&
  elements['val-room'].textContent === '—' &&
  elements['val-copay'].textContent === '—' &&
  elements['tl-fields-wrap'].children.length === 0 &&
  elements['audit-summary-badge'].textContent === '0 CHECKS RUN' &&
  elements['ws-status-banner'].className.includes('tone-warn')
);
results.push(['22. Transition 4: Previous result -> New verification in progress resets all fields & audit table', t4Ok, `status=${{elements['val-status'].textContent}}, audit=${{elements['audit-summary-badge'].textContent}}`]);

// 5. Incomplete workflow -> Failed result
ws.renderVerificationResult(incompleteRes);
const incNoGreen = !elements['ws-status-banner'].className.includes('tone-ok') && elements['tl-fields-wrap'].children.length === 0;
ws.renderVerificationResult(failedRes);
const t5Ok = (
  incNoGreen &&
  !elements['sub-status'].textContent.includes('Rahul Sharma') &&
  elements['val-status'].textContent === 'Unverified' &&
  elements['val-room'].textContent === '—' &&
  elements['val-copay'].textContent === '—' &&
  elements['tl-fields-wrap'].children.length === 0 &&
  elements['ws-status-banner'].className.includes('tone-err')
);
results.push(['23. Transition 5: Incomplete workflow -> Failed result clears all partial state', t5Ok, `status=${{elements['val-status'].textContent}}, sub=${{elements['sub-status'].textContent}}, banner=${{elements['ws-status-banner'].className}}`]);

// 6. Simulated demo -> Live mode
ws.setExecutionMode('simulated');
ws.setExecutionMode('live');
const t6Ok = (
  elements['val-status'].textContent === '—' &&
  !elements['sub-status'].textContent.includes('Rahul Sharma') &&
  elements['val-room'].textContent === '—' &&
  elements['val-copay'].textContent === '—' &&
  elements['tl-fields-wrap'].children.length === 0 &&
  elements['audit-summary-badge'].textContent === '0 CHECKS RUN'
);
results.push(['24. Transition 6: Simulated demo -> Live mode wipes all simulated preview data', t6Ok, `status=${{elements['val-status'].textContent}}, audit=${{elements['audit-summary-badge'].textContent}}`]);

// 7. Dashboard 'Waiting for human check' status while paused + starting a new case right after clears 'Waiting' banner
ws.renderWaitingForHumanCheck();
const waitShown = (
  elements['val-status'].textContent === 'Waiting for human check' &&
  elements['ev-portal-step'].textContent === 'Waiting for human check' &&
  elements['ws-status-banner'].innerHTML.includes('Waiting for human check')
);
ws.resetWorkspaceDisplay('<strong>Case Preset Updated:</strong> Stale results cleared.');
const waitClearedOnReset = (
  !elements['val-status'].textContent.includes('Waiting') &&
  !elements['ev-portal-step'].textContent.includes('Waiting') &&
  !elements['ws-status-banner'].innerHTML.includes('Waiting for human check') &&
  !elements['tl-badge-1'].textContent.includes('Waiting')
);
ws.renderWaitingForHumanCheck();
ws.renderVerificationResult(activeRes);
const waitClearedOnNewResult = (
  elements['val-status'].textContent === 'Active' &&
  elements['ev-portal-step'].textContent === 'Review & Verify' &&
  !elements['ws-status-banner'].innerHTML.includes('Waiting for human check') &&
  !elements['tl-badge-1'].textContent.includes('Waiting')
);
const waitOk = waitShown && waitClearedOnReset && waitClearedOnNewResult;
results.push(['25. Dashboard displays "Waiting for human check" while paused & clears it completely on new case', waitOk, `shown=${{waitShown}}, clearedOnReset=${{waitClearedOnReset}}, clearedOnNewResult=${{waitClearedOnNewResult}}`]);

console.log(JSON.stringify(results));
"""
    proc = subprocess.run(
        ["node", "-"],
        input=node_script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    parsed = json.loads(proc.stdout.strip().splitlines()[-1])
    return [(item[0], bool(item[1]), str(item[2])) for item in parsed]


class StubPlaywrightPage:
    """
    Stubbed Playwright page for testing the optional local headed-Chromium fallback:
    - mode == 'no_check': 'Policy Search' heading is immediately visible.
    - mode == 'check_then_completed': Initially displays a CAPTCHA/verification check;
      after human_complete_after_polls wait cycles (simulating a human completing the check
      in the visible browser window), 'Policy Search' heading appears and workflow resumes.
    - mode == 'timeout': Remains on the verification check until timeout expires.
    """

    def __init__(self, mode: str = "no_check", human_complete_after_polls: int = 2) -> None:
        self.mode = mode
        self.human_complete_after_polls = human_complete_after_polls
        self.poll_count = 0
        self.submit_clicked = False

    def get_visible_text(self) -> str:
        if self.mode == "no_check":
            return "ApexCare Health TPA — Policy Search"
        if self.mode == "check_then_completed":
            if self.poll_count < self.human_complete_after_polls:
                return "Security Check — Verify you are human (CAPTCHA challenge)"
            return "ApexCare Health TPA — Policy Search"
        return "Security Check — Verify you are human (CAPTCHA challenge)"

    def wait_for_timeout(self, ms: int) -> None:
        self.poll_count += 1

    def execute_portal_steps(
        self,
        policy_id: str,
        diagnosis: str,
        estimated_cost: float | int | str,
        room_category: str,
        hospital_name: str,
        doctor_name: str,
        use_sample_document: bool,
    ) -> dict:
        # Must only execute after post-check element ('Policy Search') is visible
        assert "policy search" in self.get_visible_text().lower()
        base = dict(MOCK_PORTAL_RESPONSES.get(policy_id.upper(), MOCK_PORTAL_RESPONSES["POL-100245"]))
        base["extracted_policy_id"] = policy_id.upper()
        base["staged_diagnosis"] = str(diagnosis)
        base["staged_estimated_cost"] = f"₹{int(float(estimated_cost)):,}"
        base["staged_room_category"] = str(room_category)
        base["document_uploaded"] = "sample_clinical_document.pdf" if use_sample_document else ""
        base["current_portal_step"] = "Review & Verify"
        base["stopped_at_review"] = True
        base["submitted_or_receipt_visible"] = False
        return base


def run_local_checks() -> None:
    """Verify guardrails, transparent audit checks, safeguard gates, timing honesty, and state transitions (0 credits)."""
    print("=== MedVerify Final Reliability, Evidence & Demo-Readiness Suite (0 Credits Used) ===\n")

    # Verify POLICY_SCHEMA has no unsupported 'description' fields
    schema_str = json.dumps(POLICY_SCHEMA)
    if '"description"' in schema_str:
        print("[FAIL] 0. POLICY_SCHEMA contains unsupported 'description' field")
        sys.exit(1)

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
    total_tests = 0
    passed_tests = 0

    def record(title: str, passed: bool, detail: str) -> None:
        nonlocal all_passed, total_tests, passed_tests
        total_tests += 1
        if passed:
            passed_tests += 1
        all_passed = all_passed and passed
        print(f"[{'PASS' if passed else 'FAIL'}] {title}")
        print(f"       {detail}\n")

    for title, kwargs, expected_status in guardrail_cases:
        res = verify_policy(**kwargs)
        actual_status = res.get("run_status")
        passed = (
            res.get("success") is False
            and actual_status == expected_status
            and res.get("policy_status") is None
            and res.get("submitted") is False
            and (res.get("timing") or {}).get("is_measured_live_run") is False
        )
        record(title, passed, f"run_status: {actual_status} | error: {res.get('error')}")

    policy_test_cases = [
        ("5. Confirmed Active Policy POL-100245 (Rahul Sharma) — 11/11 Audit Checks PASS", "POL-100245", True, "COMPLETED", True, 11),
        ("6. Confirmed Active Policy POL-205118 (Sunita Verma) — 11/11 Audit Checks PASS", "POL-205118", True, "COMPLETED", True, 11),
        ("7. Confirmed Active Policy POL-309872 (Priya Nair) — 11/11 Audit Checks PASS", "POL-309872", True, "COMPLETED", True, 11),
        ("8. Confirmed Lapsed Policy POL-999001 (Vikram Malhotra) — Halts at Policy Details (7/7 Checks PASS)", "POL-999001", False, "POLICY_LAPSED", False, 7),
        ("9. Unknown Policy ID POL-999999 — Halts at Policy Search (3/3 Checks PASS)", "POL-999999", False, "NOT_FOUND", False, 3),
    ]

    results_by_pid = {}

    with patch.dict(os.environ, {"TINYFISH_API_KEY": "mock-test-key-0-credits"}):
        for title, pid, expected_success, expected_run_status, expected_stopped, expected_check_cnt in policy_test_cases:
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
            results_by_pid[pid] = res
            acc = res.get("field_accuracy") or {}
            checks = acc.get("checks") or []
            passed = (
                res.get("success") is expected_success
                and res.get("run_status") == expected_run_status
                and res.get("stopped_at_review") is expected_stopped
                and res.get("submitted") is False
                and acc.get("verified") is True
                and acc.get("total_checks") == expected_check_cnt
                and acc.get("passed_count") == expected_check_cnt
                and acc.get("mismatch_count") == 0
                and acc.get("not_verified_count") == 0
                and len(checks) == expected_check_cnt
                and all(
                    set(c.keys()) >= {"field", "label", "expected", "actual", "status"} and c["status"] == "PASS"
                    for c in checks
                )
            )
            record(
                title,
                passed,
                f"success: {res.get('success')} | run_status: {res.get('run_status')} | "
                f"checks: {acc.get('passed_count')}/{acc.get('total_checks')} PASS",
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
        bad_pol_acc = bad_pol_res.get("field_accuracy") or {}
        room_chk = next((c for c in (bad_pol_acc.get("checks") or []) if c["field"] == "room_rent_limit"), {})
        pol_mismatch_passed = (
            bad_pol_res.get("success") is False
            and bad_pol_res.get("run_status") == "FIELD_MISMATCH"
            and bad_pol_res.get("room_rent_limit") == "₹99,000 / day (Wrong Extracted Value)"
            and bad_pol_acc.get("verified") is False
            and bad_pol_acc.get("mismatch_count") == 1
            and bad_pol_acc.get("passed_count") == 10
            and room_chk.get("status") == "MISMATCH"
            and room_chk.get("actual") == "₹99,000 / day (Wrong Extracted Value)"
        )
        record(
            "10. Policy Extraction Mismatch (room_rent_limit) flagged as MISMATCH & raw value preserved",
            pol_mismatch_passed,
            f"status: {bad_pol_res.get('run_status')} | check: {room_chk.get('status')} | actual: {room_chk.get('actual')}",
        )

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
        bad_form_acc = bad_form_res.get("field_accuracy") or {}
        cost_chk = next((c for c in (bad_form_acc.get("checks") or []) if c["field"] == "estimated_cost"), {})
        form_mismatch_passed = (
            bad_form_res.get("success") is False
            and bad_form_res.get("run_status") == "FIELD_MISMATCH"
            and bad_form_res.get("staged_estimated_cost") == "₹12,000"
            and bad_form_acc.get("verified") is False
            and bad_form_acc.get("mismatch_count") == 1
            and cost_chk.get("status") == "MISMATCH"
            and cost_chk.get("expected") == "85000"
            and cost_chk.get("actual") == "₹12,000"
        )
        record(
            "11. Staged Form Field Mismatch (estimated_cost) flagged as MISMATCH & raw value preserved",
            form_mismatch_passed,
            f"status: {bad_form_res.get('run_status')} | expected: {cost_chk.get('expected')} | actual: {cost_chk.get('actual')}",
        )

        # Test 12: Missing evidence / incomplete workflow produces NOT VERIFIED & INCOMPLETE_WORKFLOW
        incomplete_payload = dict(
            MOCK_PORTAL_RESPONSES["POL-100245"],
            stopped_at_review=False,
            staged_diagnosis=None,
        )
        fake_incomplete_run = SimpleNamespace(status=RunStatus.COMPLETED, result=incomplete_payload)
        with patch("tinyfish_client.TinyFish") as mock_tf_cls:
            mock_tf_cls.return_value.agent.run.return_value = fake_incomplete_run
            inc_res = verify_policy(
                policy_id="POL-100245",
                diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                estimated_cost=85000,
                portal_url=DEFAULT_PORTAL_URL,
            )
        inc_acc = inc_res.get("field_accuracy") or {}
        diag_chk = next((c for c in (inc_acc.get("checks") or []) if c["field"] == "diagnosis"), {})
        rev_chk = next((c for c in (inc_acc.get("checks") or []) if c["field"] == "review_screen_arrival"), {})
        inc_passed = (
            inc_res.get("success") is False
            and inc_res.get("run_status") == "INCOMPLETE_WORKFLOW"
            and inc_acc.get("verified") is False
            and inc_acc.get("not_verified_count") >= 2
            and diag_chk.get("status") == "NOT VERIFIED"
            and rev_chk.get("status") == "NOT VERIFIED"
        )
        record(
            "12. Missing Evidence & Incomplete Halt produces NOT VERIFIED & INCOMPLETE_WORKFLOW",
            inc_passed,
            f"run_status: {inc_res.get('run_status')} | not_verified_count: {inc_acc.get('not_verified_count')}",
        )

        # Test 13: Login / CAPTCHA / Access Restriction Detected -> HUMAN_ACTION_REQUIRED
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
        auth_hitl = auth_res.get("human_intervention") or {}
        auth_passed = (
            auth_res.get("success") is False
            and auth_res.get("run_status") == "HUMAN_ACTION_REQUIRED"
            and auth_res.get("legacy_run_status") == "ACCESS_OR_AUTH_BLOCKED"
            and auth_res.get("paused_for_human_check") is True
            and auth_res.get("stopped_at_review") is False
            and auth_res.get("submitted") is False
            and auth_hitl.get("required") is True
            and auth_res.get("manual_fallback_url") == DEFAULT_PORTAL_URL
        )
        record(
            "13. Login / CAPTCHA / Access Barrier Detected (HUMAN_ACTION_REQUIRED + manual_fallback_url)",
            auth_passed,
            f"run_status: {auth_res.get('run_status')} | legacy: {auth_res.get('legacy_run_status')} | fallback: {auth_res.get('manual_fallback_url')}",
        )

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
        record(
            "14. Timeout Exception Handled Safely (TIMEOUT + manual_fallback_url)",
            timeout_passed,
            f"run_status: {timeout_res.get('run_status')} | error: {timeout_res.get('error')}",
        )

        # Test 15: Direct Auto-Submission Safety Violation Gate (submitted_or_receipt_visible=True)
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
            and viol_res.get("submitted") is True
        )
        record(
            "15. Human-Review Safeguard: Direct Submission Flag (SUBMISSION_VIOLATION) enforced",
            viol_passed,
            f"run_status: {viol_res.get('run_status')} | submitted: {viol_res.get('submitted')}",
        )

        # Test 16: Contradictory Submission Evidence (submitted_or_receipt_visible=False but step/notes show Receipt)
        contradict_payload = dict(
            MOCK_PORTAL_RESPONSES["POL-100245"],
            submitted_or_receipt_visible=False,
            stopped_at_review=True,
            current_portal_step="Submission Receipt",
            notes="Pre-authorization submitted with Claim Reference CLM-2026-88412.",
        )
        fake_contradict_run = SimpleNamespace(status=RunStatus.COMPLETED, result=contradict_payload)
        with patch("tinyfish_client.TinyFish") as mock_tf_cls:
            mock_tf_cls.return_value.agent.run.return_value = fake_contradict_run
            contra_res = verify_policy(
                policy_id="POL-100245",
                diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                estimated_cost=85000,
                portal_url=DEFAULT_PORTAL_URL,
            )
        contra_passed = (
            contra_res.get("success") is False
            and contra_res.get("run_status") == "SUBMISSION_VIOLATION"
            and contra_res.get("submitted") is True
            and contra_res.get("submission_safeguard_verified") is False
        )
        record(
            "16. Human-Review Safeguard: Contradictory Receipt Step / Claim Ref rejected safely",
            contra_passed,
            f"run_status: {contra_res.get('run_status')} | error: {contra_res.get('error')}",
        )

        # Test 17: Missing Submission Evidence (submitted_or_receipt_visible=None) fails safely as NOT VERIFIED
        missing_sub_payload = dict(MOCK_PORTAL_RESPONSES["POL-100245"])
        missing_sub_payload.pop("submitted_or_receipt_visible", None)
        fake_missing_sub_run = SimpleNamespace(status=RunStatus.COMPLETED, result=missing_sub_payload)
        with patch("tinyfish_client.TinyFish") as mock_tf_cls:
            mock_tf_cls.return_value.agent.run.return_value = fake_missing_sub_run
            miss_sub_res = verify_policy(
                policy_id="POL-100245",
                diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                estimated_cost=85000,
                portal_url=DEFAULT_PORTAL_URL,
            )
        miss_sub_acc = miss_sub_res.get("field_accuracy") or {}
        sub_chk = next((c for c in (miss_sub_acc.get("checks") or []) if c["field"] == "submission_safeguard"), {})
        miss_sub_passed = (
            miss_sub_res.get("success") is False
            and miss_sub_res.get("run_status") == "INCOMPLETE_WORKFLOW"
            and miss_sub_res.get("submission_safeguard_verified") is False
            and sub_chk.get("status") == "NOT VERIFIED"
        )
        record(
            "17. Human-Review Safeguard: Missing Submission Evidence fails safely as NOT VERIFIED",
            miss_sub_passed,
            f"run_status: {miss_sub_res.get('run_status')} | safeguard check: {sub_chk.get('status')}",
        )

        # Test 18: Preparation-Time Metric Honesty
        active_timing = results_by_pid["POL-100245"].get("timing") or {}
        timing_passed = (
            active_timing.get("is_measured_live_run") is True
            and "verify_policy()" in (active_timing.get("start_boundary") or "")
            and "audit completion" in (active_timing.get("end_boundary") or "")
            and "Single-run observation" in (active_timing.get("observation_label") or "")
            and "No manual baseline" in (active_timing.get("manual_baseline_note") or "")
        )
        record(
            "18. Preparation-Time Metric Honesty (defined start/end boundaries, no fabricated manual baseline)",
            timing_passed,
            f"label: {active_timing.get('observation_label')} | note: {active_timing.get('manual_baseline_note')}",
        )

        # Tests 19-24: All 6 Policy & UI State Transitions via Node.js DOM execution of frontend/app.js
        transition_results = _run_frontend_transition_tests(
            active_res=results_by_pid["POL-100245"],
            unknown_res=results_by_pid["POL-999999"],
            lapsed_res=results_by_pid["POL-999001"],
            mismatch_res=bad_form_res,
            incomplete_res=inc_res,
            failed_res=timeout_res,
        )
        for t_title, t_ok, t_detail in transition_results:
            record(t_title, t_ok, t_detail)

        # Test 26: Playwright Fallback (Stubbed Page: No Check) -> Completes 11/11 Audit & Halts at Review
        stub_no_check = StubPlaywrightPage(mode="no_check")
        with patch("tinyfish_client.TinyFish") as mock_tf_cls:
            mock_tf_cls.return_value.agent.run.return_value = fake_auth_run
            fb_no_check_res = verify_policy(
                policy_id="POL-100245",
                diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                estimated_cost=85000,
                room_category="Semi-Private",
                portal_url=DEFAULT_PORTAL_URL,
                enable_playwright_fallback=True,
                playwright_stub_page=stub_no_check,
            )
        fb_nc_acc = fb_no_check_res.get("field_accuracy") or {}
        fb_nc_ok = (
            fb_no_check_res.get("success") is True
            and fb_no_check_res.get("fallback_used") == "playwright_headed_chromium"
            and fb_no_check_res.get("paused_for_human_check") is False
            and fb_no_check_res.get("stopped_at_review") is True
            and fb_no_check_res.get("submitted") is False
            and fb_nc_acc.get("verified") is True
            and fb_nc_acc.get("passed_count") == 11
        )
        record(
            "26. Playwright Fallback (Stubbed Page — No Check): Reuses inputs, 11/11 Audit PASS, stops at Review",
            fb_nc_ok,
            f"success: {fb_no_check_res.get('success')} | paused: {fb_no_check_res.get('paused_for_human_check')} | checks: {fb_nc_acc.get('passed_count')}/11",
        )

        # Test 27: Playwright Fallback (Stubbed Page: Check Detected -> 'Waiting for human check' -> Completed by Human)
        stub_check_done = StubPlaywrightPage(mode="check_then_completed", human_complete_after_polls=2)
        observed_statuses: list[tuple[str, str]] = []

        def _capture_status(code: str, text: str) -> None:
            observed_statuses.append((code, text))

        with patch("tinyfish_client.TinyFish") as mock_tf_cls:
            mock_tf_cls.return_value.agent.run.return_value = fake_auth_run
            fb_done_res = verify_policy(
                policy_id="POL-100245",
                diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                estimated_cost=85000,
                room_category="Semi-Private",
                portal_url=DEFAULT_PORTAL_URL,
                enable_playwright_fallback=True,
                human_check_timeout_seconds=10.0,
                poll_interval_seconds=0.01,
                status_callback=_capture_status,
                playwright_stub_page=stub_check_done,
            )
        fb_sol_acc = fb_done_res.get("field_accuracy") or {}
        fb_sol_ok = (
            fb_done_res.get("success") is True
            and fb_done_res.get("fallback_used") == "playwright_headed_chromium"
            and fb_done_res.get("paused_for_human_check") is True
            and any(txt == "Waiting for human check" for _, txt in observed_statuses)
            and stub_check_done.poll_count == 2
            and fb_done_res.get("stopped_at_review") is True
            and fb_done_res.get("submitted") is False
            and fb_sol_acc.get("verified") is True
            and fb_sol_acc.get("passed_count") == 11
        )
        record(
            "27. Playwright Fallback (Stubbed Page — Check Then Completed): Pauses ('Waiting for human check'), resumes on 'Policy Search', 11/11 PASS",
            fb_sol_ok,
            f"paused: {fb_done_res.get('paused_for_human_check')} | statuses: {[t for _, t in observed_statuses]} | polls: {stub_check_done.poll_count}",
        )

        # Test 28: Playwright Fallback (Stubbed Page: Check Expires -> HUMAN_CHECK_TIMEOUT)
        stub_timeout = StubPlaywrightPage(mode="timeout")
        timeout_statuses: list[tuple[str, str]] = []
        with patch("tinyfish_client.TinyFish") as mock_tf_cls:
            mock_tf_cls.return_value.agent.run.return_value = fake_auth_run
            fb_timeout_res = verify_policy(
                policy_id="POL-100245",
                diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                estimated_cost=85000,
                room_category="Semi-Private",
                portal_url=DEFAULT_PORTAL_URL,
                enable_playwright_fallback=True,
                human_check_timeout_seconds=0.05,
                poll_interval_seconds=0.01,
                status_callback=lambda c, t: timeout_statuses.append((c, t)),
                playwright_stub_page=stub_timeout,
            )
        fb_to_ok = (
            fb_timeout_res.get("success") is False
            and fb_timeout_res.get("run_status") == "HUMAN_CHECK_TIMEOUT"
            and fb_timeout_res.get("paused_for_human_check") is True
            and any(txt == "Waiting for human check" for _, txt in timeout_statuses)
            and fb_timeout_res.get("stopped_at_review") is False
            and fb_timeout_res.get("submitted") is False
        )
        record(
            "28. Playwright Fallback (Stubbed Page — Timeout): Returns HUMAN_CHECK_TIMEOUT when human check expires",
            fb_to_ok,
            f"run_status: {fb_timeout_res.get('run_status')} | error: {fb_timeout_res.get('error')}",
        )

        # Test 29: 20-Run Mocked Reproducibility Harness (0 credits)
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
        record(
            "29. 20-Run Mocked Reproducibility & Schema-Consistency Harness (20/20 runs)",
            repro_ok,
            "0 auto-submissions, 100% transparent audit consistency across 20 mocked runs.",
        )

        # Test 30: Non-blocking /api/status during wait + VERIFY_RUN_LOCK prevents concurrent status overwrite
        import server
        server._update_live_run_status("WAITING_FOR_HUMAN_CHECK", "Waiting for human check")
        acquired_first = server.VERIFY_RUN_LOCK.acquire(blocking=False)
        try:
            status_during_wait = server._get_live_run_status()
            acquired_second = server.VERIFY_RUN_LOCK.acquire(blocking=False)
        finally:
            if acquired_first:
                server.VERIFY_RUN_LOCK.release()
            server._update_live_run_status("IDLE", "Idle")

        concurrency_ok = (
            acquired_first is True
            and acquired_second is False
            and status_during_wait.get("status") == "Waiting for human check"
        )
        record(
            "30. Concurrency & Status Guard: /api/status answers during wait & VERIFY_RUN_LOCK prevents overlapping runs",
            concurrency_ok,
            f"status_during_wait: '{status_during_wait.get('status')}' | second_lock_blocked: {not acquired_second}",
        )

        # Test 31: Same-Session Human-in-the-Loop Pause via TinyFish Browser API (client.browser.sessions.create)
        stub_hitl_page = StubPlaywrightPage(mode="check_then_completed", human_complete_after_polls=1)
        fake_browser_session = SimpleNamespace(
            session_id="sess-tf-hitl-001",
            cdp_url="wss://browser.tinyfish.ai/cdp/sess-tf-hitl-001",
            base_url="https://browser.tinyfish.ai/sessions/sess-tf-hitl-001",
        )
        with patch("tinyfish_client.TinyFish") as mock_tf_cls:
            mock_tf_cls.return_value.agent.run.return_value = fake_auth_run
            mock_tf_cls.return_value.browser.sessions.create.return_value = fake_browser_session
            hitl_pause_res = verify_policy(
                policy_id="POL-100245",
                diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                estimated_cost=85000,
                room_category="Semi-Private",
                portal_url=DEFAULT_PORTAL_URL,
                use_tinyfish_browser_session=True,
                playwright_stub_page=stub_hitl_page,
            )
        hitl_meta = hitl_pause_res.get("human_intervention") or {}
        hitl_pause_ok = (
            hitl_pause_res.get("success") is False
            and hitl_pause_res.get("run_status") == "HUMAN_ACTION_REQUIRED"
            and hitl_meta.get("required") is True
            and hitl_meta.get("can_resume_same_session") is True
            and hitl_meta.get("session_id") == "sess-tf-hitl-001"
            and "sess-tf-hitl-001" in ACTIVE_HITL_SESSIONS
            and hitl_pause_res.get("stopped_at_review") is False
            and hitl_pause_res.get("submitted") is False
        )
        record(
            "31. TinyFish Browser API (client.browser.sessions.create) Same-Session Pause -> HUMAN_ACTION_REQUIRED",
            hitl_pause_ok,
            f"run_status: {hitl_pause_res.get('run_status')} | session_id: {hitl_meta.get('session_id')} | can_resume: {hitl_meta.get('can_resume_same_session')}",
        )

        # Test 32: Same-Session Continuation (resume_verification_session):
        #   (a) Early resume while challenge still visible keeps session alive & returns HUMAN_ACTION_REQUIRED
        #   (b) After human completes challenge ('Policy Search' visible), resumes same session, verifies landmark & policy ID, passes 11/11 checks, stops at Review & Verify
        early_resume_res = resume_verification_session("sess-tf-hitl-001")
        early_still_paused = (
            early_resume_res.get("success") is False
            and early_resume_res.get("run_status") == "HUMAN_ACTION_REQUIRED"
            and "sess-tf-hitl-001" in ACTIVE_HITL_SESSIONS
        )
        # Simulate human completing the CAPTCHA/auth challenge in the preserved session
        stub_hitl_page.wait_for_timeout(500)
        resumed_ok_res = resume_verification_session("sess-tf-hitl-001")
        resumed_acc = resumed_ok_res.get("field_accuracy") or {}
        resume_success_ok = (
            early_still_paused
            and resumed_ok_res.get("success") is True
            and resumed_ok_res.get("run_status") == "COMPLETED"
            and resumed_ok_res.get("resumed_from_human_intervention") is True
            and resumed_ok_res.get("session_id") == "sess-tf-hitl-001"
            and "sess-tf-hitl-001" not in ACTIVE_HITL_SESSIONS
            and resumed_ok_res.get("stopped_at_review") is True
            and resumed_ok_res.get("submitted") is False
            and resumed_acc.get("verified") is True
            and resumed_acc.get("passed_count") == 11
        )
        record(
            "32. Same-Session Continuation (resume_verification_session): Re-checks landmark & policy ID, 11/11 PASS, stops at Review",
            resume_success_ok,
            f"early_paused: {early_still_paused} | resumed_status: {resumed_ok_res.get('run_status')} | checks: {resumed_acc.get('passed_count')}/11 | submitted: {resumed_ok_res.get('submitted')}",
        )

        # Test 33: Expired or Unavailable Session -> SESSION_EXPIRED_OR_UNAVAILABLE + manual fallback
        stub_exp_page = StubPlaywrightPage(mode="check_then_completed", human_complete_after_polls=5)
        fake_exp_session = SimpleNamespace(
            session_id="sess-tf-expired-002",
            cdp_url="wss://browser.tinyfish.ai/cdp/sess-tf-expired-002",
            base_url="https://browser.tinyfish.ai/sessions/sess-tf-expired-002",
        )
        with patch("tinyfish_client.TinyFish") as mock_tf_cls:
            mock_tf_cls.return_value.agent.run.return_value = fake_auth_run
            mock_tf_cls.return_value.browser.sessions.create.return_value = fake_exp_session
            verify_policy(
                policy_id="POL-100245",
                diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                estimated_cost=85000,
                room_category="Semi-Private",
                portal_url=DEFAULT_PORTAL_URL,
                use_tinyfish_browser_session=True,
                playwright_stub_page=stub_exp_page,
            )
        # Force expiration of registered session
        ACTIVE_HITL_SESSIONS["sess-tf-expired-002"]["expires_at_epoch"] = 0.0
        exp_res = resume_verification_session("sess-tf-expired-002")
        missing_sess_res = resume_verification_session("sess-nonexistent-999")
        expired_ok = (
            exp_res.get("success") is False
            and exp_res.get("run_status") == "SESSION_EXPIRED_OR_UNAVAILABLE"
            and exp_res.get("manual_fallback_url") == DEFAULT_PORTAL_URL
            and exp_res.get("submitted") is False
            and "sess-tf-expired-002" not in ACTIVE_HITL_SESSIONS
            and missing_sess_res.get("run_status") == "SESSION_EXPIRED_OR_UNAVAILABLE"
        )
        record(
            "33. Expired or Unavailable Session returns SESSION_EXPIRED_OR_UNAVAILABLE + manual_fallback_url",
            expired_ok,
            f"expired_status: {exp_res.get('run_status')} | missing_status: {missing_sess_res.get('run_status')} | fallback: {exp_res.get('manual_fallback_url')}",
        )

        # Test 34: User Cancellation (cancel_verification_session) -> USER_CANCELLED + session terminated
        stub_cancel_page = StubPlaywrightPage(mode="check_then_completed", human_complete_after_polls=5)
        fake_cancel_session = SimpleNamespace(
            session_id="sess-tf-cancel-003",
            cdp_url="wss://browser.tinyfish.ai/cdp/sess-tf-cancel-003",
            base_url="https://browser.tinyfish.ai/sessions/sess-tf-cancel-003",
        )
        with patch("tinyfish_client.TinyFish") as mock_tf_cls:
            mock_tf_cls.return_value.agent.run.return_value = fake_auth_run
            mock_tf_cls.return_value.browser.sessions.create.return_value = fake_cancel_session
            verify_policy(
                policy_id="POL-100245",
                diagnosis="Acute Cholecystitis / ICD-10 K81.0",
                estimated_cost=85000,
                room_category="Semi-Private",
                portal_url=DEFAULT_PORTAL_URL,
                use_tinyfish_browser_session=True,
                playwright_stub_page=stub_cancel_page,
            )
        cancel_res = cancel_verification_session("sess-tf-cancel-003")
        cancel_ok = (
            cancel_res.get("success") is False
            and cancel_res.get("run_status") == "USER_CANCELLED"
            and cancel_res.get("cancelled_by_user") is True
            and cancel_res.get("stopped_at_review") is False
            and cancel_res.get("submitted") is False
            and cancel_res.get("manual_fallback_url") == DEFAULT_PORTAL_URL
            and "sess-tf-cancel-003" not in ACTIVE_HITL_SESSIONS
        )
        record(
            "34. User Cancellation (cancel_verification_session) terminates session & returns USER_CANCELLED",
            cancel_ok,
            f"run_status: {cancel_res.get('run_status')} | cancelled_by_user: {cancel_res.get('cancelled_by_user')}",
        )

        # Test 35: Post-Resume Policy Mismatch & Review-Stop Safeguard Enforcement
        class _WrongPolicyAfterResumeStub(StubPlaywrightPage):
            def execute_portal_steps(self, *args, **kwargs) -> dict:
                data = super().execute_portal_steps(*args, **kwargs)
                data["extracted_policy_id"] = "POL-205118"  # Wrong policy opened during human intervention
                return data

        class _ReceiptAfterResumeStub(StubPlaywrightPage):
            def execute_portal_steps(self, *args, **kwargs) -> dict:
                data = super().execute_portal_steps(*args, **kwargs)
                data["submitted_or_receipt_visible"] = True
                data["current_portal_step"] = "Submission Receipt"
                return data

        stub_wrong_pol = _WrongPolicyAfterResumeStub(mode="no_check")
        stub_receipt = _ReceiptAfterResumeStub(mode="no_check")
        ACTIVE_HITL_SESSIONS["sess-wrong-pol"] = {
            "session_id": "sess-wrong-pol",
            "session_type": "tinyfish_browser_session",
            "created_at_epoch": 9999999999.0,
            "expires_at_epoch": 9999999999.0,
            "portal_url": DEFAULT_PORTAL_URL,
            "policy_id": "POL-100245",
            "diagnosis": "Acute Cholecystitis / ICD-10 K81.0",
            "estimated_cost": 85000,
            "room_category": "Semi-Private",
            "hospital_name": "Apollo Care Superspecialty Hospital",
            "doctor_name": "Dr. Rajesh K. Mehta",
            "use_sample_document": True,
            "page": stub_wrong_pol,
        }
        ACTIVE_HITL_SESSIONS["sess-receipt-viol"] = {
            "session_id": "sess-receipt-viol",
            "session_type": "tinyfish_browser_session",
            "created_at_epoch": 9999999999.0,
            "expires_at_epoch": 9999999999.0,
            "portal_url": DEFAULT_PORTAL_URL,
            "policy_id": "POL-100245",
            "diagnosis": "Acute Cholecystitis / ICD-10 K81.0",
            "estimated_cost": 85000,
            "room_category": "Semi-Private",
            "hospital_name": "Apollo Care Superspecialty Hospital",
            "doctor_name": "Dr. Rajesh K. Mehta",
            "use_sample_document": True,
            "page": stub_receipt,
        }
        wrong_pol_res = resume_verification_session("sess-wrong-pol")
        receipt_viol_res = resume_verification_session("sess-receipt-viol")
        post_resume_guards_ok = (
            wrong_pol_res.get("success") is False
            and wrong_pol_res.get("run_status") == "FIELD_MISMATCH"
            and receipt_viol_res.get("success") is False
            and receipt_viol_res.get("run_status") == "SUBMISSION_VIOLATION"
            and receipt_viol_res.get("submitted") is True
        )
        record(
            "35. Post-Resume Safeguards: Rejects wrong policy ID (FIELD_MISMATCH) & receipt screen (SUBMISSION_VIOLATION)",
            post_resume_guards_ok,
            f"wrong_policy: {wrong_pol_res.get('run_status')} | receipt_screen: {receipt_viol_res.get('run_status')}",
        )

    print(f"Summary: {passed_tests}/{total_tests} checks passed (0 TinyFish credits used).")
    if not all_passed:
        sys.exit(1)


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
