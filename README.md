# 🏥 MedVerify

**Autonomous Web-Agent Copilot for Hospital Cashless Insurance Policy Verification & Pre-Authorization**

MedVerify is a beginner-friendly Streamlit application built with the **TinyFish Python SDK**. It helps hospital insurance desk coordinators look up synthetic patient policies on an insurance/TPA portal, extract policy status, room-rent limits, and co-payment percentages, pre-fill supported pre-authorization form fields, and **stop at the review screen** for human sign-off.

---

## ✨ Key Features & Safety Guardrails

- **TinyFish Python SDK Integration:** Uses `TinyFish().agent.run(url=..., goal=..., output_schema=...)` and checks `RunStatus.COMPLETED` following the TinyFish Workshop Guide.
- **No Hardcoded Insurer URLs:** Uses the `portal_url` supplied by the user.
- **Structured Coverage Extraction:** Extracts `policy_status`, `room_rent_limit`, and `copay_percentage` via a strict JSON `output_schema`.
- **Pre-Authorization Preparation:** Populates supported pre-authorization fields (`policy_id`, `diagnosis`, `estimated_cost`) and halts at the review screen.
- **Human-in-the-Loop (Never Auto-Submits):** The agent is explicitly instructed never to click the final submit button (`submitted: False`).
- **Honest Failure Handling:** If the API key is missing, the portal is unreachable, or the policy ID is not found, `verify_policy()` returns a structured error without inventing policy data.

---

## 📁 Project Structure

```text
Medverify/
├── app.py                # Streamlit dashboard UI
├── tinyfish_client.py    # verify_policy() function using TinyFish Python SDK
├── test_tinyfish.py      # CLI script to test verify_policy() before running Streamlit
├── requirements.txt      # Python dependencies (streamlit, tinyfish)
├── .gitignore            # Prevents committing .venv or API keys
└── README.md             # Setup & usage documentation
```

---

## 🚀 Quickstart

### 1. Create & Activate a Virtual Environment

**Windows (PowerShell):**
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -U -r requirements.txt
```

**Mac / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U -r requirements.txt
```

### 2. Set Your `TINYFISH_API_KEY`

Keep your API key in the `TINYFISH_API_KEY` environment variable (never hardcode it in source files):

**Windows (PowerShell):**
```powershell
$env:TINYFISH_API_KEY="paste-your-key"
```

**Mac / Linux:**
```bash
export TINYFISH_API_KEY="paste-your-key"
```

### 3. Test `verify_policy()` from the Terminal

Before launching the dashboard, you can test `verify_policy()` directly:

```powershell
python test_tinyfish.py https://your-sandbox-portal-url POL-1001
```

### 4. Launch the Streamlit Dashboard

```powershell
streamlit run app.py
```
