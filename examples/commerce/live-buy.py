"""Requires explicit live approval, owner-approved marketplace authority and a local wallet module."""
import json, os
from invastor import connect
from invastor_wallet import NodeWallet
if os.environ.get("INVASTOR_APPROVE_LIVE_PURCHASE") != "yes":
    raise SystemExit("Set INVASTOR_APPROVE_LIVE_PURCHASE=yes only after owner spending and wallet approval")
with open(os.environ["INVASTOR_DRAFT_FILE"]) as source: draft = json.load(source)
wallet = NodeWallet(module=os.environ["INVASTOR_WALLET_MODULE"], bridge=os.environ["INVASTOR_WALLET_BRIDGE"])
with connect(os.environ["INVASTOR_API_BASE"], client_id=os.environ["INVASTOR_CLIENT_ID"]) as agent:
    catalog = agent.catalog(os.environ.get("INVASTOR_SEARCH", ""))
    if not any(item["id"] == draft["listingId"] for item in catalog["items"]):
        raise RuntimeError("Requested listing is outside this catalog/grant")
    names = {"packageName":"package_name","shippingMethod":"shipping_method","shippingAddress":"shipping_address",
             "shippingAddressId":"shipping_address_id","selectedVariants":"selected_variants"}
    quote = agent.quote(draft["listingId"], draft.get("quantity", 1),
        **{target:draft[key] for key,target in names.items() if key in draft})["quote"]
    print(json.dumps(quote))
    if not quote.get("prePurchase") or quote["prePurchase"]["requiresSellerClarification"]:
        raise RuntimeError("Resolve missing seller terms/delivery information before buying")
    result = agent.purchase_autonomously(draft, operation_id=os.environ["INVASTOR_OPERATION_ID"],
        payment_currency="usdcsol", wallet=wallet)
    print(json.dumps(result))
    if result["purchase"]["state"] == "PAID":
        print(json.dumps(agent.watch_purchase(purchase_id=result["purchase"]["id"])))
