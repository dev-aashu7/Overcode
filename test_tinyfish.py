"""
test_tinyfish.py
----------------
Simple script to test TinyFish connectivity and the verify_policy() helper
before launching the Streamlit dashboard.

Usage (PowerShell):
    $env:TINYFISH_API_KEY="paste-your-key"
    python test_tinyfish.py https://your-sandbox-portal-url POL-1001
"""

import json
import os
import sys
from tinyfish_client import verify_policy


def main() -> None:
    if not os.getenv("TINYFISH_API_KEY"):
        sys.exit(
            "Error: TINYFISH_API_KEY is not set.\n"
            "In PowerShell, run:\n"
            '  $env:TINYFISH_API_KEY="paste-your-key"'
        )

    portal_url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.getenv("MEDVERIFY_PORTAL_URL", "")
    )
    policy_id = sys.argv[2] if len(sys.argv) > 2 else "POL-1001"
    diagnosis = "Acute Appendicitis (K35.80)"
    estimated_cost = 55000

    if not portal_url:
        print(
            "Usage:\n"
            "  python test_tinyfish.py <portal_url> [policy_id]\n\n"
            "Testing input validation with an empty portal_url (uses 0 credits):"
        )

    print(f"Running verify_policy for policy_id='{policy_id}'...")
    result = verify_policy(
        policy_id=policy_id,
        diagnosis=diagnosis,
        estimated_cost=estimated_cost,
        portal_url=portal_url,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
