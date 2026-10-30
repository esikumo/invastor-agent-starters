"""Private, single-host connect-or-resume. Python 3.11+ on POSIX."""
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from invastor_commerce import InVastorCommerce, _expiry
from invastor_connection_store import PrivateConnectionStore
import threading


class Agent:
    """Simple actions with durable intent IDs; never automatically repeats a write."""
    def __init__(self, client, root):
        self._client, self._root, self._closed = client, root, False
        self._grant = client._connection.get("grantId")
        self._mutex = threading.RLock()

    def __getattr__(self, name):
        value = getattr(self._client, name)
        if not callable(value):
            return value
        def call(*args, **kwargs):
            with self._mutex:
                if self._closed:
                    raise RuntimeError("Connection is closed")
                return value(*args, **kwargs)
        return call

    def _run(self, method, payload, operation_id):
        if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 200:
            raise ValueError("Provide a stable operation_id from your business event")
        fingerprint = hashlib.sha256(json.dumps(dict(method=method, payload=payload), sort_keys=True).encode()).hexdigest()
        key = "inv_" + hashlib.sha256((method + ":" + operation_id).encode()).hexdigest()[:60]
        path = self._root / "operations" / hashlib.sha256(operation_id.encode()).hexdigest()
        with self._mutex:
            if self._closed:
                raise RuntimeError("Connection is closed")
            with PrivateConnectionStore(path) as journal:
                previous = journal.load()
                if previous and previous.get("grantId") != self._grant:
                    raise ValueError("Operation belongs to a previous authorization; reconcile the original action before reusing its ID")
                if previous and previous["fingerprint"] != fingerprint:
                    raise ValueError("Operation ID was already used for different input")
                if previous and previous["phase"] == "COMPLETE":
                    return previous["result"]
                if previous:
                    lookup = ("requests/by-key/" + key if method == "request" else
                              "purchases/by-key/" + key + "/status" if method == "purchase" else None)
                    if lookup:
                        try:
                            result = self._client._call(lookup)
                        except Exception:
                            result = None
                        if result is not None:
                            journal.save(dict(grantId=self._grant, fingerprint=fingerprint, phase="COMPLETE", result=result))
                            return result
                    from invastor_commerce import CommerceError
                    raise CommerceError("Original write may have committed; no write was repeated. Reconcile the original action.", code="OUTCOME_UNKNOWN")
                journal.save(dict(grantId=self._grant, fingerprint=fingerprint, phase="STARTED"))
                if method in ("product", "service"):
                    route = "extended/publish_product" if method == "product" else "marketplace/publish_service"
                    body = {"product" if method == "product" else "listing": payload}
                elif method == "request":
                    route, body = "requests", dict(request=payload, idempotencyKey=key)
                else:
                    route, body = "purchases", dict(payload, idempotencyKey=key)
                result = self._client._call(route, body)
                journal.save(dict(grantId=self._grant, fingerprint=fingerprint, phase="COMPLETE", result=result))
                return result

    def publish_listing(self, listing, *, operation_id):
        fields = dict(listing)
        kind = fields.pop("type", None)
        if kind in ("service", "SERVICE"):
            return self._run("service", fields, operation_id)
        if kind not in ("product", "PHYSICAL_PRODUCT", "DIGITAL_PRODUCT"):
            raise ValueError("Use service, product, PHYSICAL_PRODUCT or DIGITAL_PRODUCT")
        fields["type"] = "PHYSICAL_PRODUCT" if kind == "product" else kind
        return self._run("product", fields, operation_id)

    def post_buying_request(self, request, *, operation_id):
        return self._run("request", request, operation_id)


    def purchase_autonomously(self, draft, *, operation_id, payment_currency=None,
                              payment_wallet=None, wallet=None, timeout=120, interval=5):
        """Pay one original purchase. Wallet authority is separate from marketplace consent.
        prepare signs only; broadcast submits only the stored bytes. Neither is retried
        after an uncertain callback. Signed public transaction bytes stay in a private journal.
        """
        import time
        import math
        from invastor_commerce import CommerceError
        if (not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 <= timeout <= 900 or
                not isinstance(interval, (int, float)) or not math.isfinite(interval) or not 3 <= interval <= 60):
            raise ValueError("Use timeout 0..900 and interval 3..60 seconds")
        if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 200:
            raise ValueError("A stable operation_id is required")
        if payment_currency and not callable(getattr(wallet, "prepare", None)):
            raise ValueError("Provide a separately authorized wallet.prepare adapter")
        canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        fingerprint = hashlib.sha256(canonical(dict(draft=draft, payment_currency=payment_currency,
            payment_wallet=payment_wallet)).encode()).hexdigest()
        path = self._root / "payments" / hashlib.sha256(operation_id.encode()).hexdigest()
        def uncertain(message):
            return CommerceError(message, code="OUTCOME_UNKNOWN", outcome_unknown=True)
        with self._mutex:
            if self._closed:
                raise RuntimeError("Connection is closed")
            with PrivateConnectionStore(path) as journal:
                record = journal.load()
                if record and (record.get("grantId") != self._grant or record.get("fingerprint") != fingerprint):
                    raise ValueError("Original payment belongs to different authority or input; reconcile it")
                if not record:
                    record = dict(grantId=self._grant, fingerprint=fingerprint, phase="CREATING")
                    journal.save(record)
                if not record.get("purchaseId"):
                    result = self.purchase(draft, operation_id=operation_id,
                        payment_currency=payment_currency, payment_wallet=payment_wallet)
                    purchase = result.get("purchase", {})
                    if not isinstance(purchase.get("id"), int) or isinstance(purchase["id"], bool) or purchase["id"] < 1:
                        raise uncertain("No authoritative purchase identity; recover the original operation")
                    record["purchaseId"] = purchase["id"]
                    record["orderId"] = purchase.get("orderId")
                    journal.save(record)
                purchase_id = record["purchaseId"]
                result = self._client.purchase_status(purchase_id)
                def paid(value):
                    record["phase"] = "PAID"
                    journal.save(record)
                    return dict(value, autonomous=True, operationId=operation_id)
                def check(value):
                    purchase = value.get("purchase", {})
                    if purchase.get("id") != purchase_id:
                        raise uncertain("Original purchase identity changed")
                    if purchase.get("state") in ("AWAITING_APPROVAL", "ORDER_READY", "REVIEW_REQUIRED", "REJECTED"):
                        raise CommerceError("Owner approval or review required; no new payment sent",
                                            code="AUTONOMOUS_PURCHASE_BLOCKED")
                    return purchase
                purchase = check(result)
                if purchase.get("state") == "PAID":
                    return paid(result)
                if payment_currency and record["phase"] not in ("BROADCASTING", "SUBMITTED", "PAID"):
                    funded = self._client._call("purchases/" + str(purchase_id) + "/funding", {})
                    payment_purchase = check(funded)
                    if payment_purchase.get("orderId") != record["orderId"]:
                        raise uncertain("Original funding order changed")
                    if payment_purchase.get("state") == "PAID":
                        return paid(funded)
                    funding = funded.get("funding", {})
                    if funding.get("currency") != payment_currency or payment_purchase.get("state") != "PAYMENT_PENDING":
                        raise uncertain("Original payment is not payable in the selected currency")
                    if funding.get("paymentRequired") and not funding.get("paid"):
                        binding = {key: funding.get(key) for key in ("currency", "intent", "transaction", "payment")}
                        if record.get("funding") and canonical(record["funding"]) != canonical(binding):
                            raise uncertain("Original funding instructions changed; no new signature is allowed")
                        if not record.get("signed"):
                            if record["phase"] == "SIGNING":
                                raise uncertain("Signer response was lost; recover the original signed bytes in the wallet journal")
                            record.update(phase="SIGNING", funding=binding)
                            journal.save(record)
                            key = "inv_" + hashlib.sha256(("purchase:" + operation_id).encode()).hexdigest()[:60]
                            try:
                                signed = wallet.prepare(funding=funding, purchase=payment_purchase,
                                    idempotency_key=key, payment_currency=payment_currency, payment_wallet=payment_wallet)
                            except Exception:
                                raise uncertain("Signer response unavailable; reconcile the original wallet journal without signing again") from None
                            if (not isinstance(signed, dict) or
                                not all(isinstance(signed.get(k), str) and signed[k] for k in ("transactionId", "signedTransaction")) or
                                len(signed["signedTransaction"]) > 2000000):
                                raise uncertain("Wallet must return original transactionId and signedTransaction without broadcasting")
                            record.update(phase="SIGNED", signed=signed)
                            journal.save(record)
                        fresh = check(self._client.purchase_status(purchase_id))
                        if fresh.get("state") == "PAID":
                            return paid(self._client.purchase_status(purchase_id))
                        if fresh.get("state") != "PAYMENT_PENDING":
                            raise uncertain("Original purchase is no longer payable")
                        intent = funding.get("intent") or {}
                        if intent.get("chain") != "solana" and not callable(getattr(wallet, "broadcast", None)):
                            raise ValueError("wallet.broadcast is required for this payment network")
                        record["phase"] = "BROADCASTING"
                        journal.save(record)  # Persist before any send; never repeat an uncertain callback.
                        if intent.get("chain") == "solana":
                            self._client._call("purchases/" + str(purchase_id) + "/funding/submit",
                                dict(intentId=intent["id"], signedTransaction=record["signed"]["signedTransaction"]))
                        else:
                            try:
                                sent = wallet.broadcast(record["signed"])
                            except Exception:
                                raise uncertain("Wallet send outcome unknown; read original purchase status without broadcasting again") from None
                            if sent.get("transactionId") != record["signed"]["transactionId"]:
                                raise uncertain("Wallet returned a different transaction identity")
                            if intent:
                                self._client._call("purchases/" + str(purchase_id) + "/funding/submit",
                                    dict(intentId=intent["id"], txHash=record["signed"]["transactionId"]))
                        record["phase"] = "SUBMITTED"
                        journal.save(record)
                deadline = time.monotonic() + timeout
                while True:
                    result = self._client.purchase_status(purchase_id)
                    purchase = check(result)
                    if purchase.get("state") == "PAID":
                        return paid(result)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return dict(result, autonomous=True, settlementPending=True,
                            paymentOutcomeUnknown=record["phase"] == "BROADCASTING", operationId=operation_id)
                    time.sleep(min(interval, remaining))

    def purchase(self, draft, *, operation_id, payment_currency=None, payment_wallet=None):
        payload = dict(draft=draft)
        if payment_currency:
            payload["paymentCurrency"] = payment_currency
        if payment_wallet:
            payload["paymentWallet"] = payment_wallet
        return self._run("purchase", payload, operation_id)


@contextmanager
def connect(api_url, *, client_id, client_name=None, role="both", directory=None,
            on_verification=None, transport=None):
    from urllib.parse import urlsplit
    base = api_url.rstrip("/") + "/"
    parsed = urlsplit(base)
    if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1"):
        raise ValueError("HTTPS API URL required")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Credential-free API URL required")
    if role not in ("buyer", "seller", "both") or not client_id:
        raise ValueError("Provide client_id and a supported role")
    binding = dict(apiUrl=base, clientId=client_id, role=role)
    key = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
    root = Path(directory) if directory else Path.home() / ".local/state/invastor/python" / key
    with PrivateConnectionStore(root) as store:
        saved = store.load()
        if saved and saved.get("binding") != binding:
            raise ValueError("Store belongs to a different endpoint, app or role")
        def save(connection):
            store.save(dict(version=1, binding=binding, connection=connection))
        import time
        connection = saved.get("connection") if saved else None
        if connection and _expiry(connection.get("authorizationExpiresAt")) > time.time() and not connection.get("reconnectRequired"):
            client = InVastorCommerce(base, connection=connection, save_connection=save, transport=transport)
            try:
                client._token()
                client.catalog(limit=1)
            except Exception as error:
                save(dict(connection, reconnectRequired=True))
                if getattr(error, "code", None) != "invalid_grant" and getattr(error, "status", None) != 401:
                    raise
                connection = None
        else:
            connection = None
        if not connection:
            def show(notice):
                print("Approve your InVastor connection: " + notice["verificationUri"], flush=True)
            client = InVastorCommerce.connect(base, client_id=client_id, client_name=client_name or client_id,
                role=role, on_verification=on_verification or show, save_connection=save, transport=transport)
        agent = Agent(client, root)
        try:
            yield agent
        finally:
            with agent._mutex:
                agent._closed = True
