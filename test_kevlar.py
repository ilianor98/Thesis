import requests
import json
import sys

API_URL = "http://localhost:8080/api/predict"
MODEL = "el"

payload = {
    "model": MODEL,
    "title": "Υπήκοος τρίτης χώρας",
    "text": "κάθε πρόσωπο που δεν είναι πολίτης της ΕΕ και δεν απολαύει του κοινοτικού δικαιώματος ελεύθερης κυκλοφορίας."
}

print(">>> test_kevlar.py started")
print(">>> Posting to:", API_URL)
print(">>> Payload keys:", list(payload.keys()))
sys.stdout.flush()

try:
    r = requests.post(API_URL, json=payload, timeout=40)
    print(">>> HTTP status:", r.status_code)
    print(">>> Raw response text (first 1000 chars):")
    print(r.text[:1000])
    sys.stdout.flush()

    # Pretty JSON (if it is JSON)
    data = r.json()
    print("\n>>> Pretty JSON:")
    print(json.dumps(data, ensure_ascii=False, indent=2))

except requests.exceptions.ConnectionError as e:
    print("!!! ConnectionError: cannot reach the server.")
    print("    Is docker running and port 8080 mapped?")
    print("    Error:", e)

except requests.exceptions.Timeout as e:
    print("!!! Timeout: server did not respond in time.")
    print("    Error:", e)

except ValueError as e:
    print("!!! Response was not JSON.")
    print("    Error:", e)

except Exception as e:
    print("!!! Unexpected error:", repr(e))
