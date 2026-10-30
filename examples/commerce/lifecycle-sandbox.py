"""Python 3.11+, standard library. No production wallet or order endpoints."""
import json, os, sys, uuid, time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
if "--approve-simulation" not in sys.argv:
    raise SystemExit("Pass --approve-simulation for fixture-only actions")

from urllib.parse import urlsplit
from email.utils import parsedate_to_datetime
configured_base = os.environ.get("INVASTOR_API_BASE", "")
parts = urlsplit(configured_base)
if parts.scheme not in ("http", "https") or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
    raise SystemExit("Set INVASTOR_API_BASE to an HTTP(S) API URL without credentials, query or fragment")
base = configured_base.rstrip("/") + "/commerce/sandbox/"
class ApiError(RuntimeError):
    def __init__(self, value):
        super().__init__(value.get("error")); self.body = value; self.code = value.get("code")
def api(path, token=None, body=None, method=None):
    method = method or ("GET" if body is None else "POST")
    for attempt in range(3):
        request = Request(base + path, data=None if body is None else json.dumps(body).encode(),
            method=method, headers={"Content-Type":"application/json", "Accept":"application/json",
                "User-Agent":"InVastor-Lifecycle-Sandbox/1.0", **({"Authorization":"Bearer " + token} if token else {})})
        try:
            response = urlopen(request, timeout=30)
        except HTTPError as error:
            response = error
        except OSError:
            raise ApiError({"code":"SANDBOX_CONNECTION_FAILED", "outcomeUnknown":method != "GET",
                "error":"Sandbox connection failed or timed out. No automatic write retry; reconcile the original purchase key before repeating a purchase."}) from None
        with response:
            status, headers = response.code, response.headers
            try: value = json.loads(response.read())
            except (ValueError, UnicodeError): value = None
        rejected = status == 429 and isinstance(value, dict) and value.get("sandbox") is True and value.get("code") == "RATE_LIMITED"
        if attempt < 2 and (method == "GET" or rejected) and status in (429, 502, 503, 504):
            header = headers.get("Retry-After")
            try:
                seconds = (61 if status == 429 else 2) if header is None else (
                    int(header) if header.isdigit() else parsedate_to_datetime(header).timestamp() - time.time())
            except (ValueError, TypeError, OverflowError): seconds = -1
            if 0 <= seconds <= 120:
                print("Sandbox temporarily unavailable (HTTP %s); waiting %s seconds before a safe retry." % (status, max(1, seconds)), file=sys.stderr)
                time.sleep(max(1, seconds)); continue
        if not isinstance(value, dict):
            raise ApiError({"code":"SANDBOX_INVALID_RESPONSE", "status":status, "outcomeUnknown":method != "GET",
                "error":"Sandbox returned a non-JSON response (HTTP %s). Check the API URL or gateway. No automatic write retry; preserve the original purchase key." % status})
        if not 200 <= status < 300: raise ApiError(value)
        return value

expected = {"out_of_stock":"OUT_OF_STOCK","price_changed":"PRICE_CHANGED","budget_limit":"BUDGET_EXCEEDED",
    "revoked_permission":"PERMISSION_REVOKED","insufficient_funds":"INSUFFICIENT_FUNDS","expired_permission":"PERMISSION_EXPIRED"}
for index, scenario in enumerate(api("scenarios")["scenarios"]):
    if index == 10:
        print("Respecting sandbox session-creation rate limit (61 seconds)", file=sys.stderr)
        time.sleep(61)
    token = api("sessions", body={"scenario":scenario})["token"]
    key = "lifecycle_" + uuid.uuid4().hex
    try:
        item = api("catalog", token)["items"][0]
        quote = api("quotes", token, {"listingId":item["id"]})["quote"]
        if scenario == "revoked_permission": api("session", token, method="DELETE")
        try: prepared = api("purchases", token, {"quoteId":quote["id"],"idempotencyKey":key})
        except ApiError as error:
            if error.code != "OUTCOME_UNKNOWN": raise
            prepared = api("purchases/by-key/" + key, token)
        assert scenario not in expected
        path = "purchases/" + prepared["purchase"]["id"]
        def action(name): return api(path + "/actions", token, {"action":name,"confirmed":True})
        if scenario == "duplicate_request":
            assert api("purchases", token, {"quoteId":quote["id"],"idempotencyKey":key})["purchase"]["id"] == prepared["purchase"]["id"]
        api(path + "/approve", token, {"approved":True}); api(path + "/approve", token, {"approved":True})
        assert api("session", token)["spentUsdCents"] == quote["totalUsdCents"]
        if scenario == "refund":
            assert action("request_refund")["purchase"]["lifecycle"]["refund"]["state"] == "REQUESTED"
            action("complete_refund"); action("complete_refund")
            state = api("session", token)
            assert state["simulatedBalanceUsdCents"] == 10000 and state["spentUsdCents"] == quote["totalUsdCents"]
        else:
            try: action("payout"); raise AssertionError("Payout before acceptance succeeded")
            except ApiError as error: assert error.code == "PAYOUT_BLOCKED"
            action("submit_work"); action("accept_delivery")
            if scenario == "payout_failure":
                try: action("payout"); raise AssertionError("Payout failure was not simulated")
                except ApiError as error:
                    assert error.code == "PAYOUT_FAILED" and not error.body["recovery"]["mayCreateReplacementPayment"]
                assert api(path, token)["purchase"]["lifecycle"]["nextAction"] == "CONTACT_SUPPORT"
            else:
                action("payout"); action("payout")
                assert api(path, token)["purchase"]["lifecycle"]["nextAction"] == "COMPLETE"
        assert api("session", token)["purchaseCount"] == 1
        print("PASS", scenario)
    except ApiError as error:
        if expected.get(scenario) != error.code: raise
        print("PASS", scenario, error.code)
