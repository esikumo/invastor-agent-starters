"""InVastor Python SDK. Python 3.11+, standard library only.
Keep this module in a trusted runtime, never an LLM prompt.
One connection belongs to one running client. Use a durable secret-store callback.
Requests, including refresh and financial writes, are never automatically retried.
"""
import base64
import copy
import hashlib
import json
import secrets
import threading
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote as urlquote, urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener


class CommerceError(RuntimeError):
    def __init__(self, message, *, code=None, status=None, outcome_unknown=False, body=None, payment_required=None, payment_response=None):
        super().__init__(message)
        self.code, self.status, self.outcome_unknown = code, status, outcome_unknown
        self.body, self.payment_required, self.payment_response = body, payment_required, payment_response
        self.recovery = body.get("recovery") if isinstance(body, dict) else None
        self.retryable = body.get("retryable", False) if isinstance(body, dict) else False
        self.outcome_unknown = outcome_unknown or (body.get("outcomeUnknown", False) if isinstance(body, dict) else False)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward a credential to another URL.


def _expiry(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.timestamp()
    except (AttributeError, TypeError, ValueError):
        raise CommerceError("Invalid owner authorization expiry") from None


def _id(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("Use a positive integer ID")
    return value


class _Http:
    def __init__(self, api_url, transport=None):
        url = urlsplit(api_url)
        if (url.scheme != "https" and not (url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1"))) or not url.hostname:
            raise ValueError("Use HTTPS; HTTP is allowed only on localhost")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("Use a credential-free API URL")
        self.base = api_url.rstrip("/") + "/"
        self.origin = (url.scheme, url.hostname, url.port)
        self.transport = transport
        self.opener = build_opener(_NoRedirect())

    def call(self, path, body=None, *, method=None, token=None, payment_signature=None):
        if path.startswith("/") or ".." in urlsplit(path).path.split("/") or "://" in path:
            raise ValueError("Invalid API-relative path")
        method = method or ("POST" if body is not None else "GET")
        headers = {"Content-Type": "application/json", "User-Agent": "InVastorPythonSDK/1.0"}
        if token:
            headers["Authorization"] = "Bearer " + token
        if payment_signature:
            headers["PAYMENT-SIGNATURE"] = payment_signature
        if self.transport:
            return self.transport(self.base + path, method, body, headers)
        request = Request(self.base + path, method=method, headers=headers,
                          data=None if body is None else json.dumps(body).encode())
        try:
            with self.opener.open(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            try:
                value = json.loads(error.read(65536))
            except (ValueError, UnicodeError):
                value = {}
            if not isinstance(value, dict):
                value = {}
            raise CommerceError(value.get("error_description") or value.get("error") or "Commerce request rejected",
                                code=value.get("code") or value.get("error"), status=error.code,
                                body=value, payment_required=error.headers.get("PAYMENT-REQUIRED"),
                                payment_response=error.headers.get("PAYMENT-RESPONSE")) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise CommerceError("Response unavailable. Reconcile the original operation; do not resend a write.",
                                outcome_unknown=method != "GET") from None


def _record(value, client_id, api_url):
    if (not isinstance(value.get("access_token"), str) or not value["access_token"]
        or not isinstance(value.get("refresh_token"), str) or not value["refresh_token"]
        or not isinstance(value.get("expires_in"), (int, float)) or isinstance(value["expires_in"], bool)
        or value["expires_in"] <= 0):
        raise CommerceError("Invalid connection response")
    _expiry(value.get("authorization_expires_at"))
    return {"apiUrl": api_url, "clientId": client_id, "accessToken": value["access_token"],
            "refreshToken": value["refresh_token"], "accessExpiresAt": time.time() * 1000 + value["expires_in"] * 1000,
            "authorizationExpiresAt": value["authorization_expires_at"], "scope": value.get("scope", ""),
            "grantId": value.get("grant_id")}


class InVastorCommerce:
    def __init__(self, api_url, *, connection, save_connection, transport=None):
        if not callable(save_connection):
            raise ValueError("A durable secret-store save_connection callback is required")
        self._http = _Http(api_url, transport)
        if not isinstance(connection, dict) or connection.get("apiUrl") != self._http.base:
            raise ValueError("Connection belongs to a different API URL; use a separate store and connect again")
        self._connection = copy.deepcopy(connection)
        self._save = save_connection
        self._lock = threading.RLock()
        self._renewal_failed = False

    @classmethod
    def connect(cls, api_url, *, client_id, client_name, role, on_verification,
                save_connection, transport=None):
        if not callable(save_connection) or not callable(on_verification):
            raise ValueError("Provide on_verification and a durable save_connection callback")
        http = _Http(api_url, transport)
        verifier = secrets.token_urlsafe(32)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        request = http.call("oauth/device_authorization", {
            "client_id": client_id, "client_name": client_name, "role": role,
            "code_challenge": challenge, "code_challenge_method": "S256"})
        uri = request["verification_uri_complete"]
        if not uri.startswith("/") or uri.startswith("//"):
            raise CommerceError("Untrusted verification URL")
        base = urlsplit(http.base)
        verification = base.scheme + "://" + base.netloc + uri
        deadline = time.monotonic() + min(float(request["expires_in"]), 900)
        on_verification({"verificationUri": verification, "userCode": request["user_code"],
                         "expiresAt": time.time() + float(request["expires_in"])})
        interval = max(5, float(request.get("interval", 5)))
        while time.monotonic() < deadline:
            time.sleep(min(interval, max(0, deadline - time.monotonic())))
            if time.monotonic() >= deadline:
                break
            try:
                result = http.call("oauth/agent-token", {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": client_id, "device_code": request["device_code"], "code_verifier": verifier})
            except CommerceError as error:
                if error.code == "authorization_pending":
                    continue
                if error.code == "slow_down":
                    interval += 5
                    continue
                raise
            record = _record(result, client_id, http.base)
            save_connection(copy.deepcopy(record))  # Persist before exposing a usable client.
            return cls(api_url, connection=record, save_connection=save_connection, transport=transport)
        raise CommerceError("Connection link expired; start a new connection", code="expired_token")

    def _token(self):
        with self._lock:
            current = self._connection
            if self._renewal_failed:
                raise CommerceError("Renewal outcome requires reconciliation or a new owner connection")
            if _expiry(current.get("authorizationExpiresAt")) <= time.time():
                raise CommerceError("Owner authorization expired; connect again")
            if current.get("accessExpiresAt", 0) <= time.time() * 1000 + 15000:
                try:
                    value = self._http.call("oauth/agent-token", {
                        "grant_type": "refresh_token", "client_id": current["clientId"],
                        "refresh_token": current["refreshToken"]})
                    updated = _record(value, current["clientId"], self._http.base)
                    if (updated["grantId"] != current.get("grantId")
                        or _expiry(updated["authorizationExpiresAt"]) != _expiry(current["authorizationExpiresAt"])):
                        raise CommerceError("Renewal changed original authorization identity")
                    self._save(copy.deepcopy(updated))
                    self._connection = updated
                except Exception:
                    self._renewal_failed = True
                    self._save(dict(current, reconnectRequired=True))
                    raise
            return self._connection["accessToken"]

    def _call(self, path, body=None, *, payment_signature=None):
        token = self._token()
        for attempt in range(2):
            try:
                return self._http.call("commerce/agent-access/" + path, body, token=token, payment_signature=payment_signature)
            except Exception as error:
                if body is None and attempt == 0 and (isinstance(error, OSError) or getattr(error, "status", None) in (429, 502, 503, 504)):
                    continue
                if getattr(error, "status", None) == 401:
                    self._renewal_failed = True
                    self._save(dict(self._connection, reconnectRequired=True))
                raise

    def catalog(self, query="", limit=20):
        return self._call("catalog?" + urlencode({"q": query, "limit": limit}))

    def quote(self, listing_id, quantity=1, *, package_name=None, shipping_method=None,
              shipping_address=None, shipping_address_id=None, selected_variants=None):
        fields = dict(listingId=_id(listing_id), quantity=_id(quantity))
        for key, value in (("packageName", package_name), ("shippingMethod", shipping_method),
                           ("shippingAddress", shipping_address), ("shippingAddressId", shipping_address_id),
                           ("selectedVariants", selected_variants)):
            if value is not None:
                fields[key] = value
        return self._call("quotes", fields)

    def purchase_status(self, purchase_id):
        return self._call("purchases/" + str(_id(purchase_id)) + "/status")

    def purchase_by_key(self, key):
        if not isinstance(key, str) or not key:
            raise ValueError("Provide the original idempotency key")
        return self._call("purchases/by-key/" + urlquote(key, safe="") + "/status")

    def purchase_evidence(self, purchase_id):
        return self._call("purchases/" + str(_id(purchase_id)) + "/evidence")

    def watch_purchase(self, *, purchase_id=None, idempotency_key=None, timeout=120, interval=5, on_update=None):
        if (purchase_id is None) == (idempotency_key is None):
            raise ValueError("Provide exactly one original purchase_id or idempotency_key")
        if not isinstance(timeout, (int, float)) or not 0 <= timeout <= 900 or not isinstance(interval, (int, float)) or not 3 <= interval <= 60:
            raise ValueError("Use timeout 0..900 seconds and polling interval 3..60 seconds")
        started = time.monotonic()
        while True:
            result = self.purchase_status(purchase_id) if purchase_id is not None else self.purchase_by_key(idempotency_key)
            if on_update:
                on_update(result)
            action = result.get("purchase", {}).get("lifecycle", {}).get("nextAction")
            outcome = ("STATUS_UNAVAILABLE" if not action else "COMPLETE" if action == "COMPLETE" else
                       "ACTION_REQUIRED" if action in ("CONTACT_SUPPORT", "REVIEW_DISPUTE", "REVIEW_ORIGINAL_ORDER", "BUYER_APPROVAL_REQUIRED", "STOP") else None)
            if outcome:
                return dict(result, monitoring={"outcome": outcome})
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                return dict(result, monitoring={"outcome": "TIMED_OUT"})
            time.sleep(min(interval, remaining))

    def x402(self, purchase_id, *, payment_signature=None):
        return self._call("purchases/" + str(_id(purchase_id)) + "/x402", {},
                          payment_signature=payment_signature)

    def service_jobs(self):
        return self._call("marketplace/service_jobs", {})

    def service_job(self, order_id):
        return self._call("marketplace/service_job", {"orderId": _id(order_id)})

    def service_action(self, operation, order_id, **fields):
        if operation not in ("seller_service_agreement", "seller_agree_service_terms", "start_service", "deliver_service"):
            raise ValueError("Unsupported seller service operation")
        return self._call("marketplace/" + operation, {**fields, "orderId": _id(order_id)})


class SandboxCommerce:
    """Separate fixture client. No live grants, real orders, approval, or payments."""
    def __init__(self, api_url, *, scenario="happy_path", transport=None):
        self._http = _Http(api_url, transport)
        value = self._call("sessions", {"scenario": scenario})
        self._token_value = value["token"]

    def _call(self, path, body=None):
        value = self._http.call("commerce/sandbox/" + path, body, token=getattr(self, "_token_value", None))
        if value.get("sandbox") is not True:
            raise CommerceError("Refusing a response not explicitly marked as sandbox")
        return value

    def catalog(self, query="keyboard"):
        return self._call("catalog?" + urlencode({"q": query}))

    def quote(self, listing_id, quantity=1):
        return self._call("quotes", {"listingId": listing_id, "quantity": _id(quantity)})

    def purchase_status(self, purchase_id):
        return self._call("purchases/" + urlquote(str(purchase_id), safe="") if str(purchase_id).startswith("sp_")
                          else "purchases/by-key/" + urlquote(str(purchase_id), safe=""))
