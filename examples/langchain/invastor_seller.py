"""Developer-owned text-statistics service. No LLM, scraping, or wallet signing.
Default is READ-ONLY: inspect a real owned job and compute a local report.
--deliver requires paid native service terms already accepted by both parties.
This is an execution example, NOT permission to submit unrelated work to a job.
"""
import argparse
import hashlib
import json
from pathlib import Path
from invastor_commerce import InVastorCommerce
from invastor_connection_store import PrivateConnectionStore


def analyze(text):
    return {"service": "text-statistics", "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "characters": len(text), "words": len(text.split()), "lines": len(text.splitlines())}


def fulfill(client, order_id, text, journal, *, deliver=False):
    job = client.service_job(order_id)
    report = analyze(text)
    if not deliver:
        return {"mode": "READ_ONLY", "job": job, "computedReport": report,
                "next": "Only deliver if the accepted job brief requires this exact text-statistics service."}
    order = job.get("order") or {}
    if order.get("status") in ("DELIVERED", "COMPLETED"):
        return {"mode": "ALREADY_DELIVERED", "orderId": order_id}
    if not order.get("paidAt") or order.get("status") not in ("PAID", "IN_PROGRESS") or job.get("blocked"):
        raise RuntimeError("This job is not funded and eligible; no work was submitted")
    if any(r.get("kind") == "REVISION" and r.get("status") not in ("RESOLVED", "WITHDRAWN") for r in job.get("requests", [])):
        raise RuntimeError("An unresolved revision needs the revision workflow, not another initial delivery")
    agreement = client.service_action("seller_service_agreement", order_id).get("agreement") or {}
    if not agreement.get("buyerAcceptedAt") or not agreement.get("sellerAcceptedAt"):
        raise RuntimeError("Both parties must accept the native service agreement first")
    previous = journal.load()
    identity = {"orderId": order_id, "inputSha256": report["sha256"], "agreementVersion": agreement["version"]}
    if previous and any(previous.get(k) != v for k, v in identity.items()):
        raise RuntimeError("Journal belongs to another job, input, or agreement; reconcile the original work")
    if previous:
        raise RuntimeError("A delivery was already attempted. Inspect the original job; never resend blindly")
    # Durable write precedes ALL mutations. A crash/response loss requires inspection.
    journal.save({**identity, "phase": "SUBMITTING"})
    if order["status"] == "PAID":
        client.service_action("start_service", order_id)
    result = client.service_action("deliver_service", order_id, deliveryNote=json.dumps(report, sort_keys=True))
    journal.save({**identity, "phase": "DELIVERED"})
    return {"mode": "DELIVERED", "orderId": order_id, "result": result,
            "notice": "Delivery is not buyer acceptance or seller payment. Native review and dispute holds remain."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--store", required=True, help="Private persistent directory; plaintext, 0700; never commit it")
    parser.add_argument("--order-id", type=int, help="Omit to list your authorized service jobs")
    parser.add_argument("--input", help="UTF-8 file supplied for the accepted text-statistics job")
    parser.add_argument("--deliver", action="store_true", help="Submit actual work to this already-paid job")
    args = parser.parse_args()
    if args.deliver and (not args.order_id or not args.input):
        parser.error("--deliver requires --order-id and --input")
    with PrivateConnectionStore(args.store) as store:
        record = store.load()
        if record:
            client = InVastorCommerce(args.api_url, connection=record, save_connection=store.save)
        else:
            client = InVastorCommerce.connect(
                args.api_url, client_id="invastor-text-statistics-example", client_name="Text statistics seller",
                role="seller", save_connection=store.save,
                on_verification=lambda notice: print("Approve your seller connection: " + notice["verificationUri"], flush=True))
        if not args.order_id:
            print(json.dumps(client.service_jobs(), indent=2))
            return
        if not args.input:
            print(json.dumps(client.service_job(args.order_id), indent=2))
            return
        text = Path(args.input).read_text(encoding="utf-8")
        # Separate journal store; do not overwrite the connection credentials.
        with PrivateConnectionStore(Path(args.store) / ("job-" + str(args.order_id))) as journal:
            print(json.dumps(fulfill(client, args.order_id, text, journal, deliver=args.deliver), indent=2))


if __name__ == "__main__":
    main()
