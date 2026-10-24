"""
app.py
------
MedVerify Streamlit Dashboard for Insurance Policy Verification & Pre-Authorization Prep.
Uses tinyfish_client.verify_policy() powered by the TinyFish Python SDK.
"""

import os
import streamlit as st
from tinyfish_client import verify_policy


st.set_page_config(
    page_title="MedVerify | Insurance Policy Verification",
    page_icon="🏥",
    layout="wide",
)

# Sidebar: Environment Status & Safety Notice
with st.sidebar:
    st.header("🏥 MedVerify")
    st.caption("Autonomous Web-Agent Copilot for Cashless Pre-Authorization")

    api_key_present = bool(os.getenv("TINYFISH_API_KEY"))
    if api_key_present:
        st.success("TINYFISH_API_KEY detected in environment")
    else:
        st.error("TINYFISH_API_KEY is not set")
        st.code('$env:TINYFISH_API_KEY="your-key"', language="powershell")

    st.divider()
    st.subheader("Safety Guardrails")
    st.markdown(
        "- **Synthetic Data Only:** Uses test/sandbox policy IDs.\n"
        "- **Human-in-the-Loop:** Stops at the portal review screen.\n"
        "- **No Auto-Submit:** Never submits a pre-authorization form automatically.\n"
        "- **Honest Failure Handling:** Never invents policy results if a run fails."
    )

# Main Header
st.title("🏥 MedVerify: Insurance Policy Verification")
st.write(
    "Enter a synthetic policy ID, diagnosis, estimated treatment cost, and target portal URL. "
    "TinyFish will look up the policy, extract coverage limits, prepare supported pre-authorization "
    "fields, and stop at the review screen for your verification."
)

# Intake Form
with st.form("verify_policy_form"):
    col1, col2 = st.columns(2)

    with col1:
        portal_url = st.text_input(
            "Target Portal URL",
            placeholder="https://your-sandbox-portal.example.com",
            help="Supply the sandbox or test insurance portal URL (never hardcoded).",
        )
        policy_id = st.text_input(
            "Synthetic Policy ID",
            value="POL-1001",
            placeholder="e.g., POL-1001",
        )

    with col2:
        diagnosis = st.text_input(
            "Diagnosis / ICD-10 Code",
            value="Acute Appendicitis (K35.80)",
            placeholder="e.g., Acute Appendicitis (K35.80)",
        )
        estimated_cost = st.number_input(
            "Estimated Treatment Cost (INR)",
            min_value=0,
            value=55000,
            step=1000,
        )

    submitted_btn = st.form_submit_button(
        "🔍 Verify Policy & Prepare Pre-Auth",
        use_container_width=True,
    )

if submitted_btn:
    with st.spinner("Running TinyFish web agent (this typically takes 30–90 seconds)..."):
        result = verify_policy(
            policy_id=policy_id,
            diagnosis=diagnosis,
            estimated_cost=estimated_cost,
            portal_url=portal_url,
        )

    st.divider()
    st.subheader("Verification & Pre-Authorization Results")

    # Handle failure or policy not found without inventing successful data
    if not result.get("success"):
        st.error(f"Verification did not succeed: {result.get('error')}")
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Run Status", result.get("run_status", "FAILED"))
        col_b.metric("Policy Found", "No")
        col_c.metric("Auto-Submitted", "No (Blocked)")

        if result.get("notes"):
            st.info(f"**Agent Notes:** {result['notes']}")

        with st.expander("View Raw Response Details"):
            st.json(result)
    else:
        st.success(
            f"Policy **{result.get('policy_id')}** verified on portal. "
            "Pre-authorization fields prepared and halted at review screen."
        )

        # Coverage Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Policy Status", result.get("policy_status") or "Unknown")
        m2.metric("Room-Rent Limit", result.get("room_rent_limit") or "Not Specified")
        m3.metric("Co-Payment", result.get("copay_percentage") or "Not Specified")
        m4.metric(
            "Stopped at Review",
            "Yes" if result.get("stopped_at_review") else "Check Portal",
        )

        # Prepared Form Fields & Notes
        left_col, right_col = st.columns(2)
        with left_col:
            st.markdown("#### Prepared Pre-Authorization Fields")
            fields = result.get("fields_prepared") or []
            if fields:
                for field in fields:
                    st.markdown(f"- ✅ `{field}`")
            else:
                st.write("No form fields were reported as populated.")

        with right_col:
            st.markdown("#### Human Review Gate")
            st.warning(
                "**Form Not Submitted:** In compliance with MedVerify safety rules, "
                "the agent stopped at the review screen (`submitted = False`). "
                "A hospital coordinator must review and confirm final submission."
            )
            if result.get("notes"):
                st.markdown(f"**Agent Summary:** {result['notes']}")

        with st.expander("View Structured JSON Output"):
            st.json(result)
