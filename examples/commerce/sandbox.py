# Python 3.9+; standard library only. SIMULATION ONLY.
# INVASTOR_API_BASE=https://YOUR_HOST/api python3 invastor-sandbox.py happy_path
import json, os, sys, uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError
base = os.environ.get("INVASTOR_API_BASE", "").rstrip("/")
if not base:
    raise SystemExit("Set INVASTOR_API_BASE to your serving host plus /api")
scenario = sys.argv[1] if len(sys.argv) > 1 else "happy_path"
approve_simulation = "--approve-simulation" in sys.argv[2:]
token = None
class ApiError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
def api(path, body=None, method=None):
    headers = {"Content-Type": "application/json", "User-Agent": "InVastorSandboxExample/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(base + "/commerce/sandbox" + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers, method=method or ("POST" if body is not None else "GET"))
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except HTTPError as error:
        try: data = json.load(error)
        except ValueError: data = {}
        raise ApiError(data.get("code", "HTTP_ERROR"), data.get("error", str(error)))
session = api("/sessions", {"scenario": scenario})
token = session["token"]  # Never print a bearer credential.
print("SIMULATION ONLY. Fixture balance: $100.00. No real order or payment.")
expected = {"out_of_stock":"OUT_OF_STOCK", "price_changed":"PRICE_CHANGED",
    "budget_limit":"BUDGET_EXCEEDED", "revoked_permission":"PERMISSION_REVOKED",
    "insufficient_funds":"INSUFFICIENT_FUNDS", "expired_permission":"PERMISSION_EXPIRED"}
try:
    if scenario == "revoked_permission":
        api("/session", method="DELETE")
        api("/catalog")
    else:
        items = api("/catalog?q=keyboard")["items"]
        quote = api("/quotes", {"listingId": items[0]["id"], "quantity": 1})["quote"]
        key = "example_" + uuid.uuid4().hex
        try:
            result = api("/purchases", {"quoteId": quote["id"], "idempotencyKey": key})
        except ApiError as error:
            if error.code != "OUTCOME_UNKNOWN": raise
            result = api("/purchases/by-key/" + key)
        except Exception:
            try: result = api("/purchases/by-key/" + key)
            except Exception:
                raise RuntimeError("Outcome unknown. Keep key " + key + "; query status, do not create a replacement.")
        print("Prepared:", result["purchase"]["state"])
        if scenario == "duplicate_request":
            replay = api("/purchases", {"quoteId": quote["id"], "idempotencyKey": key})
            assert replay["replayed"] and replay["purchase"]["id"] == result["purchase"]["id"]
            print("Duplicate safely returned the original purchase.")
        if scenario in expected:
            raise RuntimeError("Expected failure was not raised.")
        if approve_simulation or input("Approve this SIMULATED $49 purchase? [y/N] ").lower() == "y":
            path = "/purchases/" + result["purchase"]["id"]
            api(path + "/approve", {"approved": True})
            if scenario == "duplicate_request":
                api(path + "/approve", {"approved": True})
            status, state = api(path), api("/session")
            assert status["purchase"]["state"] == "SIMULATED_PAID"
            assert state["simulatedPaidCount"] == 1 and state["spentUsdCents"] == quote["totalUsdCents"]
            print("PASS:", status["purchase"]["state"], "balance cents:", state["simulatedBalanceUsdCents"])
        else:
            print("Not approved. No simulated payment made.")
except Exception as error:
    if scenario in expected and getattr(error, "code", None) == expected[scenario]:
        print("PASS: expected safe rejection", error.code)
    else:
        print("FAIL:", str(error), file=sys.stderr)
        sys.exit(1)
