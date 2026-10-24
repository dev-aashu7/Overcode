/* ============================================================================
   MedVerify — Cashless Pre-Authorization Desk Client
   Configured for https://medverify-tpa-portal.vercel.app/
   ============================================================================ */

(function () {
  "use strict";

  const DEFAULT_PORTAL_URL = "https://medverify-tpa-portal.vercel.app/";

  // --------------------------------------------------------------------------
  // 1. BACKEND HEALTH TELEMETRY
  // --------------------------------------------------------------------------
  const navApiDot = document.getElementById("nav-api-dot");
  const navTelemetryBtn = document.getElementById("nav-telemetry-btn");

  let backendHealth = {
    api_key_configured: false,
    environment: "SANDBOX",
    default_portal_url: DEFAULT_PORTAL_URL
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
        : "NOT SET (set $env:TINYFISH_API_KEY in PowerShell before live cloud runs)";
      alert(
        "MedVerify Backend Telemetry\n\n" +
          "• Default Portal: " + (backendHealth.default_portal_url || DEFAULT_PORTAL_URL) + "\n" +
          "• Environment: SANDBOX (Synthetic Data Only)\n" +
          "• TINYFISH_API_KEY: " + keyStatus + "\n" +
          "• Submission Lock: ENFORCED (submitted = False)\n" +
          "• Backend Function: tinyfish_client.verify_policy()"
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
  const portalUrlInput = document.getElementById("portal-url-input");
  const verifyForm = document.getElementById("verify-form");
  const verifySubmitBtn = document.getElementById("verify-submit-btn");
  const verifyBtnText = document.getElementById("verify-btn-text");
  const guardrailTestBtn = document.getElementById("guardrail-test-btn");

  let currentMode = "live"; // "live" | "simulated"

  // Confirmed Portal Scenarios matching https://medverify-tpa-portal.vercel.app/
  const SIMULATED_SCENARIOS = {
    pol100245: {
      is_simulated_demo: true,
      success: true,
      run_status: "SIMULATED_DEMO",
      policy_id: "POL-100245",
      portal_url: DEFAULT_PORTAL_URL,
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
      form_prepared: true,
      stopped_at_review: true,
      submitted: false,
      notes: "SIMULATED DEMO (0 Credits) — Verified Active policy for Rahul Sharma (POL-100245), filled Pre-Authorization Form, attached sample_clinical_document.pdf, navigated to Review & Verify, and stopped without clicking Submit Pre-Authorization.",
      error: null
    },
    pol205118: {
      is_simulated_demo: true,
      success: true,
      run_status: "SIMULATED_DEMO",
      policy_id: "POL-205118",
      portal_url: DEFAULT_PORTAL_URL,
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
      form_prepared: true,
      stopped_at_review: true,
      submitted: false,
      notes: "SIMULATED DEMO (0 Credits) — Verified Active policy for Sunita Verma (POL-205118), staged pre-authorization form & sample clinical document, and stopped at Review & Verify.",
      error: null
    },
    pol309872: {
      is_simulated_demo: true,
      success: true,
      run_status: "SIMULATED_DEMO",
      policy_id: "POL-309872",
      portal_url: DEFAULT_PORTAL_URL,
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
      form_prepared: true,
      stopped_at_review: true,
      submitted: false,
      notes: "SIMULATED DEMO (0 Credits) — Verified Active Corporate GMC policy for Priya Nair (POL-309872), staged pre-auth form & sample document, and stopped at Review & Verify.",
      error: null
    },
    pol999001: {
      is_simulated_demo: true,
      success: false,
      run_status: "POLICY_LAPSED",
      policy_id: "POL-999001",
      portal_url: DEFAULT_PORTAL_URL,
      policy_found: true,
      patient_name: "Vikram Malhotra",
      insurer_name: "SecureLife Mediclaim Co. — Basic Hospitalization Floater",
      policy_status: "Lapsed",
      room_rent_limit: "₹3,000 / day",
      copay_percentage: "20%",
      co_payment: "20%",
      fields_prepared: [],
      document_uploaded: null,
      form_prepared: false,
      stopped_at_review: false,
      submitted: false,
      notes: "SIMULATED DEMO (0 Credits) — Policy POL-999001 (Vikram Malhotra) is Lapsed (expired 2024-12-31). Pre-authorization cannot be initiated.",
      error: "Policy 'POL-999001' status is Lapsed. Cashless pre-authorization cannot be initiated for a lapsed policy."
    },
    unknown: {
      is_simulated_demo: true,
      success: false,
      run_status: "NOT_FOUND",
      policy_id: "POL-999999",
      portal_url: DEFAULT_PORTAL_URL,
      policy_found: false,
      patient_name: null,
      insurer_name: null,
      policy_status: "Not Found",
      room_rent_limit: null,
      copay_percentage: null,
      co_payment: null,
      fields_prepared: [],
      document_uploaded: null,
      form_prepared: false,
      stopped_at_review: false,
      submitted: false,
      notes: "SIMULATED DEMO (0 Credits) — Policy ID 'POL-999999' was not found in ApexCare TPA records.",
      error: "Policy 'POL-999999' was not found in TPA portal records."
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

  function renderVerificationResult(data) {
    const modeBadge = document.getElementById("result-mode-badge");
    const banner = document.getElementById("ws-status-banner");

    const chipStatus = document.getElementById("chip-status");
    const valStatus = document.getElementById("val-status");
    const subStatus = document.getElementById("sub-status");

    const chipRoom = document.getElementById("chip-room");
    const valRoom = document.getElementById("val-room");

    const chipCopay = document.getElementById("chip-copay");
    const valCopay = document.getElementById("val-copay");

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

    if (!data) return;

    const isSim = Boolean(data.is_simulated_demo);
    const prefixTag = isSim ? "SIMULATED" : "LIVE TINYFISH";
    if (modeBadge) {
      modeBadge.textContent = "02 / 03 · " + prefixTag;
    }

    if (rawJsonPre) {
      rawJsonPre.textContent = JSON.stringify(data, null, 2);
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

    if (gateStopped) gateStopped.textContent = String(stopped);
    if (gateSubmitted) gateSubmitted.textContent = String(submitted) + " (Locked)";

    // Reset timeline classes
    [tlStep1, tlStep2, tlStep3].forEach(function (el) {
      if (el) el.className = "ws-tl-item";
    });
    if (tlFieldsWrap) tlFieldsWrap.innerHTML = "";

    // CASE 1: Policy NOT found or guardrail/SDK error (policy_found === false)
    if (!policyFound) {
      if (banner) {
        banner.className = "ws-status-banner tone-err";
        banner.innerHTML =
          "<strong>" +
          (isSim ? "[Simulated Demo] " : "") +
          "Verification Failed (" +
          (data.run_status || "FAILED") +
          "):</strong> " +
          (data.error || "Policy lookup did not succeed.") +
          " No coverage values were fabricated.";
      }

      if (valStatus) {
        valStatus.textContent = pStatus || "Unverified";
        valStatus.className = "vital-reading" + (pStatus ? "" : " muted");
      }
      if (chipStatus) {
        chipStatus.textContent = data.run_status === "NOT_FOUND" ? "NOT FOUND" : "ERROR";
        chipStatus.className = "vital-chip chip-err";
      }
      if (subStatus) subStatus.textContent = "Run status: " + (data.run_status || "FAILED");

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

      if (tlStep1) tlStep1.classList.add("err");
      if (tlBadge1) tlBadge1.textContent = data.run_status || "FAILED";
      if (tlDesc1) tlDesc1.textContent = data.error || "Policy lookup did not succeed.";

      if (tlBadge2) tlBadge2.textContent = "SKIPPED";
      if (tlDesc2) tlDesc2.textContent = "Pre-authorization form & document staging skipped because policy lookup failed.";

      if (tlBadge3) tlBadge3.textContent = "NOT REACHED";
      if (tlDesc3) tlDesc3.textContent = "Workflow halted before Review & Verify.";
      return;
    }

    // CASE 2: Policy WAS found on the portal (Active, Lapsed, or Incomplete)
    if (valStatus) {
      valStatus.textContent = pStatus || "Unspecified";
      valStatus.className = "vital-reading";
    }
    if (chipStatus) {
      chipStatus.textContent = inactive ? "LAPSED" : active ? (isSim ? "SIMULATED" : "ACTIVE") : "EXTRACTED";
      chipStatus.className = "vital-chip " + (active ? "chip-ok" : inactive ? "chip-err" : "chip-warn");
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
      chipRoom.className = "vital-chip " + (rLimit ? (inactive ? "chip-warn" : "chip-ok") : "chip-warn");
    }

    if (valCopay) {
      valCopay.textContent = copay || "Not reported";
      valCopay.className = "vital-reading" + (copay ? "" : " muted");
    }
    if (chipCopay) {
      chipCopay.textContent = copay ? (isSim ? "SIMULATED" : "EXTRACTED") : "MISSING";
      chipCopay.className = "vital-chip " + (copay ? (inactive ? "chip-warn" : "chip-ok") : "chip-warn");
    }

    // Timeline Step 1: Policy Search & Coverage Extraction
    if (tlStep1) tlStep1.classList.add(inactive ? "warn" : "done");
    if (tlBadge1) tlBadge1.textContent = inactive ? "FOUND (LAPSED)" : "COMPLETED";
    if (tlDesc1) {
      tlDesc1.textContent = inactive
        ? "Located policy record for " + (patientName || data.policy_id) + ", but status is '" + pStatus + "'."
        : "Located policy record for " + (patientName || data.policy_id) + " and extracted coverage sub-limits.";
    }

    // Timeline Step 2: Pre-Auth Form & Document Upload
    if (inactive) {
      if (tlStep2) tlStep2.classList.add("err");
      if (tlBadge2) tlBadge2.textContent = "BLOCKED (LAPSED)";
      if (tlDesc2) tlDesc2.textContent = "Pre-authorization cannot be initiated because the policy has lapsed.";
    } else if (fields.length > 0) {
      if (tlStep2) tlStep2.classList.add("done");
      if (tlBadge2) tlBadge2.textContent = fields.length + " ITEMS STAGED";
      if (tlDesc2) tlDesc2.textContent = "Filled Pre-Authorization Form and attached synthetic clinical document:";
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
      if (tlDesc2) tlDesc2.textContent = "Policy verified, but pre-authorization form fields were not reported.";
    }

    // Timeline Step 3: Review & Verify Screen Halt
    if (inactive) {
      if (tlBadge3) tlBadge3.textContent = "NOT REACHED";
      if (tlDesc3) tlDesc3.textContent = "Halted on Policy Details screen due to Lapsed policy status.";
    } else if (stopped && !submitted) {
      if (tlStep3) tlStep3.classList.add("done");
      if (tlBadge3) tlBadge3.textContent = "STOPPED AT REVIEW & VERIFY";
      if (tlDesc3) tlDesc3.textContent = "Agent reached Review & Verify and stopped without clicking Submit Pre-Authorization.";
    } else {
      if (tlStep3) tlStep3.classList.add("warn");
      if (tlBadge3) tlBadge3.textContent = "INCOMPLETE HALT";
      if (tlDesc3) tlDesc3.textContent = "Agent did not confirm stopping at Review & Verify. Manual check required.";
    }

    // Banner state: Only data.success === true renders as a green verified & staged state!
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
    } else if (data.success && active && stopped && !submitted) {
      if (banner) {
        banner.className = "ws-status-banner tone-ok";
        banner.innerHTML =
          "<strong>" +
          (isSim ? "[Simulated Demo] " : "") +
          "Policy Verified &amp; Staged at Review &amp; Verify:</strong> " +
          (data.notes || "All coverage terms extracted, sample document attached, and halted before submission.");
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

  // Confirmed Portal Preset Selector
  if (presetSelect) {
    presetSelect.addEventListener("change", function () {
      const val = presetSelect.value;
      if (val === "pol100245") {
        policyIdInput.value = "POL-100245";
        diagnosisInput.value = "Acute Cholecystitis / ICD-10 K81.0";
        costInput.value = "85000";
      } else if (val === "pol205118") {
        policyIdInput.value = "POL-205118";
        diagnosisInput.value = "Senile Nuclear Cataract / ICD-10 H25.1";
        costInput.value = "62000";
      } else if (val === "pol309872") {
        policyIdInput.value = "POL-309872";
        diagnosisInput.value = "Acute Appendicitis / ICD-10 K35.80";
        costInput.value = "95000";
      } else if (val === "pol999001") {
        policyIdInput.value = "POL-999001";
        diagnosisInput.value = "Inpatient Medical Evaluation / ICD-10 Z03.89";
        costInput.value = "45000";
      } else if (val === "pol999999") {
        policyIdInput.value = "POL-999999";
        diagnosisInput.value = "Observational Evaluation / ICD-10 Z03.89";
        costInput.value = "25000";
      }
    });
  }

  // Live Verification Form Submit -> POST /api/verify
  async function executeBackendVerification(payload) {
    const banner = document.getElementById("ws-status-banner");
    if (verifySubmitBtn) verifySubmitBtn.disabled = true;
    if (verifyBtnText) verifyBtnText.textContent = "Running TinyFish Cloud Agent...";
    if (banner) {
      banner.className = "ws-status-banner tone-warn";
      banner.innerHTML =
        "<strong>Dispatching TinyFish Browser Agent:</strong> Navigating <code>" +
        (payload.portal_url || DEFAULT_PORTAL_URL) +
        "</code> for policy <code>" +
        (payload.policy_id || "—") +
        "</code> (Policy Search &rarr; Details &rarr; Pre-Auth Form &rarr; Document Upload &rarr; Review &amp; Verify)...";
    }

    try {
      const response = await fetch("/api/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      renderVerificationResult(result);
    } catch (err) {
      renderVerificationResult({
        success: false,
        run_status: "NETWORK_ERROR",
        policy_id: payload.policy_id,
        portal_url: payload.portal_url,
        policy_found: false,
        policy_status: null,
        room_rent_limit: null,
        copay_percentage: null,
        fields_prepared: [],
        stopped_at_review: false,
        submitted: false,
        error: "Could not reach local Python backend (/api/verify): " + err.message
      });
    } finally {
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

      executeBackendVerification({
        policy_id: policyIdInput ? policyIdInput.value : "",
        diagnosis: diagnosisInput ? diagnosisInput.value : "",
        estimated_cost: costInput ? Number(costInput.value) : 0,
        portal_url: portalUrlInput ? portalUrlInput.value : DEFAULT_PORTAL_URL
      });
    });
  }

  // 0-Credit Backend Guardrail Test Button (tests localhost block without using credits)
  if (guardrailTestBtn) {
    guardrailTestBtn.addEventListener("click", function () {
      setExecutionMode("live");
      executeBackendVerification({
        policy_id: policyIdInput ? policyIdInput.value : "POL-100245",
        diagnosis: diagnosisInput ? diagnosisInput.value : "Acute Cholecystitis / ICD-10 K81.0",
        estimated_cost: costInput ? Number(costInput.value) : 85000,
        portal_url: "http://localhost:8000"
      });
    });
  }
})();
