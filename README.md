# 🏥 MedVerify

**Autonomous Web-Agent Copilot for Hospital Cashless Insurance Policy Verification & Pre-Authorization**

MedVerify is a healthcare administration platform built for **HackIIITD 2026 / ESYA '26** using the **TinyFish Python SDK**. It assists hospital insurance desk coordinators by looking up synthetic patient policies on an insurance/TPA portal, extracting policy status, room-rent limits, and co-payment percentages, preparing supported pre-authorization form fields, attaching the synthetic clinical document, and **stopping at the Review & Verify screen** for mandatory human sign-off.

---

## 🌐 Confirmed Mock TPA Portal & Sample Policies

- **Deployed Portal URL:** [https://medverify-tpa-portal.vercel.app/](https://medverify-tpa-portal.vercel.app/)
- **Confirmed Sample Policy IDs:**
  - `POL-100245` — **Rahul Sharma** — `Active` (`₹5,000 / day` room cap · `0% (Nil)` co-pay)
  - `POL-205118` — **Sunita Verma** — `Active` (`Single Private AC Room (up to 1% of Sum Insured)` · `10%` co-pay)
  - `POL-309872` — **Priya Nair** — `Active` (`No Capping / Actuals` · `0% (Waived under Corporate GMC)` co-pay)
  - `POL-999001` — **Vikram Malhotra** — `Lapsed` (`₹3,000 / day` · `20%` co-pay — Pre-Authorization blocked)
  - Any other policy ID (e.g., `POL-999999`) is treated as **Not Found**.

---

## ✨ Architecture & Interfaces

MedVerify provides two connected interfaces backed by the same `tinyfish_client.py` verification engine:

1. **Cashless Pre-Authorization Desk (`server.py` + `frontend/` — Port `8080`):**
   - Clean, focused **Verify. Prepare. Review.** workspace (`01/03` Case Intake Parameters, `02/03` Coverage Readout & Automation Progress, `03/03` Mandatory Human Review Stage).
   - Connects to the Python backend via `GET /api/health` and `POST /api/verify` (which invokes `tinyfish_client.verify_policy()`).
   - Includes both **Live TinyFish Backend Mode** and a clearly labeled **Simulated Demo Mode (0 Credits)** so judges and coordinators can preview all confirmed portal outcomes without fabricating live results.
2. **Operational Streamlit Workstation (`app.py` — Port `8501`):**
   - Internal Streamlit operational dashboard calling `tinyfish_client.verify_policy()` directly.

---

## 📁 Project Structure

```text
Medverify/
├── frontend/
│   ├── index.html        # Cashless Pre-Authorization Desk UI
│   ├── styles.css        # Swiss editorial typography & responsive workspace styles
│   └── app.js            # Frontend client for /api/health, /api/verify & simulated demos
├── .streamlit/
│   └── config.toml       # Streamlit light clinical theme configuration
├── server.py             # Python HTTP + JSON API server (/api/health, /api/verify)
├── app.py                # Internal Streamlit operational workstation
├── tinyfish_client.py    # verify_policy() function using TinyFish Python SDK
├── test_tinyfish.py      # CLI script for 0-credit guardrail & mocked portal checks
├── requirements.txt      # Python dependencies (streamlit, tinyfish)
├── .gitignore            # Excludes .venv, __pycache__, and .env secrets
└── README.md             # Project documentation
```

---

## 🚀 Quickstart

### 1. Install Dependencies

**Windows (PowerShell):**
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -U -r requirements.txt
```

### 2. Run Local Guardrail & Mocked Policy Checks (0 Credits)

```powershell
python test_tinyfish.py --check
```

### 3. Set Your `TINYFISH_API_KEY` (Backend Only)

Keep your API key in the `TINYFISH_API_KEY` environment variable (never in frontend files):

```powershell
$env:TINYFISH_API_KEY="paste-your-key"
```

### 4. Run the MedVerify Web Application (Recommended — Port `8080`)

```powershell
python server.py 8080
```
Then open **[http://localhost:8080](http://localhost:8080)** in your browser.

### 5. Run the Streamlit Workstation (Port `8501`)

```powershell
python -m streamlit run app.py
```
Then open **[http://localhost:8501](http://localhost:8501)** in your browser.
