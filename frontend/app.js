/* ============================================================================
   MedVerify — Cashless Pre-Authorization Desk Client
   Configured for https://cpth1.vercel.app/
   ============================================================================ */

(function () {
  "use strict";

  const DEFAULT_PORTAL_URL = "https://cpth1.vercel.app/";

  // --------------------------------------------------------------------------
  // 1. BACKEND HEALTH TELEMETRY
  // --------------------------------------------------------------------------
  const navApiDot = document.getElementById("nav-api-dot");
  const navTelemetryBtn = document.getElementById("nav-telemetry-btn");

  let backendHealth = {
    api_key_configured: false,
    environment: "SANDBOX",
    default_portal_url: DEFAULT_PORTAL_URL,
    timing_stats: null
  };

  async function checkBackendHealth() {
    try {
      const res = await fetch("/api/health");
      if (!res.ok) throw new Error("Health check failed");
      backendHealth = await res.json();

      if (navApiDot) {
        navApiDot.classList.toggle("warn", !backendHealth.api_key_configured);
      }
      if (backendHealth.default_portal_url) {
        const urlInput = document.getElementById("portal-url-input");
        if (urlInput && !urlInput.value) {
          urlInput.value = backendHealth.default_portal_url;
        }
      }
    } catch (_) {
      // Keep default warning dot if offline
    }
  }

  if (navTelemetryBtn) {
    navTelemetryBtn.addEventListener("click", function () {
      const keyStatus = backendHealth.api_key_configured
        ? "CONFIGURED in Python environment"
        : "NOT SET (set $env:TINYFISH_API_KEY or .env before live cloud runs)";
      const tStats = backendHealth.timing_stats || {};
      alert(
        "MedVerify Backend Telemetry\n\n" +
          "• Authorized Portal: " + (backendHealth.default_portal_url || DEFAULT_PORTAL_URL) + "\n" +
          "• Environment: SANDBOX (Synthetic Data Only)\n" +
          "• TINYFISH_API_KEY: " + keyStatus + "\n" +
          "• Submission Lock: ENFORCED (submitted = False)\n" +
          "• Live Timing Telemetry: " + (tStats.observation_label || "No live runs recorded yet") + "\n" +
          "• Cross-Check Engine: Transparent Field-by-Field Evidence Audit"
      );
    });
  }

  checkBackendHealth();

  // --------------------------------------------------------------------------
  // 2. WORKSPACE LOGIC: LIVE TINYFISH BACKEND & SIMULATED DEMO (0 CREDITS)
  // --------------------------------------------------------------------------
  const modeLiveBtn = document.getElementById("mode-live-btn");
  const modeSimBtn = document.getElementById("mode-sim-btn");
  const navSimBtn = document.getElementById("nav-sim-btn");
  const simBanner = document.getElementById("sim-banner");
  const scenarioBtns = document.querySelectorAll(".scenario-btn");

  const presetSelect = document.getElementById("preset-select");
  const policyIdInput = document.getElementById("policy-id-input");
  const costInput = document.getElementById("cost-input");
  const diagnosisInput = document.getElementById("diagnosis-input");
  const roomCategorySelect = document.getElementById("room-category-select");
  const sampleDocSelect = document.getElementById("sample-doc-select");
  const portalUrlInput = document.getElementById("portal-url-input");
  const playwrightFallbackCheckbox = document.getElementById("playwright-fallback-checkbox");
  const verifyForm = document.getElementById("verify-form");
  const verifySubmitBtn = document.getElementById("verify-submit-btn");
  const verifyBtnText = document.getElementById("verify-btn-text");
  const guardrailTestBtn = document.getElementById("guardrail-test-btn");

  let currentMode = "live"; // "live" | "simulated"
  let liveTimerInterval = null;
  let activeHitlSessionId = null;
  let activeHitlPolicyId = null;
  let activeHitlPortalUrl = DEFAULT_PORTAL_URL;

  function buildActiveChecks(pid, name, roomLimit, copay, diag, costInputStr, stagedCostStr, roomCat, stagedRoomCat, docName, stopped, submitted) {
    const costMatch = String(costInputStr).replace(/[^\d]/g, "") === String(stagedCostStr).replace(/[^\d]/g, "");
    const roomCatMatch = String(roomCat).toLowerCase() === String(stagedRoomCat).toLowerCase();
    return [
      { field: "policy_id", label: "Policy ID", expected: pid, actual: pid, status: "PASS" },
      { field: "patient_name", label: "Patient Name", expected: name, actual: name, status: "PASS" },
      { field: "policy_status", label: "Policy Status", expected: "Active", actual: "Active", status: "PASS" },
      { field: "room_rent_limit", label: "Room-Rent Limit", expected: roomLimit, actual: roomLimit, status: "PASS" },
      { field: "co_payment", label: "Co-Payment", expected: copay, actual: copay, status: "PASS" },
      { field: "diagnosis", label: "Diagnosis (Review & Verify)", expected: diag, actual: diag, status: "PASS" },
      {
        field: "estimated_cost",
        label: "Estimated Cost (Review & Verify)",
        expected: String(costInputStr),
        actual: stagedCostStr,
        status: costMatch ? "PASS" : "MISMATCH"
      },
      {
        field: "room_category",
        label: "Room Category (Review & Verify)",
        expected: roomCat,
        actual: stagedRoomCat,
        status: roomCatMatch ? "PASS" : "MISMATCH"
      },
      {
        field: "supporting_document",
        label: "Supporting Clinical Document",
        expected: "sample_clinical_document.pdf",
        actual: docName || "Not staged",
        status: docName === "sample_clinical_document.pdf" ? "PASS" : "NOT VERIFIED"
      },
      {
        field: "review_screen_arrival",
        label: "Review-Screen Arrival",
        expected: "Review & Verify (stopped_at_review = true)",
        actual: stopped ? "Review & Verify (stopped_at_review = true)" : "Not reached (stopped_at_review = false)",
        status: stopped ? "PASS" : "NOT VERIFIED"
      },
      {
        field: "submission_safeguard",
        label: "Submission Status (Safeguard)",
        expected: "Not Submitted (submitted_or_receipt_visible = false, stopped_at_review = true)",
        actual: !submitted && stopped
          ? "Not Submitted (submitted_or_receipt_visible = false, halted at Review & Verify)"
          : "Unverified or violated safeguard state",
        status: !submitted && stopped ? "PASS" : (submitted ? "MISMATCH" : "NOT VERIFIED")
      }
    ];
  }

  // Confirmed Portal Scenarios matching https://medverify-tpa-portal.vercel.app/
  const SIMULATED_SCENARIOS = {
    pol100245: {
      is_simulated_demo: true,
      success: true,
      run_status: "SIMULATED_DEMO",
      policy_id: "POL-100245",
      extracted_policy_id: "POL-100245",
      portal_url: DEFAULT_PORTAL_URL,
      manual_fallback_url: DEFAULT_PORTAL_URL,
      elapsed_seconds: 0.0,
      timing: {
        elapsed_seconds: 0.0,
        is_measured_live_run: false,
        observation_label: "Simulated preview (0 credits — not measured)",
        manual_baseline_note: "No manual baseline measured in this environment"
      },
      policy_found: true,
      patient_name: "Rahul Sharma",
      insurer_name: "CareShield General Insurance — Optima Health Platinum Individual",
      policy_status: "Active",
      room_rent_limit: "₹5,000 / day (Single Standard AC Room)",
      copay_percentage: "0% (Nil)",
      co_payment: "0% (Nil)",
      fields_prepared: [
        "hospital_name",
        "doctor_name",
        "diagnosis",
        "admission_date",
        "estimated_cost",
        "room_category",
        "sample_clinical_document.pdf"
      ],
      document_uploaded: "sample_clinical_document.pdf",
      current_portal_step: "Review & Verify",
      staged_diagnosis: "Acute Cholecystitis / ICD-10 K81.0",
      staged_estimated_cost: "₹85,000",
      staged_room_category: "Semi-Private",
      form_prepared: true,
      stopped_at_review: true,
      submitted: false,
      submission_safeguard_verified: true,
      field_accuracy: {
        verified: true,
        fixture_source: "AUTHORITATIVE_PORTAL_FIXTURES[POL-100245]",
        total_checks: 11,
        passed_count: 11,
        mismatch_count: 0,
        not_verified_count: 0,
        checks: buildActiveChecks(
          "POL-100245",
          "Rahul Sharma",
          "₹5,000 / day (Single Standard AC Room)",
          "0% (Nil)",
          "Acute Cholecystitis / ICD-10 K81.0",
          "85000",
          "₹85,000",
          "Semi-Private",
          "Semi-Private",
          "sample_clinical_document.pdf",
          true,
          false
        ),
        matched_checks: ["11/11 checks passed"],
        policy_discrepancies: [],
        staging_discrepancies: [],
        discrepancies: []
      },
      notes: "SIMULATED DEMO (0 Credits) — Verified Active policy for Rahul Sharma (POL-100245), filled Pre-Authorization Form, attached sample_clinical_document.pdf, navigated to Review & Verify, and stopped without clicking Submit Pre-Authorization.",
      error: null
    },
    pol205118: {
      is_simulated_demo: true,
      success: true,
      run_status: "SIMULATED_DEMO",
      policy_id: "POL-205118",
      extracted_policy_id: "POL-205118",
      portal_url: DEFAULT_PORTAL_URL,
      manual_fallback_url: DEFAULT_PORTAL_URL,
      elapsed_seconds: 0.0,
      timing: {
        elapsed_seconds: 0.0,
        is_measured_live_run: false,
        observation_label: "Simulated preview (0 credits — not measured)",
        manual_baseline_note: "No manual baseline measured in this environment"
      },
      policy_found: true,
      patient_name: "Sunita Verma",
      insurer_name: "Heritage Life & Health Assurance — Senior Citizen Comprehensive Health",
      policy_status: "Active",
      room_rent_limit: "Single Private AC Room (up to 1% of Sum Insured)",
      copay_percentage: "10% Co-Pay applicable on total admitted claim amount",
      co_payment: "10% Co-Pay applicable on total admitted claim amount",
      fields_prepared: [
        "hospital_name",
        "doctor_name",
        "diagnosis",
        "admission_date",
        "estimated_cost",
        "room_category",
        "sample_clinical_document.pdf"
      ],
      document_uploaded: "sample_clinical_document.pdf",
      current_portal_step: "Review & Verify",
      staged_diagnosis: "Senile Nuclear Cataract / ICD-10 H25.1",
      staged_estimated_cost: "₹62,000",
      staged_room_category: "Semi-Private",
      form_prepared: true,
      stopped_at_review: true,
      submitted: false,
      submission_safeguard_verified: true,
      field_accuracy: {
        verified: true,
        fixture_source: "AUTHORITATIVE_PORTAL_FIXTURES[POL-205118]",
        total_checks: 11,
        passed_count: 11,
        mismatch_count: 0,
        not_verified_count: 0,
        checks: buildActiveChecks(
          "POL-205118",
          "Sunita Verma",
          "Single Private AC Room (up to 1% of Sum Insured)",
          "10% Co-Pay applicable on total admitted claim amount",
          "Senile Nuclear Cataract / ICD-10 H25.1",
          "62000",
          "₹62,000",
          "Semi-Private",
          "Semi-Private",
          "sample_clinical_document.pdf",
          true,
          false
        ),
        matched_checks: ["11/11 checks passed"],
        policy_discrepancies: [],
        staging_discrepancies: [],
        discrepancies: []
      },
      notes: "SIMULATED DEMO (0 Credits) — Verified Active policy for Sunita Verma (POL-205118), staged pre-authorization form & sample clinical document, and stopped at Review & Verify.",
      error: null
    },
    pol309872: {
      is_simulated_demo: true,
      success: true,
      run_status: "SIMULATED_DEMO",
      policy_id: "POL-309872",
      extracted_policy_id: "POL-309872",
      portal_url: DEFAULT_PORTAL_URL,
      manual_fallback_url: DEFAULT_PORTAL_URL,
      elapsed_seconds: 0.0,
      timing: {
        elapsed_seconds: 0.0,
        is_measured_live_run: false,
        observation_label: "Simulated preview (0 credits — not measured)",
        manual_baseline_note: "No manual baseline measured in this environment"
      },
      policy_found: true,
      patient_name: "Priya Nair",
      insurer_name: "Universal Alliance Health — Corporate Group Mediclaim (GMC)",
      policy_status: "Active",
      room_rent_limit: "No Capping / Actuals (Any category up to Deluxe)",
      copay_percentage: "0% (Waived under Corporate GMC)",
      co_payment: "0% (Waived under Corporate GMC)",
      fields_prepared: [
        "hospital_name",
        "doctor_name",
        "diagnosis",
        "admission_date",
        "estimated_cost",
        "room_category",
        "sample_clinical_document.pdf"
      ],
      document_uploaded: "sample_clinical_document.pdf",
      current_portal_step: "Review & Verify",
      staged_diagnosis: "Acute Appendicitis / ICD-10 K35.80",
      staged_estimated_cost: "₹95,000",
      staged_room_category: "Semi-Private",
      form_prepared: true,
      stopped_at_review: true,
      submitted: false,
      submission_safeguard_verified: true,
      field_accuracy: {
        verified: true,
        fixture_source: "AUTHORITATIVE_PORTAL_FIXTURES[POL-309872]",
        total_checks: 11,
        passed_count: 11,
        mismatch_count: 0,
        not_verified_count: 0,
        checks: buildActiveChecks(
          "POL-309872",
          "Priya Nair",
          "No Capping / Actuals (Any category up to Deluxe)",
          "0% (Waived under Corporate GMC)",
          "Acute Appendicitis / ICD-10 K35.80",
          "95000",
          "₹95,000",
          "Semi-Private",
          "Semi-Private",
          "sample_clinical_document.pdf",
          true,
          false
        ),
        matched_checks: ["11/11 checks passed"],
        policy_discrepancies: [],
        staging_discrepancies: [],
        discrepancies: []
      },
      notes: "SIMULATED DEMO (0 Credits) — Verified Active Corporate GMC policy for Priya Nair (POL-309872), staged pre-auth form & sample document, and stopped at Review & Verify.",
      error: null
    },
    pol999001: {
      is_simulated_demo: true,
      success: false,
      run_status: "POLICY_LAPSED",
      policy_id: "POL-999001",
      extracted_policy_id: "POL-999001",
      portal_url: DEFAULT_PORTAL_URL,
      manual_fallback_url: DEFAULT_PORTAL_URL,
      elapsed_seconds: 0.0,
      timing: {
        elapsed_seconds: 0.0,
        is_measured_live_run: false,
        observation_label: "Simulated preview (0 credits — not measured)",
        manual_baseline_note: "No manual baseline measured in this environment"
      },
      policy_found: true,
      patient_name: "Vikram Malhotra",
      insurer_name: "SecureLife Mediclaim Co. — Basic Hospitalization Floater",
      policy_status: "Lapsed",
      room_rent_limit: "₹3,000 / day",
      copay_percentage: "20%",
      co_payment: "20%",
      fields_prepared: [],
      document_uploaded: null,
      current_portal_step: "Policy Details",
      staged_diagnosis: null,
      staged_estimated_cost: null,
      staged_room_category: null,
      form_prepared: false,
      stopped_at_review: false,
      submitted: false,
      submission_safeguard_verified: true,
      field_accuracy: {
        verified: true,
        fixture_source: "AUTHORITATIVE_PORTAL_FIXTURES[POL-999001]",
        total_checks: 7,
        passed_count: 7,
        mismatch_count: 0,
        not_verified_count: 0,
        checks: [
          { field: "policy_id", label: "Policy ID", expected: "POL-999001", actual: "POL-999001", status: "PASS" },
          { field: "patient_name", label: "Patient Name", expected: "Vikram Malhotra", actual: "Vikram Malhotra", status: "PASS" },
          { field: "policy_status", label: "Policy Status", expected: "Lapsed", actual: "Lapsed", status: "PASS" },
          { field: "room_rent_limit", label: "Room-Rent Limit", expected: "₹3,000 / day", actual: "₹3,000 / day", status: "PASS" },
          { field: "co_payment", label: "Co-Payment", expected: "20%", actual: "20%", status: "PASS" },
          {
            field: "preauth_halt_on_lapsed",
            label: "Lapsed-Policy Pre-Auth Halt",
            expected: "Policy Details (fields_prepared = [], stopped_at_review = false)",
            actual: "Policy Details (fields_prepared = 0, stopped_at_review = false)",
            status: "PASS"
          },
          {
            field: "submission_safeguard",
            label: "Submission Status (Safeguard)",
            expected: "Not Submitted (submitted_or_receipt_visible = false)",
            actual: "Not Submitted (submitted_or_receipt_visible = false)",
            status: "PASS"
          }
        ],
        matched_checks: ["7/7 checks passed"],
        policy_discrepancies: [],
        staging_discrepancies: [],
        discrepancies: []
      },
      notes: "SIMULATED DEMO (0 Credits) — Policy POL-999001 (Vikram Malhotra) is Lapsed (expired 2024-12-31). Pre-authorization cannot be initiated.",
      error: "Policy 'POL-999001' status is Lapsed. Cashless pre-authorization cannot be initiated for a lapsed policy."
    },
    unknown: {
      is_simulated_demo: true,
      success: false,
      run_status: "NOT_FOUND",
      policy_id: "POL-999999",
      extracted_policy_id: "",
      portal_url: DEFAULT_PORTAL_URL,
      manual_fallback_url: DEFAULT_PORTAL_URL,
      elapsed_seconds: 0.0,
      timing: {
        elapsed_seconds: 0.0,
        is_measured_live_run: false,
        observation_label: "Simulated preview (0 credits — not measured)",
        manual_baseline_note: "No manual baseline measured in this environment"
      },
      policy_found: false,
      patient_name: null,
      insurer_name: null,
      policy_status: "Not Found",
      room_rent_limit: null,
      copay_percentage: null,
      co_payment: null,
      fields_prepared: [],
      document_uploaded: null,
      current_portal_step: "Policy Search",
      staged_diagnosis: null,
      staged_estimated_cost: null,
      staged_room_category: null,
      form_prepared: false,
      stopped_at_review: false,
      submitted: false,
      submission_safeguard_verified: true,
      field_accuracy: {
        verified: true,
        fixture_source: "unknown_policy_rule",
        total_checks: 3,
        passed_count: 3,
        mismatch_count: 0,
        not_verified_count: 0,
        checks: [
          {
            field: "policy_id",
            label: "Policy ID Lookup",
            expected: "POL-999999 (Unlisted / Unknown Policy ID)",
            actual: "Rejected on Policy Search (policy_found = false)",
            status: "PASS"
          },
          {
            field: "policy_status",
            label: "Policy Status",
            expected: "Not Found",
            actual: "Not Found",
            status: "PASS"
          },
          {
            field: "submission_safeguard",
            label: "Submission Status (Safeguard)",
            expected: "Not Submitted (submitted_or_receipt_visible = false)",
            actual: "Not Submitted (submitted_or_receipt_visible = false)",
            status: "PASS"
          }
        ],
        matched_checks: ["unknown_policy_correctly_rejected"],
        policy_discrepancies: [],
        staging_discrepancies: [],
        discrepancies: []
      },
      notes: "SIMULATED DEMO (0 Credits) — Policy ID 'POL-999999' was not found in ApexCare TPA records.",
      error: "Policy 'POL-999999' was not found in TPA portal records."
    },
    mismatch: {
      is_simulated_demo: true,
      success: false,
      run_status: "FIELD_MISMATCH",
      policy_id: "POL-100245",
      extracted_policy_id: "POL-100245",
      portal_url: DEFAULT_PORTAL_URL,
      manual_fallback_url: DEFAULT_PORTAL_URL,
      elapsed_seconds: 0.0,
      timing: {
        elapsed_seconds: 0.0,
        is_measured_live_run: false,
        observation_label: "Simulated preview (0 credits — not measured)",
        manual_baseline_note: "No manual baseline measured in this environment"
      },
      policy_found: true,
      patient_name: "Rahul Sharma",
      insurer_name: "CareShield General Insurance",
      policy_status: "Active",
      room_rent_limit: "₹5,000 / day (Single Standard AC Room)",
      copay_percentage: "0% (Nil)",
      co_payment: "0% (Nil)",
      fields_prepared: ["diagnosis", "estimated_cost", "room_category"],
      document_uploaded: "sample_clinical_document.pdf",
      current_portal_step: "Review & Verify",
      staged_diagnosis: "Acute Cholecystitis / ICD-10 K81.0",
      staged_estimated_cost: "₹12,000",
      staged_room_category: "General",
      form_prepared: true,
      stopped_at_review: true,
      submitted: false,
      submission_safeguard_verified: true,
      field_accuracy: {
        verified: false,
        fixture_source: "AUTHORITATIVE_PORTAL_FIXTURES[POL-100245]",
        total_checks: 11,
        passed_count: 9,
        mismatch_count: 2,
        not_verified_count: 0,
        checks: buildActiveChecks(
          "POL-100245",
          "Rahul Sharma",
          "₹5,000 / day (Single Standard AC Room)",
          "0% (Nil)",
          "Acute Cholecystitis / ICD-10 K81.0",
          "85000",
          "₹12,000",
          "Semi-Private",
          "General",
          "sample_clinical_document.pdf",
          true,
          false
        ),
        matched_checks: ["9/11 checks passed"],
        policy_discrepancies: [],
        staging_discrepancies: [
          "staged_estimated_cost mismatch: submitted '85000', review screen showed '₹12,000'",
          "staged_room_category mismatch: submitted 'Semi-Private', review screen showed 'General'"
        ],
        discrepancies: [
          "staged_estimated_cost mismatch: submitted '85000', review screen showed '₹12,000'",
          "staged_room_category mismatch: submitted 'Semi-Private', review screen showed 'General'"
        ]
      },
      notes: "SIMULATED DEMO (0 Credits) — Demonstrates how MedVerify rejects a run when the staged Review & Verify values do not match the submitted case inputs.",
      error: "Field verification mismatch detected: staged_estimated_cost mismatch: submitted '85000', review screen showed '₹12,000'; staged_room_category mismatch: submitted 'Semi-Private', review screen showed 'General'"
    }
  };

  function isPolicyInactive(status) {
    if (!status) return false;
    const s = String(status).toLowerCase();
    return ["lapsed", "expired", "inactive", "cancelled", "canceled", "suspended"].some(function (k) {
      return s.includes(k);
    });
  }

  function isPolicyActive(status) {
    if (!status) return false;
    const s = String(status).toLowerCase();
    if (isPolicyInactive(s)) return false;
    return s.includes("active") || s.includes("valid");
  }

  // Clear all previous results immediately so stale data is NEVER displayed
  function resetWorkspaceDisplay(statusMessageHtml, bannerTone) {
    if (liveTimerInterval) {
      clearInterval(liveTimerInterval);
      liveTimerInterval = null;
    }
    activeHitlSessionId = null;
    const hitlActionBar = document.getElementById("hitl-action-bar");
    if (hitlActionBar) {
      hitlActionBar.style.display = "none";
    }
    const modeBadge = document.getElementById("result-mode-badge");
    const banner = document.getElementById("ws-status-banner");

    const chipStatus = document.getElementById("chip-status");
    const valStatus = document.getElementById("val-status");
    const subStatus = document.getElementById("sub-status");

    const chipRoom = document.getElementById("chip-room");
    const valRoom = document.getElementById("val-room");
    const subRoom = document.getElementById("sub-room");

    const chipCopay = document.getElementById("chip-copay");
    const valCopay = document.getElementById("val-copay");
    const subCopay = document.getElementById("sub-copay");

    const evPortalStep = document.getElementById("ev-portal-step");
    const evStagedSummary = document.getElementById("ev-staged-summary");
    const evAccuracy = document.getElementById("ev-accuracy");
    const evPrepTime = document.getElementById("ev-prep-time");

    const auditSummaryBadge = document.getElementById("audit-summary-badge");
    const auditTableBody = document.getElementById("audit-table-body");

    const tlStep1 = document.getElementById("tl-step-1");
    const tlBadge1 = document.getElementById("tl-badge-1");
    const tlDesc1 = document.getElementById("tl-desc-1");

    const tlStep2 = document.getElementById("tl-step-2");
    const tlBadge2 = document.getElementById("tl-badge-2");
    const tlDesc2 = document.getElementById("tl-desc-2");
    const tlFieldsWrap = document.getElementById("tl-fields-wrap");

    const tlStep3 = document.getElementById("tl-step-3");
    const tlBadge3 = document.getElementById("tl-badge-3");
    const tlDesc3 = document.getElementById("tl-desc-3");

    const gateStopped = document.getElementById("gate-stopped-val");
    const gateSubmitted = document.getElementById("gate-submitted-val");
    const rawJsonPre = document.getElementById("raw-json-pre");

    if (modeBadge) modeBadge.textContent = "02 / 03 · STANDBY";
    if (banner) {
      banner.className = "ws-status-banner" + (bannerTone ? " " + bannerTone : "");
      banner.innerHTML =
        statusMessageHtml ||
        "<strong>Ready for Verification:</strong> Click <strong>Verify Policy &amp; Stage Form (Live SDK)</strong> to launch real TinyFish automation against <code>https://cpth1.vercel.app/</code>.";
    }

    if (valStatus) {
      valStatus.textContent = "—";
      valStatus.className = "vital-reading muted";
    }
    if (chipStatus) {
      chipStatus.textContent = "IDLE";
      chipStatus.className = "vital-chip";
    }
    if (subStatus) subStatus.textContent = "Portal verification state";

    if (valRoom) {
      valRoom.textContent = "—";
      valRoom.className = "vital-reading muted";
    }
    if (chipRoom) {
      chipRoom.textContent = "IDLE";
      chipRoom.className = "vital-chip";
    }
    if (subRoom) subRoom.textContent = "Daily inpatient cap";

    if (valCopay) {
      valCopay.textContent = "—";
      valCopay.className = "vital-reading muted";
    }
    if (chipCopay) {
      chipCopay.textContent = "IDLE";
      chipCopay.className = "vital-chip";
    }
    if (subCopay) subCopay.textContent = "Policyholder share %";

    if (evPortalStep) evPortalStep.textContent = "—";
    if (evStagedSummary) evStagedSummary.textContent = "—";
    if (evAccuracy) {
      evAccuracy.textContent = "—";
      evAccuracy.style.color = "";
    }
    if (evPrepTime) {
      evPrepTime.innerHTML = "&mdash; <small>(Unmeasured)</small>";
      evPrepTime.title = "Measured from backend verify_policy() start to TinyFish response & audit completion";
    }

    if (auditSummaryBadge) {
      auditSummaryBadge.textContent = "0 CHECKS RUN";
      auditSummaryBadge.className = "audit-summary-badge";
    }
    if (auditTableBody) {
      auditTableBody.innerHTML =
        '<tr><td colspan="4" class="audit-empty-cell">No field-accuracy checks executed yet. Run live verification or preview a scenario to inspect field-by-field evidence.</td></tr>';
    }

    [tlStep1, tlStep2, tlStep3].forEach(function (el) {
      if (el) el.className = "ws-tl-item";
    });
    if (tlBadge1) tlBadge1.textContent = "PENDING";
    if (tlDesc1) tlDesc1.textContent = "Opens Policy Search, queries Policy ID, and extracts patient name, status, room-rent limit, and co-payment clause.";
    if (tlBadge2) tlBadge2.textContent = "PENDING";
    if (tlDesc2) tlDesc2.innerHTML = "Driven by Active status: populates Diagnosis, Cost &amp; Room Category, and stages <code>sample_clinical_document.pdf</code>.";
    if (tlFieldsWrap) tlFieldsWrap.innerHTML = "";
    if (tlBadge3) tlBadge3.textContent = "LOCKED";
    if (tlDesc3) tlDesc3.textContent = "Reads back staged values on Review & Verify, cross-checks against case inputs, and halts without submitting.";

    if (gateStopped) gateStopped.textContent = "—";
    if (gateSubmitted) {
      gateSubmitted.textContent = "false (Locked)";
      gateSubmitted.style.color = "#10B981";
    }
    if (rawJsonPre) rawJsonPre.textContent = "Awaiting verification run...";
  }

  function renderWaitingForHumanCheck(detailMessage) {
    const modeBadge = document.getElementById("result-mode-badge");
    const banner = document.getElementById("ws-status-banner");
    const chipStatus = document.getElementById("chip-status");
    const valStatus = document.getElementById("val-status");
    const subStatus = document.getElementById("sub-status");
    const evPortalStep = document.getElementById("ev-portal-step");
    const tlStep1 = document.getElementById("tl-step-1");
    const tlBadge1 = document.getElementById("tl-badge-1");
    const tlDesc1 = document.getElementById("tl-desc-1");

    if (modeBadge) modeBadge.textContent = "02 / 03 · Waiting for human check";
    if (banner) {
      banner.className = "ws-status-banner tone-warn";
      banner.innerHTML =
        "<strong>Waiting for human check:</strong> " +
        (detailMessage ||
          "Local headed Chromium is paused at a verification/CAPTCHA challenge. Please complete the check in the visible browser window; MedVerify will resume automatically when the 'Policy Search' heading appears (timeout: 5m).");
    }
    if (valStatus) {
      valStatus.textContent = "Waiting for human check";
      valStatus.className = "vital-reading";
    }
    if (chipStatus) {
      chipStatus.textContent = "HUMAN CHECK";
      chipStatus.className = "vital-chip chip-warn";
    }
    if (subStatus) {
      subStatus.textContent = "Paused in headed Chromium window";
    }
    if (evPortalStep) {
      evPortalStep.textContent = "Waiting for human check";
    }
    if (tlStep1) tlStep1.className = "ws-tl-item warn";
    if (tlBadge1) tlBadge1.textContent = "Waiting for human check";
    if (tlDesc1) {
      tlDesc1.textContent =
        "Paused for human verification in headed Chromium. Resumes automatically when 'Policy Search' appears.";
    }
  }

  function renderAuditTable(acc) {
    const auditSummaryBadge = document.getElementById("audit-summary-badge");
    const auditTableBody = document.getElementById("audit-table-body");
    const evAccuracy = document.getElementById("ev-accuracy");

    const checks = acc && Array.isArray(acc.checks) ? acc.checks : [];
    const total = checks.length;
    const passCount = checks.filter(function (c) { return c.status === "PASS"; }).length;
    const mismatchCount = checks.filter(function (c) { return c.status === "MISMATCH"; }).length;
    const notVerifiedCount = checks.filter(function (c) { return c.status === "NOT VERIFIED"; }).length;

    if (auditSummaryBadge) {
      if (total === 0) {
        auditSummaryBadge.textContent = "0 CHECKS RUN · NOT VERIFIED";
        auditSummaryBadge.className = "audit-summary-badge badge-warn";
      } else {
        auditSummaryBadge.textContent =
          passCount + " / " + total + " PASS · " +
          mismatchCount + " MISMATCH · " +
          notVerifiedCount + " NOT VERIFIED";
        if (mismatchCount > 0) {
          auditSummaryBadge.className = "audit-summary-badge badge-err";
        } else if (notVerifiedCount > 0) {
          auditSummaryBadge.className = "audit-summary-badge badge-warn";
        } else {
          auditSummaryBadge.className = "audit-summary-badge badge-ok";
        }
      }
    }

    if (evAccuracy) {
      if (total === 0) {
        evAccuracy.textContent = "NOT VERIFIED (0 checks)";
        evAccuracy.style.color = "#D97706";
      } else if (mismatchCount > 0) {
        evAccuracy.textContent = "MISMATCH (" + mismatchCount + " failed, " + passCount + "/" + total + " pass)";
        evAccuracy.style.color = "#DC2626";
      } else if (notVerifiedCount > 0) {
        evAccuracy.textContent = "NOT VERIFIED (" + notVerifiedCount + " unverified, " + passCount + "/" + total + " pass)";
        evAccuracy.style.color = "#D97706";
      } else {
        evAccuracy.textContent = "PASS (" + passCount + "/" + total + " checks)";
        evAccuracy.style.color = "#065F46";
      }
    }

    if (auditTableBody) {
      auditTableBody.innerHTML = "";
      if (total === 0) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 4;
        td.className = "audit-empty-cell";
        td.textContent =
          (acc && acc.discrepancies && acc.discrepancies.length > 0)
            ? "No portal field checks executed (" + acc.discrepancies.join("; ") + ")."
            : "No field-accuracy checks executed for this run.";
        tr.appendChild(td);
        auditTableBody.appendChild(tr);
        return;
      }

      checks.forEach(function (chk) {
        const tr = document.createElement("tr");

        const tdField = document.createElement("td");
        tdField.className = "audit-field-col";
        tdField.textContent = chk.label || chk.field || "—";

        const tdExpected = document.createElement("td");
        tdExpected.textContent = chk.expected != null ? String(chk.expected) : "—";

        const tdActual = document.createElement("td");
        tdActual.textContent = chk.actual != null ? String(chk.actual) : "—";

        const tdStatus = document.createElement("td");
        const pill = document.createElement("span");
        const st = String(chk.status || "NOT VERIFIED").toUpperCase();
        pill.textContent = st;
        if (st === "PASS") {
          pill.className = "audit-status-pill status-pass";
        } else if (st === "MISMATCH") {
          pill.className = "audit-status-pill status-mismatch";
        } else {
          pill.className = "audit-status-pill status-unverified";
        }
        tdStatus.appendChild(pill);

        tr.appendChild(tdField);
        tr.appendChild(tdExpected);
        tr.appendChild(tdActual);
        tr.appendChild(tdStatus);
        auditTableBody.appendChild(tr);
      });
    }
  }

  function renderVerificationResult(data) {
    if (!data) return;

    // Always wipe all previous DOM state first so no stale patient name, coverage value,
    // prepared-field badge, audit row, or success banner can ever persist across transitions.
    resetWorkspaceDisplay();

    const modeBadge = document.getElementById("result-mode-badge");
    const banner = document.getElementById("ws-status-banner");

    const chipStatus = document.getElementById("chip-status");
    const valStatus = document.getElementById("val-status");
    const subStatus = document.getElementById("sub-status");

    const chipRoom = document.getElementById("chip-room");
    const valRoom = document.getElementById("val-room");

    const chipCopay = document.getElementById("chip-copay");
    const valCopay = document.getElementById("val-copay");

    const evPortalStep = document.getElementById("ev-portal-step");
    const evStagedSummary = document.getElementById("ev-staged-summary");
    const evPrepTime = document.getElementById("ev-prep-time");

    const tlStep1 = document.getElementById("tl-step-1");
    const tlBadge1 = document.getElementById("tl-badge-1");
    const tlDesc1 = document.getElementById("tl-desc-1");

    const tlStep2 = document.getElementById("tl-step-2");
    const tlBadge2 = document.getElementById("tl-badge-2");
    const tlDesc2 = document.getElementById("tl-desc-2");
    const tlFieldsWrap = document.getElementById("tl-fields-wrap");

    const tlStep3 = document.getElementById("tl-step-3");
    const tlBadge3 = document.getElementById("tl-badge-3");
    const tlDesc3 = document.getElementById("tl-desc-3");

    const gateStopped = document.getElementById("gate-stopped-val");
    const gateSubmitted = document.getElementById("gate-submitted-val");
    const manualFallbackLink = document.getElementById("manual-fallback-link");
    const rawJsonPre = document.getElementById("raw-json-pre");

    const isSim = Boolean(data.is_simulated_demo);
    const prefixTag = isSim ? "SIMULATED (0 CREDITS)" : "LIVE TINYFISH";
    if (modeBadge) {
      modeBadge.textContent = "02 / 03 · " + prefixTag;
    }

    if (rawJsonPre) {
      rawJsonPre.textContent = JSON.stringify(data, null, 2);
    }

    const fallbackUrl = data.manual_fallback_url || data.portal_url || DEFAULT_PORTAL_URL;
    if (manualFallbackLink && fallbackUrl.startsWith("http")) {
      manualFallbackLink.href = fallbackUrl;
    }

    const policyFound = Boolean(data.policy_found);
    const pStatus = data.policy_status;
    const patientName = data.patient_name;
    const rLimit = data.room_rent_limit;
    const copay = data.copay_percentage || data.co_payment;
    const fields = Array.isArray(data.fields_prepared) ? data.fields_prepared : [];
    const stopped = Boolean(data.stopped_at_review);
    const submitted = Boolean(data.submitted);
    const inactive = isPolicyInactive(pStatus);
    const active = isPolicyActive(pStatus);
    const acc = data.field_accuracy || {};
    const accVerified = Boolean(acc.verified);
    const timing = data.timing || {};

    if (gateStopped) gateStopped.textContent = String(stopped);
    if (gateSubmitted) {
      if (submitted) {
        gateSubmitted.textContent = "true (VIOLATION)";
        gateSubmitted.style.color = "#DC2626";
      } else if (data.submission_safeguard_verified === false && policyFound) {
        gateSubmitted.textContent = "false (Unverified)";
        gateSubmitted.style.color = "#F59E0B";
      } else {
        gateSubmitted.textContent = "false (Locked)";
        gateSubmitted.style.color = "#10B981";
      }
    }

    // Update Evaluation Evidence Strip & Transparent Audit Table
    if (evPortalStep) {
      evPortalStep.textContent = data.current_portal_step || (stopped ? "Review & Verify" : "Halted");
    }
    if (evStagedSummary) {
      if (data.staged_diagnosis || data.staged_estimated_cost || data.staged_room_category) {
        evStagedSummary.textContent =
          (data.staged_diagnosis || "—") +
          " · " +
          (data.staged_estimated_cost || "—") +
          (data.staged_room_category ? " (" + data.staged_room_category + ")" : "");
      } else {
        evStagedSummary.textContent = "Not staged";
      }
    }

    renderAuditTable(acc);

    if (evPrepTime) {
      if (isSim) {
        evPrepTime.innerHTML = "0.0s <small>(Simulated — not measured)</small>";
      } else if (typeof data.elapsed_seconds === "number" && data.elapsed_seconds > 0) {
        const obsLabel = timing.observation_label || "Single-run observation";
        evPrepTime.innerHTML = data.elapsed_seconds.toFixed(1) + "s <small>(" + obsLabel + ")</small>";
        if (timing.start_boundary && timing.end_boundary) {
          evPrepTime.title =
            "Start: " + timing.start_boundary + " | End: " + timing.end_boundary +
            " (" + (timing.manual_baseline_note || "No manual baseline") + ")";
        }
      } else {
        evPrepTime.innerHTML = "&mdash; <small>(Pre-dispatch check)</small>";
      }
    }

    // CASE 1: Policy NOT found or guardrail/auth/HITL/SDK halt (policy_found === false)
    if (!policyFound) {
      const isHitl =
        data.run_status === "HUMAN_ACTION_REQUIRED" || Boolean(data.human_action_required);
      const isCancelled = data.run_status === "USER_CANCELLED";
      const isSessionLost = data.run_status === "SESSION_EXPIRED_OR_UNAVAILABLE";
      const hitlMeta = data.human_intervention || {};
      const hitlActionBar = document.getElementById("hitl-action-bar");
      const hitlActionText = document.getElementById("hitl-action-text");
      const hitlSessionBadge = document.getElementById("hitl-session-badge");
      const btnHitlResume = document.getElementById("btn-hitl-resume");
      const hitlManualLink = document.getElementById("hitl-manual-link");

      if (isHitl) {
        activeHitlSessionId = data.session_id || hitlMeta.session_id || null;
        activeHitlPolicyId = data.policy_id || "";
        activeHitlPortalUrl = fallbackUrl;
        const canResume = Boolean(
          data.can_resume_same_session || hitlMeta.can_resume_same_session
        );
        const actionMsg =
          hitlMeta.action_required ||
          data.error ||
          "Complete the CAPTCHA, MFA, or login challenge in the active browser session, then click Continue After Human Verification or use the Manual Portal Fallback.";

        if (banner) {
          banner.className = "ws-status-banner tone-warn";
          banner.innerHTML =
            "<strong>Workflow Paused — Human Action Required (HUMAN_ACTION_REQUIRED):</strong> " +
            actionMsg;
        }
        if (hitlActionBar) {
          hitlActionBar.style.display = "block";
        }
        if (hitlActionText) {
          hitlActionText.textContent =
            (hitlMeta.challenge_reason ? hitlMeta.challenge_reason + " — " : "") + actionMsg;
        }
        if (hitlSessionBadge) {
          hitlSessionBadge.textContent = canResume
            ? "SESSION ACTIVE: " + activeHitlSessionId
            : "NO SAME-SESSION HANDLE (USE MANUAL FALLBACK)";
        }
        if (btnHitlResume) {
          btnHitlResume.disabled = false;
          btnHitlResume.style.opacity = "1";
          btnHitlResume.textContent = canResume
            ? "Continue After Human Verification →"
            : "Complete CAPTCHA in Browser & Continue →";
        }
        if (hitlManualLink && fallbackUrl.startsWith("http")) {
          hitlManualLink.href = fallbackUrl;
        }

        if (valStatus) {
          valStatus.textContent = "Human Action Required";
          valStatus.className = "vital-reading";
        }
        if (chipStatus) {
          chipStatus.textContent = "HUMAN ACTION";
          chipStatus.className = "vital-chip chip-warn";
        }
        if (subStatus) {
          subStatus.textContent = canResume
            ? "Paused in session " + activeHitlSessionId
            : "Paused at portal access challenge";
        }
        if (tlStep1) tlStep1.classList.add("warn");
        if (tlBadge1) tlBadge1.textContent = "HUMAN_ACTION_REQUIRED";
        if (tlDesc1) tlDesc1.textContent = actionMsg;
      } else {
        if (banner) {
          banner.className = "ws-status-banner tone-err";
          banner.innerHTML =
            "<strong>" +
            (isSim ? "[Simulated Demo] " : "") +
            "Verification Halted (" +
            (data.run_status || "FAILED") +
            "):</strong> " +
            (data.error || "Policy lookup did not succeed.") +
            " No coverage values were fabricated.";
        }

        if (valStatus) {
          valStatus.textContent = isCancelled
            ? "Cancelled by User"
            : isSessionLost
            ? "Session Expired"
            : pStatus || "Unverified";
          valStatus.className = "vital-reading" + (pStatus || isCancelled || isSessionLost ? "" : " muted");
        }
        if (chipStatus) {
          chipStatus.textContent =
            data.run_status === "NOT_FOUND"
              ? "NOT FOUND"
              : isCancelled
              ? "CANCELLED"
              : isSessionLost
              ? "SESSION LOST"
              : "ERROR";
          chipStatus.className = "vital-chip chip-err";
        }
        if (subStatus) subStatus.textContent = "Run status: " + (data.run_status || "FAILED");

        if (tlStep1) tlStep1.classList.add("err");
        if (tlBadge1) tlBadge1.textContent = data.run_status || "FAILED";
        if (tlDesc1) tlDesc1.textContent = data.error || "Policy lookup did not succeed.";
      }

      if (valRoom) {
        valRoom.textContent = "—";
        valRoom.className = "vital-reading muted";
      }
      if (chipRoom) {
        chipRoom.textContent = "UNAVAILABLE";
        chipRoom.className = "vital-chip";
      }

      if (valCopay) {
        valCopay.textContent = "—";
        valCopay.className = "vital-reading muted";
      }
      if (chipCopay) {
        chipCopay.textContent = "UNAVAILABLE";
        chipCopay.className = "vital-chip";
      }

      if (tlBadge2) tlBadge2.textContent = isHitl ? "PAUSED" : "SKIPPED";
      if (tlDesc2) {
        tlDesc2.textContent = isHitl
          ? "Awaiting human challenge completion before staging pre-authorization fields."
          : "Pre-authorization form & document staging skipped because policy lookup failed.";
      }

      if (tlBadge3) tlBadge3.textContent = "NOT REACHED";
      if (tlDesc3) tlDesc3.textContent = "Workflow halted before Review & Verify.";
      return;
    }

    // CASE 2: Policy WAS found on the portal (Active, Lapsed, Field Mismatch, or Incomplete)
    const isGenuineSuccess = Boolean(data.success && active && stopped && !submitted && accVerified);

    if (valStatus) {
      valStatus.textContent = pStatus || "Unspecified";
      valStatus.className = "vital-reading";
    }
    if (chipStatus) {
      chipStatus.textContent = inactive
        ? "LAPSED"
        : isGenuineSuccess
        ? (isSim ? "SIMULATED" : "ACTIVE")
        : "UNVERIFIED";
      chipStatus.className = "vital-chip " + (isGenuineSuccess ? "chip-ok" : inactive ? "chip-err" : "chip-warn");
    }
    if (subStatus) {
      subStatus.textContent = patientName
        ? patientName + " · " + (data.policy_id || "")
        : "Policy ID: " + (data.policy_id || "—");
    }

    if (valRoom) {
      valRoom.textContent = rLimit || "Not reported";
      valRoom.className = "vital-reading" + (rLimit ? "" : " muted");
    }
    if (chipRoom) {
      chipRoom.textContent = rLimit ? (isSim ? "SIMULATED" : "EXTRACTED") : "MISSING";
      chipRoom.className = "vital-chip " + (rLimit && isGenuineSuccess ? "chip-ok" : "chip-warn");
    }

    if (valCopay) {
      valCopay.textContent = copay || "Not reported";
      valCopay.className = "vital-reading" + (copay ? "" : " muted");
    }
    if (chipCopay) {
      chipCopay.textContent = copay ? (isSim ? "SIMULATED" : "EXTRACTED") : "MISSING";
      chipCopay.className = "vital-chip " + (copay && isGenuineSuccess ? "chip-ok" : "chip-warn");
    }

    // Timeline Step 1: Policy Search & Coverage Extraction
    const hasPolMismatch = Array.isArray(acc.policy_discrepancies) && acc.policy_discrepancies.length > 0;
    if (tlStep1) tlStep1.classList.add(hasPolMismatch ? "err" : inactive ? "warn" : "done");
    if (tlBadge1) {
      tlBadge1.textContent = hasPolMismatch
        ? "MISMATCH"
        : inactive
        ? "FOUND (LAPSED)"
        : "VERIFIED";
    }
    if (tlDesc1) {
      tlDesc1.textContent = hasPolMismatch
        ? "Policy extraction discrepancy: " + acc.policy_discrepancies.join("; ")
        : inactive
        ? "Located policy record for " + (patientName || data.policy_id) + ", but status is '" + pStatus + "'."
        : "Extracted and verified policy record for " + (patientName || data.policy_id) + ".";
    }

    // Timeline Step 2: Pre-Auth Form & Document Upload
    const hasStageMismatch = Array.isArray(acc.staging_discrepancies) && acc.staging_discrepancies.length > 0;
    if (inactive) {
      if (tlStep2) tlStep2.classList.add("err");
      if (tlBadge2) tlBadge2.textContent = "BLOCKED (LAPSED)";
      if (tlDesc2) tlDesc2.textContent = "Extracted Lapsed status prevented pre-authorization preparation.";
    } else if (data.run_status === "FIELD_MISMATCH" && hasStageMismatch) {
      if (tlStep2) tlStep2.classList.add("err");
      if (tlBadge2) tlBadge2.textContent = "FIELD MISMATCH";
      if (tlDesc2) tlDesc2.textContent = "Staged form values did not match submitted case inputs: " + acc.staging_discrepancies.join("; ");
    } else if (isGenuineSuccess && fields.length > 0) {
      if (tlStep2) tlStep2.classList.add("done");
      if (tlBadge2) tlBadge2.textContent = fields.length + " ITEMS STAGED";
      if (tlDesc2) tlDesc2.textContent = "Populated Pre-Authorization Form and attached synthetic clinical document:";
      if (tlFieldsWrap) {
        fields.forEach(function (f) {
          const span = document.createElement("span");
          span.className = "prepared-tag";
          span.textContent = f;
          tlFieldsWrap.appendChild(span);
        });
      }
    } else {
      if (tlStep2) tlStep2.classList.add("warn");
      if (tlBadge2) tlBadge2.textContent = "INCOMPLETE";
      if (tlDesc2) tlDesc2.textContent = "Pre-authorization form staging or review read-back was incomplete.";
    }

    // Timeline Step 3: Review & Verify Screen Halt & Cross-Check
    if (inactive) {
      if (tlBadge3) tlBadge3.textContent = "NOT REACHED";
      if (tlDesc3) tlDesc3.textContent = "Halted on Policy Details screen due to Lapsed policy status.";
    } else if (isGenuineSuccess) {
      if (tlStep3) tlStep3.classList.add("done");
      if (tlBadge3) tlBadge3.textContent = "STOPPED & VERIFIED";
      if (tlDesc3) tlDesc3.textContent = "Reached Review & Verify, verified all 11 field checks against case inputs, and stopped without clicking Submit.";
    } else if (stopped && !accVerified) {
      if (tlStep3) tlStep3.classList.add("err");
      if (tlBadge3) tlBadge3.textContent = "MISMATCH AT REVIEW";
      if (tlDesc3) tlDesc3.textContent = "Reached Review & Verify, but cross-check found discrepancies requiring coordinator correction.";
    } else {
      if (tlStep3) tlStep3.classList.add("warn");
      if (tlBadge3) tlBadge3.textContent = "INCOMPLETE HALT";
      if (tlDesc3) tlDesc3.textContent = "Agent did not confirm stopping at Review & Verify. Manual check required.";
    }

    // Banner state: Only isGenuineSuccess renders green!
    if (inactive) {
      if (banner) {
        banner.className = "ws-status-banner tone-err";
        banner.innerHTML =
          "<strong>" +
          (isSim ? "[Simulated Demo] " : "") +
          "Verification Halted — Policy Lapsed (" +
          (data.policy_id || "") +
          "):</strong> " +
          (data.error || "Cashless pre-authorization is prohibited for a lapsed policy.");
      }
    } else if (data.run_status === "FIELD_MISMATCH") {
      if (banner) {
        banner.className = "ws-status-banner tone-err";
        banner.innerHTML =
          "<strong>" +
          (isSim ? "[Simulated Demo] " : "") +
          "Verification Rejected — Field Mismatch Detected:</strong> " +
          (data.error || "Extracted or staged values did not match expected case inputs.");
      }
    } else if (isGenuineSuccess) {
      if (banner) {
        banner.className = "ws-status-banner tone-ok";
        banner.innerHTML =
          "<strong>" +
          (isSim ? "[Simulated Demo] " : "") +
          "Policy Verified &amp; Staged at Review &amp; Verify:</strong> " +
          (data.notes || "All coverage terms and staged form fields cross-checked and halted before submission.");
      }
    } else {
      if (banner) {
        banner.className = "ws-status-banner tone-warn";
        banner.innerHTML =
          "<strong>" +
          (isSim ? "[Simulated Demo] " : "") +
          "Incomplete Verification — Coordinator Check Required:</strong> " +
          (data.error || data.notes || "Workflow did not complete all staging steps.");
      }
    }
  }

  function setExecutionMode(mode) {
    currentMode = mode;
    const isSim = mode === "simulated";
    if (modeLiveBtn) {
      modeLiveBtn.classList.toggle("active", !isSim);
      modeLiveBtn.setAttribute("aria-selected", String(!isSim));
    }
    if (modeSimBtn) {
      modeSimBtn.classList.toggle("active", isSim);
      modeSimBtn.setAttribute("aria-selected", String(isSim));
    }
    if (simBanner) {
      simBanner.classList.toggle("visible", isSim);
    }
    if (verifyBtnText) {
      verifyBtnText.textContent = isSim
        ? "Preview Simulated Scenario (0 Credits)"
        : "Verify Policy & Stage Form (Live SDK)";
    }
    if (isSim) {
      const activeBtn = document.querySelector(".scenario-btn.active");
      const key = activeBtn ? activeBtn.getAttribute("data-scenario") : "pol100245";
      renderVerificationResult(SIMULATED_SCENARIOS[key] || SIMULATED_SCENARIOS.pol100245);
    } else {
      resetWorkspaceDisplay(
        "<strong>Live TinyFish Mode Active:</strong> Previous simulated preview cleared. Click <strong>Verify Policy &amp; Stage Form (Live SDK)</strong> to run real browser automation against <code>https://medverify-tpa-portal.vercel.app/</code>."
      );
    }
  }

  if (modeLiveBtn) {
    modeLiveBtn.addEventListener("click", function () {
      setExecutionMode("live");
    });
  }
  if (modeSimBtn) {
    modeSimBtn.addEventListener("click", function () {
      setExecutionMode("simulated");
    });
  }
  if (navSimBtn) {
    navSimBtn.addEventListener("click", function () {
      setExecutionMode("simulated");
    });
  }

  scenarioBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      scenarioBtns.forEach(function (b) {
        b.classList.remove("active");
      });
      btn.classList.add("active");
      const key = btn.getAttribute("data-scenario");
      if (SIMULATED_SCENARIOS[key]) {
        renderVerificationResult(SIMULATED_SCENARIOS[key]);
      }
    });
  });

  // Confirmed Portal Preset Selector — clears stale results on change
  if (presetSelect) {
    presetSelect.addEventListener("change", function () {
      const val = presetSelect.value;
      if (val === "pol100245") {
        policyIdInput.value = "POL-100245";
        diagnosisInput.value = "Acute Cholecystitis / ICD-10 K81.0";
        costInput.value = "85000";
        if (roomCategorySelect) roomCategorySelect.value = "Semi-Private";
      } else if (val === "pol205118") {
        policyIdInput.value = "POL-205118";
        diagnosisInput.value = "Senile Nuclear Cataract / ICD-10 H25.1";
        costInput.value = "62000";
        if (roomCategorySelect) roomCategorySelect.value = "Semi-Private";
      } else if (val === "pol309872") {
        policyIdInput.value = "POL-309872";
        diagnosisInput.value = "Acute Appendicitis / ICD-10 K35.80";
        costInput.value = "95000";
        if (roomCategorySelect) roomCategorySelect.value = "Semi-Private";
      } else if (val === "pol999001") {
        policyIdInput.value = "POL-999001";
        diagnosisInput.value = "Inpatient Medical Evaluation / ICD-10 Z03.89";
        costInput.value = "45000";
        if (roomCategorySelect) roomCategorySelect.value = "Semi-Private";
      } else if (val === "pol999999") {
        policyIdInput.value = "POL-999999";
        diagnosisInput.value = "Observational Evaluation / ICD-10 Z03.89";
        costInput.value = "25000";
        if (roomCategorySelect) roomCategorySelect.value = "Semi-Private";
      }

      if (currentMode === "simulated") {
        const key = val === "pol999999" || val === "custom" ? "unknown" : val;
        if (SIMULATED_SCENARIOS[key]) {
          renderVerificationResult(SIMULATED_SCENARIOS[key]);
        }
      } else {
        resetWorkspaceDisplay(
          "<strong>Case Preset Updated (<code>" +
            policyIdInput.value +
            "</code>):</strong> Stale results cleared. Click <strong>Verify Policy &amp; Stage Form (Live SDK)</strong> to launch TinyFish."
        );
      }
    });
  }

  // Also clear stale results if user edits Policy ID manually in Live Mode
  if (policyIdInput) {
    policyIdInput.addEventListener("input", function () {
      if (currentMode === "live") {
        resetWorkspaceDisplay(
          "<strong>Policy ID Modified (<code>" +
            (policyIdInput.value || "—") +
            "</code>):</strong> Previous results cleared. Click <strong>Verify Policy &amp; Stage Form (Live SDK)</strong> to run verification."
        );
      }
    });
  }

  // Live Verification Form Submit -> POST /api/verify
  async function executeBackendVerification(payload) {
    if (verifySubmitBtn) verifySubmitBtn.disabled = true;
    const startMs = Date.now();

    // Immediately clear stale results before launching the agent!
    resetWorkspaceDisplay(
      "<strong>Dispatching TinyFish Browser Agent (0.0s):</strong> Navigating <code>" +
        (payload.portal_url || DEFAULT_PORTAL_URL) +
        "</code> for policy <code>" +
        (payload.policy_id || "—") +
        "</code> (Policy Search &rarr; Details &rarr; Pre-Auth Form &rarr; Document Upload &rarr; Review &amp; Verify)...",
      "tone-warn"
    );

    const banner = document.getElementById("ws-status-banner");
    const evPrepTime = document.getElementById("ev-prep-time");
    let isPausedForHuman = false;
    if (liveTimerInterval) clearInterval(liveTimerInterval);
    liveTimerInterval = setInterval(async function () {
      const elapsed = ((Date.now() - startMs) / 1000).toFixed(1);
      try {
        const stRes = await fetch("/api/status");
        if (stRes && stRes.ok) {
          const stJson = await stRes.json();
          if (
            stJson &&
            (stJson.state === "WAITING_FOR_HUMAN_CHECK" || stJson.status === "Waiting for human check")
          ) {
            isPausedForHuman = true;
            renderWaitingForHumanCheck();
            if (verifyBtnText) {
              verifyBtnText.textContent = "Waiting for human check (" + elapsed + "s)...";
            }
            if (evPrepTime) {
              evPrepTime.innerHTML = elapsed + "s <small>(Waiting for human check)</small>";
            }
            return;
          }
          isPausedForHuman = false;
        }
      } catch (_) {
        // Ignore transient status poll errors
      }

      if (!isPausedForHuman) {
        if (verifyBtnText) {
          verifyBtnText.textContent = "Running TinyFish Cloud Agent (" + elapsed + "s)...";
        }
        if (evPrepTime) {
          evPrepTime.innerHTML = elapsed + "s <small>(in progress...)</small>";
        }
        if (banner) {
          banner.innerHTML =
            "<strong>TinyFish Cloud Browser Active (" +
            elapsed +
            "s):</strong> Navigating <code>" +
            (payload.portal_url || DEFAULT_PORTAL_URL) +
            "</code> for policy <code>" +
            (payload.policy_id || "—") +
            "</code> (Policy Search &rarr; Details &rarr; Pre-Auth Form &rarr; Document Upload &rarr; Review &amp; Verify)...";
        }
      }
    }, 500);

    try {
      const response = await fetch("/api/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (liveTimerInterval) clearInterval(liveTimerInterval);
      renderVerificationResult(result);
    } catch (err) {
      if (liveTimerInterval) clearInterval(liveTimerInterval);
      renderVerificationResult({
        success: false,
        run_status: "NETWORK_ERROR",
        policy_id: payload.policy_id,
        portal_url: payload.portal_url,
        manual_fallback_url: payload.portal_url || DEFAULT_PORTAL_URL,
        policy_found: false,
        policy_status: null,
        room_rent_limit: null,
        copay_percentage: null,
        fields_prepared: [],
        stopped_at_review: false,
        submitted: false,
        field_accuracy: {
          verified: false,
          total_checks: 0,
          passed_count: 0,
          mismatch_count: 0,
          not_verified_count: 0,
          checks: [],
          discrepancies: ["Could not reach local Python backend (/api/verify): " + err.message]
        },
        error: "Could not reach local Python backend (/api/verify): " + err.message
      });
    } finally {
      if (liveTimerInterval) clearInterval(liveTimerInterval);
      if (verifySubmitBtn) verifySubmitBtn.disabled = false;
      if (verifyBtnText) {
        verifyBtnText.textContent =
          currentMode === "simulated"
            ? "Preview Simulated Scenario (0 Credits)"
            : "Verify Policy & Stage Form (Live SDK)";
      }
    }
  }

  if (verifyForm) {
    verifyForm.addEventListener("submit", function (e) {
      e.preventDefault();
      if (currentMode === "simulated") {
        const pid = (policyIdInput ? policyIdInput.value : "").trim().toUpperCase();
        const pidMap = {
          "POL-100245": "pol100245",
          "POL-205118": "pol205118",
          "POL-309872": "pol309872",
          "POL-999001": "pol999001"
        };
        const key = pidMap[pid] || "unknown";
        scenarioBtns.forEach(function (b) {
          b.classList.toggle("active", b.getAttribute("data-scenario") === key);
        });
        renderVerificationResult(SIMULATED_SCENARIOS[key]);
        return;
      }

      const autoSubmitCheckbox = document.getElementById("auto-submit-checkbox");
      const useBrowserDirect = playwrightFallbackCheckbox ? Boolean(playwrightFallbackCheckbox.checked) : true;
      const doFinalSubmit = autoSubmitCheckbox ? Boolean(autoSubmitCheckbox.checked) : false;

      executeBackendVerification({
        policy_id: policyIdInput ? policyIdInput.value : "",
        diagnosis: diagnosisInput ? diagnosisInput.value : "",
        estimated_cost: costInput ? Number(costInput.value) : 0,
        room_category: roomCategorySelect ? roomCategorySelect.value : "Semi-Private",
        use_sample_document: sampleDocSelect ? sampleDocSelect.value === "true" : true,
        portal_url: portalUrlInput ? portalUrlInput.value : DEFAULT_PORTAL_URL,
        enable_playwright_fallback: useBrowserDirect,
        use_tinyfish_browser_session: useBrowserDirect,
        auto_submit_preauth: doFinalSubmit
      });
    });
  }

  // Human-in-the-Loop Resume & Cancel Controls
  const btnHitlResumeEl = document.getElementById("btn-hitl-resume");
  const btnHitlCancelEl = document.getElementById("btn-hitl-cancel");

  async function executeHitlResume(sessionIdOverride) {
    const sid = sessionIdOverride || activeHitlSessionId || "";
    if (!sid) {
      // If no persistent session ID was opened, launch/resume interactive browser verification
      return executeBackendVerification({
        policy_id: policyIdInput ? policyIdInput.value : "POL-100245",
        diagnosis: diagnosisInput ? diagnosisInput.value : "Acute Cholecystitis / ICD-10 K81.0",
        estimated_cost: costInput ? Number(costInput.value) : 85000,
        room_category: roomCategorySelect ? roomCategorySelect.value : "Semi-Private",
        use_sample_document: sampleDocSelect ? sampleDocSelect.value === "true" : true,
        portal_url: portalUrlInput ? portalUrlInput.value : DEFAULT_PORTAL_URL,
        use_tinyfish_browser_session: true
      });
    }
    try {
      const res = await fetch("/api/verify/resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sid })
      });
      const data = await res.json();
      renderVerificationResult(data);
      return data;
    } catch (err) {
      const fallbackData = {
        success: false,
        run_status: "SESSION_EXPIRED_OR_UNAVAILABLE",
        session_id: sid,
        policy_id: activeHitlPolicyId || "",
        portal_url: activeHitlPortalUrl || DEFAULT_PORTAL_URL,
        manual_fallback_url: activeHitlPortalUrl || DEFAULT_PORTAL_URL,
        policy_found: false,
        stopped_at_review: false,
        submitted: false,
        error: "Could not resume session (/api/verify/resume): " + err.message
      };
      renderVerificationResult(fallbackData);
      return fallbackData;
    }
  }

  async function executeHitlCancel(sessionIdOverride) {
    const sid = sessionIdOverride || activeHitlSessionId || "";
    try {
      const res = await fetch("/api/verify/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sid,
          policy_id: activeHitlPolicyId || (policyIdInput ? policyIdInput.value : ""),
          portal_url: activeHitlPortalUrl || (portalUrlInput ? portalUrlInput.value : DEFAULT_PORTAL_URL)
        })
      });
      const data = await res.json();
      renderVerificationResult(data);
      return data;
    } catch (err) {
      const cancelData = {
        success: false,
        run_status: "USER_CANCELLED",
        session_id: sid,
        policy_id: activeHitlPolicyId || "",
        portal_url: activeHitlPortalUrl || DEFAULT_PORTAL_URL,
        manual_fallback_url: activeHitlPortalUrl || DEFAULT_PORTAL_URL,
        policy_found: false,
        stopped_at_review: false,
        submitted: false,
        error: "Session cancelled by coordinator."
      };
      renderVerificationResult(cancelData);
      return cancelData;
    }
  }

  if (btnHitlResumeEl) {
    btnHitlResumeEl.addEventListener("click", function () {
      executeHitlResume();
    });
  }
  if (btnHitlCancelEl) {
    btnHitlCancelEl.addEventListener("click", function () {
      executeHitlCancel();
    });
  }

  // 0-Credit Instant Preview Button for the currently selected Policy ID
  if (guardrailTestBtn) {
    guardrailTestBtn.addEventListener("click", function () {
      const pid = (policyIdInput ? policyIdInput.value : "").trim().toUpperCase();
      const pidMap = {
        "POL-100245": "pol100245",
        "POL-205118": "pol205118",
        "POL-309872": "pol309872",
        "POL-999001": "pol999001"
      };
      const key = pidMap[pid] || "unknown";
      setExecutionMode("simulated");
      scenarioBtns.forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-scenario") === key);
      });
      renderVerificationResult(SIMULATED_SCENARIOS[key]);
    });
  }

  // Expose workspace state controllers for automated transition testing
  if (typeof window !== "undefined") {
    window.MedVerifyWorkspace = {
      resetWorkspaceDisplay: resetWorkspaceDisplay,
      renderWaitingForHumanCheck: renderWaitingForHumanCheck,
      renderVerificationResult: renderVerificationResult,
      setExecutionMode: setExecutionMode,
      executeHitlResume: executeHitlResume,
      executeHitlCancel: executeHitlCancel,
      SIMULATED_SCENARIOS: SIMULATED_SCENARIOS
    };
  }
})();
