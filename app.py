import os
import streamlit as st

try:
    from tinyfish_client import DEFAULT_PORTAL_URL, verify_policy
    TINYFISH_IMPORT_ERROR = None
except Exception as e:
    DEFAULT_PORTAL_URL = "https://medverify-tpa-portal.vercel.app/"
    verify_policy = None
    TINYFISH_IMPORT_ERROR = str(e)

st.set_page_config(
    page_title="MedVerify | Clinical TPA Pre-Auth Workstation",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# CLINICAL EHR / TPA WORKSTATION CSS
# -----------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    background-color: #F4F7F9;
    color: #0F172A;
}

.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
    max-width: 1380px !important;
}

[data-testid="stSidebar"] {
    background-color: #0B192C !important;
    border-right: 1px solid #1E293B;
}
[data-testid="stSidebar"] * {
    color: #E2E8F0 !important;
}
[data-testid="stSidebar"] hr {
    border-color: #1E293B !important;
}
[data-testid="stSidebar"] pre,
[data-testid="stSidebar"] code,
[data-testid="stSidebar"] [data-testid="stCodeBlock"] pre {
    background-color: #13253D !important;
    border: 1px solid #1E3A5F !important;
    color: #E2E8F0 !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background-color: #13253D !important;
    border-color: #1E3A5F !important;
    color: #E2E8F0 !important;
}

.clinical-header {
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-left: 6px solid #0D9488;
    border-radius: 8px;
    padding: 16px 22px;
    margin-bottom: 18px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}
.clinical-title {
    font-size: 1.45rem;
    font-weight: 700;
    color: #0F172A;
    margin: 0;
    letter-spacing: -0.02em;
}
.clinical-subtitle {
    font-size: 0.85rem;
    color: #475569;
    margin-top: 4px;
}
.badge-row {
    display: flex;
    gap: 10px;
    align-items: center;
}
.sandbox-pill {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    font-weight: 600;
    background-color: #CCFBF1;
    color: #115E59;
    border: 1px solid #5EEAD4;
    padding: 5px 10px;
    border-radius: 4px;
    letter-spacing: 0.05em;
}
.status-pill {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    font-weight: 600;
    background-color: #F1F5F9;
    color: #334155;
    border: 1px solid #CBD5E1;
    padding: 5px 12px;
    border-radius: 4px;
}

.stepper-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 20px;
}
.step-node {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-top: 3px solid #CBD5E1;
    border-radius: 6px;
    padding: 10px 14px;
}
.step-node.active {
    border-top: 3px solid #0D9488;
    background: #F0FDFA;
}
.step-node.done {
    border-top: 3px solid #10B981;
}
.step-node.error {
    border-top: 3px solid #EF4444;
    background: #FEF2F2;
}
.step-num {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    color: #64748B;
    font-weight: 600;
}
.step-label {
    font-size: 0.85rem;
    font-weight: 600;
    color: #0F172A;
    margin-top: 2px;
}

.pane-header {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #0F766E;
    margin-bottom: 10px;
    display: flex;
    justify-content: space-between;
    border-bottom: 1px solid #E2E8F0;
    padding-bottom: 6px;
}

.vital-card {
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-left: 4px solid #94A3B8;
    border-radius: 6px;
    padding: 14px 16px;
    margin-bottom: 12px;
}
.vital-card.ok {
    border-left-color: #10B981;
}
.vital-card.warn {
    border-left-color: #F59E0B;
}
.vital-card.err {
    border-left-color: #EF4444;
}
.vital-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.vital-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: #64748B;
    font-weight: 600;
}
.vital-tag {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    padding: 2px 7px;
    border-radius: 4px;
    background: #F1F5F9;
    color: #475569;
}
.vital-value {
    font-size: 1.25rem;
    font-weight: 700;
    color: #0F172A;
    margin: 6px 0 2px 0;
}
.vital-sub {
    font-size: 0.76rem;
    color: #64748B;
}

.review-gate-box {
    background: #FFFBEB;
    border: 1px solid #FDE68A;
    border-left: 5px solid #D97706;
    border-radius: 6px;
    padding: 14px 16px;
    margin-top: 14px;
}
.review-gate-title {
    font-size: 0.9rem;
    font-weight: 700;
    color: #92400E;
    margin-bottom: 4px;
}
.review-gate-desc {
    font-size: 0.82rem;
    color: #78350F;
}

div.stButton > button[kind="primary"] {
    background-color: #0F766E !important;
    color: #FFFFFF !important;
    border: none !important;
    font-weight: 600 !important;
    padding: 0.6rem 1.2rem !important;
    border-radius: 6px !important;
    width: 100%;
}
div.stButton > button[kind="primary"]:hover {
    background-color: #115E59 !important;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# SESSION STATE INITIALIZATION
# -----------------------------------------------------------------------------
if "verification_result" not in st.session_state:
    st.session_state.verification_result = None
if "run_state" not in st.session_state:
    st.session_state.run_state = "IDLE"  # IDLE, RUNNING, COMPLETE, ERROR

# -----------------------------------------------------------------------------
# SIDEBAR: TELEMETRY, SAFETY LOCKS & UI PREVIEW MODE
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🏥 MedVerify")
    st.caption("HOSPITAL TPA DESK • ESYA '26")
    st.markdown("---")

    api_key_present = bool(os.environ.get("TINYFISH_API_KEY"))
    key_badge = "✅ CONFIGURED" if api_key_present else "⚠️ NOT SET"

    st.markdown("**SYSTEM TELEMETRY**")
    st.code(
        f"ENV: SANDBOX\n"
        f"PORTAL: medverify-tpa-portal.vercel.app\n"
        f"TINYFISH_API_KEY: {key_badge}\n"
        f"AUTO-SUBMIT LOCK: ENFORCED\n"
        f"DATA POLICY: SYNTHETIC ONLY",
        language="yaml",
    )

    if not api_key_present:
        st.caption("Set your API key in PowerShell before running live verification:")
        st.code('$env:TINYFISH_API_KEY="your_key"', language="powershell")

    st.markdown("---")
    st.markdown("**CONFIRMED PORTAL PREVIEW (0 CREDITS)**")
    st.caption(
        "Preview confirmed policy outcomes from medverify-tpa-portal.vercel.app without using TinyFish credits."
    )
    ui_preview_mode = st.selectbox(
        "Display Mode",
        options=[
            "Live Mode (Actual TinyFish Output)",
            "UI Preview: POL-100245 (Rahul Sharma — Active)",
            "UI Preview: POL-205118 (Sunita Verma — Active)",
            "UI Preview: POL-309872 (Priya Nair — Active)",
            "UI Preview: POL-999001 (Vikram Malhotra — Lapsed)",
            "UI Preview: POL-999999 (Unknown Policy ID)",
        ],
        index=0,
    )

# -----------------------------------------------------------------------------
# DETERMINE DISPLAY DATA (NEVER FAKE REAL RESULTS!)
# -----------------------------------------------------------------------------
is_preview = ui_preview_mode != "Live Mode (Actual TinyFish Output)"

if ui_preview_mode == "UI Preview: POL-100245 (Rahul Sharma — Active)":
    display_state = "COMPLETE"
    display_data = {
        "is_ui_preview": True,
        "success": True,
        "run_status": "SIMULATED_PREVIEW",
        "policy_id": "POL-100245",
        "policy_found": True,
        "patient_name": "Rahul Sharma",
        "policy_status": "Active",
        "room_rent_limit": "₹5,000 / day (Single Standard AC Room)",
        "copay_percentage": "0% (Nil)",
        "co_payment": "0% (Nil)",
        "fields_prepared": ["diagnosis", "estimated_cost", "sample_clinical_document.pdf"],
        "document_uploaded": "sample_clinical_document.pdf",
        "form_prepared": True,
        "stopped_at_review": True,
        "submitted": False,
        "notes": "UI Preview — Active policy staged through Document Upload and halted at Review & Verify.",
    }
elif ui_preview_mode == "UI Preview: POL-205118 (Sunita Verma — Active)":
    display_state = "COMPLETE"
    display_data = {
        "is_ui_preview": True,
        "success": True,
        "run_status": "SIMULATED_PREVIEW",
        "policy_id": "POL-205118",
        "policy_found": True,
        "patient_name": "Sunita Verma",
        "policy_status": "Active",
        "room_rent_limit": "Single Private AC Room (up to 1% of Sum Insured)",
        "copay_percentage": "10% Co-Pay applicable on total admitted claim amount",
        "co_payment": "10% Co-Pay applicable on total admitted claim amount",
        "fields_prepared": ["diagnosis", "estimated_cost", "sample_clinical_document.pdf"],
        "document_uploaded": "sample_clinical_document.pdf",
        "form_prepared": True,
        "stopped_at_review": True,
        "submitted": False,
        "notes": "UI Preview — Senior Citizen policy staged and halted at Review & Verify.",
    }
elif ui_preview_mode == "UI Preview: POL-309872 (Priya Nair — Active)":
    display_state = "COMPLETE"
    display_data = {
        "is_ui_preview": True,
        "success": True,
        "run_status": "SIMULATED_PREVIEW",
        "policy_id": "POL-309872",
        "policy_found": True,
        "patient_name": "Priya Nair",
        "policy_status": "Active",
        "room_rent_limit": "No Capping / Actuals (Any category up to Deluxe)",
        "copay_percentage": "0% (Waived under Corporate GMC)",
        "co_payment": "0% (Waived under Corporate GMC)",
        "fields_prepared": ["diagnosis", "estimated_cost", "sample_clinical_document.pdf"],
        "document_uploaded": "sample_clinical_document.pdf",
        "form_prepared": True,
        "stopped_at_review": True,
        "submitted": False,
        "notes": "UI Preview — Corporate GMC policy staged and halted at Review & Verify.",
    }
elif ui_preview_mode == "UI Preview: POL-999001 (Vikram Malhotra — Lapsed)":
    display_state = "ERROR"
    display_data = {
        "is_ui_preview": True,
        "success": False,
        "run_status": "POLICY_LAPSED",
        "policy_id": "POL-999001",
        "policy_found": True,
        "patient_name": "Vikram Malhotra",
        "policy_status": "Lapsed",
        "room_rent_limit": "₹3,000 / day",
        "copay_percentage": "20%",
        "co_payment": "20%",
        "fields_prepared": [],
        "form_prepared": False,
        "stopped_at_review": False,
        "submitted": False,
        "error": "Policy 'POL-999001' status is Lapsed. Cashless pre-authorization cannot be initiated.",
    }
elif ui_preview_mode == "UI Preview: POL-999999 (Unknown Policy ID)":
    display_state = "ERROR"
    display_data = {
        "is_ui_preview": True,
        "success": False,
        "run_status": "NOT_FOUND",
        "policy_id": "POL-999999",
        "policy_found": False,
        "policy_status": "Not Found",
        "error": "Policy 'POL-999999' was not found in TPA portal records.",
    }
else:
    display_state = st.session_state.run_state
    display_data = st.session_state.verification_result

# -----------------------------------------------------------------------------
# TOP CLINICAL RIBBON & 4-NODE WORKFLOW STEPPER
# -----------------------------------------------------------------------------
status_label_map = {
    "IDLE": "● AWAITING INTAKE",
    "RUNNING": "◌ AGENT DISPATCHED",
    "COMPLETE": "● STOPPED AT REVIEW & VERIFY",
    "ERROR": "▲ VERIFICATION HALTED",
}
ribbon_status = status_label_map.get(display_state, "● AWAITING INTAKE")
if is_preview:
    ribbon_status = f"👁️ {ui_preview_mode.upper()}"

st.markdown(
    f'<div class="clinical-header">'
    f'<div>'
    f'<h1 class="clinical-title">Cashless Pre-Authorization Desk</h1>'
    f'<div class="clinical-subtitle">Automated TPA Policy Lookup, Document Upload & Review-Screen Staging</div>'
    f'</div>'
    f'<div class="badge-row">'
    f'<span class="sandbox-pill">SANDBOX • APEXCARE TPA</span>'
    f'<span class="status-pill">{ribbon_status}</span>'
    f'</div>'
    f'</div>',
    unsafe_allow_html=True,
)

form_is_prepared = bool(
    display_data
    and (display_data.get("form_prepared") or display_data.get("fields_prepared"))
)
s1 = "done" if display_state in ("COMPLETE", "ERROR") else "active"
s2 = "done" if (display_data and display_data.get("policy_found")) else ("error" if display_state == "ERROR" else "")
s3 = "done" if (display_state == "COMPLETE" and form_is_prepared) else ("error" if display_state == "ERROR" else "")
s4 = "active" if (display_state == "COMPLETE" and display_data and display_data.get("stopped_at_review")) else ""

st.markdown(
    f'<div class="stepper-grid">'
    f'<div class="step-node {s1}"><div class="step-num">STAGE 01</div><div class="step-label">Case Intake & Parameters</div></div>'
    f'<div class="step-node {s2}"><div class="step-num">STAGE 02</div><div class="step-label">Policy Search & Details</div></div>'
    f'<div class="step-node {s3}"><div class="step-num">STAGE 03</div><div class="step-label">Pre-Auth Form & Doc Upload</div></div>'
    f'<div class="step-node {s4}"><div class="step-num">STAGE 04</div><div class="step-label">Review & Verify Halt</div></div>'
    f'</div>',
    unsafe_allow_html=True,
)

if is_preview:
    st.warning(
        "**UI PREVIEW MODE ACTIVE (0 CREDITS):** Displaying confirmed policy scenarios from `medverify-tpa-portal.vercel.app`. "
        "Switch the sidebar back to **Live Mode** when ready to run TinyFish."
    )

# -----------------------------------------------------------------------------
# SPLIT WORKSTATION: LEFT (INTAKE) | RIGHT (COVERAGE VITALS & HUMAN REVIEW)
# -----------------------------------------------------------------------------
left_col, right_col = st.columns([5, 7], gap="large")

with left_col:
    st.markdown(
        '<div class="pane-header"><span>01 // PATIENT & POLICY INTAKE CHART</span><span>APEXCARE TPA</span></div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        preset = st.selectbox(
            "Confirmed Portal Policy Preset",
            options=[
                "POL-100245 — Rahul Sharma (Active · ₹5,000/day · 0% Co-Pay)",
                "POL-205118 — Sunita Verma (Active · Senior 1% SI · 10% Co-Pay)",
                "POL-309872 — Priya Nair (Active · Corporate GMC · No Cap)",
                "POL-999001 — Vikram Malhotra (Lapsed Policy Test)",
                "POL-999999 — Unknown / Not Found Policy Test",
                "Custom Input",
            ],
            index=0,
        )

        default_pol = "POL-100245"
        default_diag = "Acute Cholecystitis / ICD-10 K81.0"
        default_cost = 85000

        if "POL-205118" in preset:
            default_pol = "POL-205118"
            default_diag = "Senile Nuclear Cataract / ICD-10 H25.1"
            default_cost = 62000
        elif "POL-309872" in preset:
            default_pol = "POL-309872"
            default_diag = "Acute Appendicitis / ICD-10 K35.80"
            default_cost = 95000
        elif "POL-999001" in preset:
            default_pol = "POL-999001"
            default_diag = "Inpatient Medical Evaluation / ICD-10 Z03.89"
            default_cost = 45000
        elif "POL-999999" in preset:
            default_pol = "POL-999999"
            default_diag = "Observational Evaluation / ICD-10 Z03.89"
            default_cost = 25000

        policy_id = st.text_input(
            "Synthetic Policy ID",
            value=default_pol,
            help="Confirmed Policy ID on https://medverify-tpa-portal.vercel.app/",
        )
        diagnosis = st.text_input(
            "Provisional Diagnosis / ICD-10 Code",
            value=default_diag,
            help="Clinical diagnosis to populate on the Pre-Authorization Form",
        )
        estimated_cost = st.number_input(
            "Estimated Cost (INR)",
            min_value=1000,
            value=default_cost,
            step=1000,
            help="Estimated hospitalization cost in INR",
        )
        portal_url = st.text_input(
            "Target Mock TPA Portal URL",
            value=os.environ.get("MOCK_PORTAL_URL", DEFAULT_PORTAL_URL),
            help="Configurable portal URL (defaults to https://medverify-tpa-portal.vercel.app/)",
        )

        st.caption(
            "🔒 **Safety Guarantee:** The TinyFish agent stops at **Review & Verify** and never clicks **Submit Pre-Authorization**."
        )

        verify_clicked = st.button("⚡ Dispatch TinyFish Agent & Stage Form", type="primary")

        if verify_clicked:
            if verify_policy is None:
                st.session_state.run_state = "ERROR"
                st.session_state.verification_result = {
                    "error": f"Could not import verify_policy from tinyfish_client.py: {TINYFISH_IMPORT_ERROR}"
                }
                st.rerun()
            else:
                with st.spinner("TinyFish cloud browser navigating ApexCare TPA portal & staging pre-auth form..."):
                    raw_res = verify_policy(
                        policy_id=policy_id.strip(),
                        diagnosis=diagnosis.strip(),
                        estimated_cost=estimated_cost,
                        portal_url=portal_url.strip(),
                    )
                    if not isinstance(raw_res, dict):
                        st.session_state.run_state = "ERROR"
                        st.session_state.verification_result = {
                            "error": f"Unexpected return type from verify_policy: {type(raw_res).__name__}"
                        }
                    elif raw_res.get("success") is True:
                        st.session_state.run_state = "COMPLETE"
                        st.session_state.verification_result = raw_res
                    else:
                        st.session_state.run_state = "ERROR"
                        st.session_state.verification_result = raw_res
                st.rerun()

with right_col:
    st.markdown(
        '<div class="pane-header"><span>02 // EXTRACTED COVERAGE VITALS</span><span>TINYFISH TELEMETRY</span></div>',
        unsafe_allow_html=True,
    )

    if display_state == "ERROR" and display_data:
        st.error(f"**Verification Halted ({display_data.get('run_status', 'FAILED')}):** {display_data.get('error', 'Unknown error returned by agent.')}")

    pol_status = "—"
    room_limit = "—"
    copay_val = "—"
    card_tone = ""
    badge_text = "IDLE"

    if isinstance(display_data, dict) and display_data.get("policy_found"):
        pol_status = str(display_data.get("policy_status") or "—")
        room_limit = str(display_data.get("room_rent_limit") or "—")
        copay_val = str(display_data.get("copay_percentage") or display_data.get("co_payment") or "—")
        badge_text = "UI PREVIEW" if display_data.get("is_ui_preview") else "EXTRACTED"
        if display_data.get("success") is True and "ACTIVE" in pol_status.upper():
            card_tone = "ok"
        elif "LAPSED" in pol_status.upper() or "EXPIRED" in pol_status.upper():
            card_tone = "err"
        else:
            card_tone = "warn"
    elif display_state == "ERROR" and isinstance(display_data, dict):
        pol_status = str(display_data.get("policy_status") or "Unverified")
        card_tone = "err"
        badge_text = "HALTED"

    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(
            f'<div class="vital-card {card_tone}">'
            f'<div class="vital-top"><span class="vital-label">POLICY STATUS</span><span class="vital-tag">{badge_text}</span></div>'
            f'<div class="vital-value">{pol_status}</div>'
            f'<div class="vital-sub">Portal verification state</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f'<div class="vital-card {card_tone}">'
            f'<div class="vital-top"><span class="vital-label">ROOM-RENT CAP</span><span class="vital-tag">{badge_text}</span></div>'
            f'<div class="vital-value">{room_limit}</div>'
            f'<div class="vital-sub">Daily inpatient room limit</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f'<div class="vital-card {card_tone}">'
            f'<div class="vital-top"><span class="vital-label">CO-PAYMENT</span><span class="vital-tag">{badge_text}</span></div>'
            f'<div class="vital-value">{copay_val}</div>'
            f'<div class="vital-sub">Policyholder share %</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="pane-header" style="margin-top: 18px;">'
        '<span>03 // FORM STAGING & HUMAN REVIEW GATE</span><span>HUMAN-IN-THE-LOOP</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        if display_state == "IDLE":
            st.info(
                "**Ready for Intake:** Target portal defaults to `https://medverify-tpa-portal.vercel.app/`. "
                "Select a confirmed policy preset on the left or preview outcomes from the sidebar."
            )
        elif display_state == "ERROR":
            st.warning(
                "**Human Review Gate Not Reached:** Because the policy was Lapsed, Not Found, or incomplete, "
                "pre-authorization staging was halted prior to Review & Verify."
            )
            if isinstance(display_data, dict):
                with st.expander("Inspect Raw Dictionary Returned by tinyfish_client.py"):
                    st.json(display_data)
        elif display_state == "COMPLETE" and isinstance(display_data, dict):
            form_staged = bool(display_data.get("form_prepared"))
            stopped_safe = bool(display_data.get("stopped_at_review"))

            c_a, c_b = st.columns(2)
            with c_a:
                st.markdown("**Staged Pre-Auth Summary**")
                st.markdown(f"- **Patient Name:** `{display_data.get('patient_name') or '—'}`")
                st.markdown(f"- **Policy ID:** `{display_data.get('policy_id') or policy_id}`")
                st.markdown(f"- **Document Attached:** `{display_data.get('document_uploaded') or 'sample_clinical_document.pdf'}`")
            with c_b:
                st.markdown("**Agent Safety Checkpoints**")
                st.markdown(f"- **Pre-Auth Form Filled:** `{'Yes' if form_staged else 'No'}`")
                st.markdown(f"- **Stopped at Review & Verify:** `{'Yes (Locked)' if stopped_safe else 'Unverified'}`")
                st.markdown("- **Submit Pre-Authorization Clicked:** `False (Blocked)`")

            st.markdown(
                '<div class="review-gate-box">'
                '<div class="review-gate-title">🛑 HUMAN REVIEW GATE ACTIVE — STOPPED AT REVIEW & VERIFY</div>'
                '<div class="review-gate-desc">'
                'TinyFish has halted on the Review & Verify screen without clicking Submit Pre-Authorization. '
                'A hospital coordinator must review the staged fields before final submission.'
                '</div>'
                '</div>',
                unsafe_allow_html=True,
            )

            with st.expander("Inspect Raw Dictionary Returned by tinyfish_client.py"):
                st.json(display_data)
