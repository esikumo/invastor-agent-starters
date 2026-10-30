"""InVastor LangChain tools. Python 3.11+, langchain-core>=1.0,<2.
Download invastor_commerce.py beside this file. Default: fixture sandbox only.
No model/provider is required for the runnable demo; bind tools to your own agent.
Do not put credentials or connection records into prompts, tool arguments or traces.
"""
import argparse
from langchain_core.tools import StructuredTool
from invastor_commerce import SandboxCommerce, InVastorCommerce


def build_tools(client):
    """Read/quote/status only. No approval, funding, purchase, acceptance or payout tools."""
    if not isinstance(client, (SandboxCommerce, InVastorCommerce)):
        raise TypeError("Use an explicit InVastor sandbox or owner-connected commerce client")
    sandbox = isinstance(client, SandboxCommerce)
    label = "SIMULATION ONLY" if sandbox else "LIVE CATALOG; no payment authority in these tools"

    def search_services(query: str = "") -> dict:
        """Search permitted marketplace listings. Read the listing type before selecting a service."""
        return client.catalog(query)

    def quote_listing(listing_id: str, quantity: int = 1) -> dict:
        """Get an estimate, not an inventory reservation or permission to pay."""
        identity = listing_id if sandbox else int(listing_id)
        return client.quote(identity, quantity)

    def purchase_status(purchase_id: str) -> dict:
        """Inspect an existing purchase. Never re-create or resend a payment."""
        return client.purchase_status(purchase_id if sandbox else int(purchase_id))

    return [
        StructuredTool.from_function(search_services, name="invastor_search", description=label + ": " + search_services.__doc__),
        StructuredTool.from_function(quote_listing, name="invastor_quote", description=label + ": " + quote_listing.__doc__),
        StructuredTool.from_function(purchase_status, name="invastor_status", description=label + ": " + purchase_status.__doc__),
    ]


def main():
    parser = argparse.ArgumentParser(description="Run actual LangChain tool calls against fictional inventory; no LLM or money.")
    parser.add_argument("--api-url", required=True, help="Your serving origin plus /api")
    parser.add_argument("--query", default="keyboard")
    parser.add_argument("--scenario", default="happy_path", choices=[
        "happy_path", "out_of_stock", "price_changed", "budget_limit", "revoked_permission", "duplicate_request"])
    args = parser.parse_args()
    client = SandboxCommerce(args.api_url, scenario=args.scenario)
    tools = build_tools(client)
    found = tools[0].invoke({"query": args.query})
    print("SIMULATION ONLY. No model called; no real orders, wallet actions or payments.")
    print(found)
    if found["items"]:
        print(tools[1].invoke({"listing_id": found["items"][0]["id"], "quantity": 1}))


if __name__ == "__main__":
    main()
