"""Read-only live order monitor. Python 3.11+, serving-release SDK."""
import json
import os
from invastor import connect

api_url = os.environ.get("INVASTOR_API_BASE")
client_id = os.environ.get("INVASTOR_CLIENT_ID")
purchase_id, key = os.environ.get("PURCHASE_ID"), os.environ.get("PURCHASE_KEY")
if not api_url or not client_id or bool(purchase_id) == bool(key):
    raise SystemExit("Set INVASTOR_API_BASE, original INVASTOR_CLIENT_ID and exactly one original PURCHASE_ID or PURCHASE_KEY")
with connect(api_url, client_id=client_id) as agent:
    result = agent.watch_purchase(
        **({"purchase_id": int(purchase_id)} if purchase_id else {"idempotency_key": key}),
        on_update=lambda value: print(json.dumps({"id": value["purchase"]["id"], "lifecycle": value["purchase"].get("lifecycle")})))
    print(json.dumps({"monitoring": result["monitoring"]}))
    print(json.dumps(agent.purchase_evidence(result["purchase"]["id"])))
    if result["monitoring"]["outcome"] != "COMPLETE":
        raise SystemExit(2)
