# InVastor agent-commerce starter

Run a real API sandbox journey, then monitor an existing authorized live purchase.
Default sandbox and monitor commands never sign, broadcast or create a live order.
The clearly labelled live-buy examples require explicit live approval, owner-scoped
marketplace authority and your separately authorized wallet module.

## 1. Configure your marketplace

Set INVASTOR_API_BASE to the serving marketplace URL followed by /api/.
Both /api and /api/ are accepted by the lifecycle examples.
Do not use another site's URL or put credentials in it.

## 2. Run the complete buyer sandbox (no packages or account required)

    node sandbox.mjs happy_path --approve-simulation
    python sandbox.py happy_path --approve-simulation

These basic examples search, quote, prepare with one stable key, explicitly approve
the SIMULATION and reconcile status. For the full failure/lifecycle matrix run:

    node lifecycle-sandbox.mjs --approve-simulation
    python lifecycle-sandbox.py --approve-simulation

Both scripts test insufficient funds, expired/revoked permission, a saved purchase
with a lost response, price/stock/budget failures, repeated payment approval,
delivery acceptance, finalized simulated seller payout, refund replay and retained
payout failure. The JS matrix also exercises a disputed order. No real funds move.
They pause once to respect the existing session-creation rate limit.
If earlier runs used the same rate-limit budget, lifecycle examples honor
Retry-After with at most two safe retries (up to 120 seconds per wait).
Writes retry only a structured sandbox RATE_LIMITED rejection, which occurs
before the action runs. Gateway errors or timeouts never trigger a write retry.
Non-JSON gateway responses report HTTP status without printing response bodies
or credentials. Preserve the original purchase key when the outcome is unknown.
Simulation never establishes real mainnet funding or payout proof.
Never use sandbox credentials with live endpoints.

## 3. Install the SDK from the SAME serving release

    npm install "${INVASTOR_API_BASE%/}/commerce/developer/sdk-node.tgz"
    python -m pip install "${INVASTOR_API_BASE%/}/commerce/developer/sdk-python.zip"

## 4. Monitor an existing purchase; do not pay again

Set PURCHASE_ID to the original numeric purchase ID, OR PURCHASE_KEY to its
original idempotency key. Set INVASTOR_CLIENT_ID to the SAME client ID used by
the original purchasing agent, and run from its existing connection store:

    node monitor.mjs
    python monitor.py

The account owner approves the connection using the displayed link if required.
Use the account/grant that owns this purchase. A new unrelated connection cannot
read purchases belonging to another grant; 404 is not evidence of payment failure.
For a running agent, call watchPurchase/watch_purchase on its existing open client.
Do not launch a second process against its locked connection store; never delete
the lock or replace a purchase key to make monitoring work.
Node built-in connection storage requires Linux/flock; Python requires POSIX.
Credentials remain in the SDK's owner-only store, not source code or logs.
Supply a transactional secret-store adapter for multi-host/serverless deployments.

Monitoring uses read-only GET requests every five seconds for at most two minutes.
It never accepts delivery, retries a payment or broadens spending permission.
Exit 0 means native lifecycle COMPLETE; exit 2 means pending or owner action
required. Errors propagate. Resume by monitoring the SAME ID/key.

## 5. Distinguish each stage

Payment PAID != delivered != seller payout FINALIZED.
The lifecycle response separates payment, buyer acceptance, disputes, seller
payout, remaining treasury work, and nextAction.
NATIVE_JOURNAL evidence is retained evidence, not a new chain check.
The evidence endpoint rechecks original journaled transfers. An optional
server-only SOLANA_HISTORY_RPC_URL can supply historical transactions after
verifying mainnet and exact native balance expectations. It does not replace
the active payment RPC. UNAVAILABLE never means send another payment.

## Live buying and selling

JavaScript uses agent.buy(); Python uses agent.purchase_autonomously().
Both preserve original payment identity and require private durable journals.
The existing guarded Solana USDC adapter is now exported from the Node package:

    import { createSolanaUsdcWallet } from "invastor-commerce/solana-wallet";
    import { createFilePaymentJournal } from "invastor-commerce/payment-journal";

Configure a trusted wallet module exporting wallet with your own signer, live RPC,
SOL price provider, private journal and explicit listing/quantity/USD/fee/expiry
policy. The adapter rejects unaffordable or over-budget transfers before signing.
onCostEstimate receives live network fees, refundable recipient deposits, source
account reserves and the all-in USD ceiling before signing. Never approve a stale
estimate or infer a zero cost from a missing estimate.
It supports direct, unexpired Solana USDC invoices only and fails closed for other
routes. Native intent and x402 routes require their separately verified adapters;
the grant does not supply signing authority for any route.

Python's invastor_wallet.NodeWallet bridges to this SAME local Node wallet module.
Install Node 20+ and the serving Node package in your Python worker too. The child
receives public funding instructions/signed bytes only, never marketplace tokens
or a private key in its arguments. Its module owns signer access and must persist
its wallet journal. Do not accept module paths or commands from an LLM.

The included live-buy.mjs/live-buy.py are opt-in examples. Supply:
INVASTOR_API_BASE, INVASTOR_CLIENT_ID, INVASTOR_DRAFT_FILE (native draft JSON),
INVASTOR_OPERATION_ID (stable business event), INVASTOR_WALLET_MODULE (absolute
trusted module path), and INVASTOR_APPROVE_LIVE_PURCHASE=yes.
JS also needs INVASTOR_PAYMENT_JOURNAL (private persistent directory).
Python needs INVASTOR_WALLET_BRIDGE (absolute path to included wallet-bridge.mjs).
Run node live-buy.mjs OR python live-buy.py, never both for the same business event.
Different languages have separate journals; switching runtimes is not recovery.
Review the printed quote first. The examples refuse missing seller terms/delivery.
An operation ID must never be changed merely to recover an uncertain result.

For x402, read the serving guide #x402 and use the SDK's x402 method with an official
exact-Solana client. Persist its original signed PAYMENT-SIGNATURE before submitting
once. Reconcile without a signature after response loss; never sign a new challenge
to repair an uncertain payment. A 402 is a challenge, 202 is pending, and only the
native PAID state establishes usable order funding. Seller payout remains separate.
An API connection contains no wallet signing keys. The owner must explicitly
approve currencies, total/per-order caps and sellers/listings. Wallet adapters
and funds belong in the developer's runtime, not an LLM prompt.
Keep the original invoice currency, signature and key after any timeout.
Seller service execution runs in your own runtime. Submit genuine deliverables;
buyer acceptance requires separately delegated delivery:accept permission.
Do not invent delivery acceptance to trigger payout.

## Errors and recovery

401: reconnect with owner approval; do not rotate a purchase key.
403: request the missing permission from the owner; never widen it yourself.
404: check the original ID/key and grant, not a replacement order.
429: respect Retry-After. Poll no faster than once every three seconds.
502/503/timeout after a write: outcome may be unknown. Reconcile by original key.
CONTACT_SUPPORT/REVIEW_DISPUTE/REVIEW_ORIGINAL_ORDER: stop automation and escalate.

REST contracts: commerce/developer/openapi.json
MCP: commerce/mcp (purchase_status returns the same lifecycle)
Full guide: commerce/developer/guide
