# InVastor LangChain starter

## Before publishing: $10 verifiable InVastor Coin

Before publishing new products, services or blogs, tell the account owner to hold at least $10 worth of real InVastor Coin in their own signed, linked Solana wallet at the current verified market price. Existing content included in the owner's one-time restoration is grandfathered; its visibility and edits do not require this holding. Grandfathering belongs to that content, not permission to publish new items. The owner's account qualifies; each delegated agent does not need a separate holding. Owner-designated exemptions still apply. Reward points, shopping credits and payout-only wallet addresses do not qualify. Ask the owner to open /wallet, add and sign to verify their wallet, and use /invastor-coin#publication-requirement for buying instructions. Never request a seed phrase or private key, sign for the owner, or buy coins without explicit authority. The signed-in owner can GET /api/users/me/publication-holdings for status and POST the same endpoint to recheck; these endpoints require the owner's signed-in session, not a commerce agent grant or merchant API key. On PUBLICATION_HOLDINGS_REQUIRED or a propagated publication-eligibility error, stop publication, show the owner the reason and setup links, and wait for verification instead of retrying in a loop. Verification unavailable can return HTTP 503: it is not proof of insufficient holdings. Future non-grandfathered content can be suspended reversibly if holdings cease to qualify; after qualifying the owner chooses to reactivate it. Moderation removals, private drafts and retired seed inventory are not restored. Existing orders and paid downloads are unaffected. Mere API connection, browsing and buying do not require this publishing holding. This is not a fee or transfer to InVastor, does not prove seller authenticity and does not override moderation or grant spending or wallet-signing authority.

Python 3.11+. These files are downloadable source examples, NOT a published npm/PyPI
package, provider endorsement, or instant per-call billing wrapper. These repository examples are MIT-licensed; third-party dependencies retain their own licenses.
Check the live readiness endpoint before using live features. Your runtime executes work.

## Fast path: connect once and use simple actions

    from invastor import connect
    with connect("https://YOUR_HOST/api", client_id="my-marketplace-agent") as agent:
        print(agent.catalog("repair"))
        # agent.publish_listing(your_listing, operation_id="listing-123-v1")
        # agent.post_buying_request(your_request, operation_id="request-456")

The helper is included in this download. It handles private storage, process
locking, resume, refresh and durable operation journals. No copied tokens or
custom storage callback. On first run, send the approval link to the account
owner. Default combined access is search and posting without spending; enable
purchasing only with explicit owner approval and limits. Credentials are
owner-only files, not encrypted at rest: use encrypted persistent private disks,
one worker per connection. Advanced hosted adapters remain available below.

Optional installable SDK-only packages are linked from the developer quickstart;
they do not require LangChain. Those packages are served by the site, not npm/PyPI.

## 1. Optional sandbox LangChain tool calls (no money, no model)

Extract all files into one directory.

    python -m pip install -r requirements.txt
    python invastor_langchain.py --api-url https://YOUR_HOST/api

This uses actual langchain_core StructuredTool objects to search fictional inventory
and get a simulated quote. It never buys, approves, signs or pays. No model/API key
is needed. Pass --scenario out_of_stock to exercise failure. Session tokens expire
and sessions disappear on restart. The sandbox is not real merchant inventory.

## 2. Bind to your own LangChain / LangGraph agent

    from invastor_commerce import SandboxCommerce
    from invastor_langchain import build_tools
    tools = build_tools(SandboxCommerce("https://YOUR_HOST/api"))
    # Connect these tools to your chosen model/graph; e.g. model.bind_tools(tools).

Only search, quote, and purchase-status tools are exposed. Approval, purchasing,
funding, delivery acceptance, refunds, payout, tokens and wallet keys are NOT model
tools. Model usage is optional, separately configured and potentially billable.

## 3. Live owner connection, no token copying

    from invastor_commerce import InVastorCommerce
    from invastor_connection_store import PrivateConnectionStore
    from invastor_langchain import build_tools
    with PrivateConnectionStore("./private-buyer") as store:
        saved = store.load()
        client = (InVastorCommerce("https://YOUR_HOST/api",
                  connection=saved, save_connection=store.save) if saved else
                  InVastorCommerce.connect("https://YOUR_HOST/api",
                  client_id="my-langchain-buyer", client_name="My LangChain buyer",
                  role="buyer", save_connection=store.save,
                  on_verification=lambda n: print(n["verificationUri"], flush=True)))
        tools = build_tools(client)
        print(tools[0].invoke({"query": "research"}))
        # Run your agent INSIDE this block so the connection stays locked.

The account owner reviews and approves the link once. Credentials go only to your
runtime; access renewal preserves native grant identity, scopes, committed budgets
and original authorization expiry. Refresh is serialized inside a client. Use one
runtime per connection. No automatic write/refresh retry. On uncertain refresh or
durable-save failure reconcile or reconnect; do not keep resending the old token.
Never put stores in Git, web roots, prompts or tracing. The POSIX local store holds
plaintext secrets with 0700/0600 permissions and a process lock. For multi-host
deployments use your own encrypted transactional secret store and distributed lock.
Wallet signing is separate. An agent grant is not a wallet key.

## 4. Run a real service you provide

First offer an accurately described, positively priced text-statistics service.
Agree on the actual input, acceptance rules and native service terms with a buyer.
Do not deliver this example to an unrelated job. The example never creates fake
listings, buyer acceptance, payments, shipments or earnings.

    python invastor_seller.py --api-url https://YOUR_HOST/api --store ./private-seller

Approve the seller's owner link; it lists your own authorized service jobs.
For an already-funded text-statistics job:

    python invastor_seller.py --api-url https://YOUR_HOST/api --store ./private-seller --order-id JOB_ID --input input.txt

This only inspects the job and computes a report. After both parties have accepted
the service agreement and you confirm the job/input match the service, add --deliver
to submit the actual deterministic result. A private per-job journal precedes every
mutation; uncertain writes are not retried. Inspect the original job to reconcile.
Buyer acceptance and eligible payout are separate; delivery alone does not release money.

## 5. Real paid demonstration: required evidence, not a sandbox claim

Publish and check the serving SDK/connection contract first. Obtain each account's
own buyer/seller grants; the platform owner does not approve outside developers.
For the owner's previously authorized ONE $5 demo, preserve that total all-in cap,
including network costs. Do not start a replacement payment on uncertain outcomes.
The buyer agent defines the job, the seller agent performs genuine matching work,
and a separately authorized buyer reviews the result against the agreed rules.
Retain the original job/order and payment identifiers, delivery evidence, explicit
acceptance and the native final seller-transfer signature with its frozen recipient
and amount. Verify finalized chain settlement before claiming seller payout.

Metered jobs differ from ordinary orders: separately consented capped USDC funding,
1% of accepted service value, fractional carry and aggregated settlement starting
at $1 (cost checks may require more). No smart-contract escrow or zero-fee claim.
The text-statistics example demonstrates ordinary native service execution; it
does not pretend to implement metered result submission or a paid BaseTool decorator.

Availability, enabled flags, simulated approval, allocated balances, and invoking
a payout worker are NOT proof of real payment-to-payout. Readiness remains explicitly
unverified until the real evidence exists. No live money is spent by installation
or by the LangChain starter.
