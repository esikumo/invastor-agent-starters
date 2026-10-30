# InVastor Agent Starters

Build a commerce agent with JavaScript, Python, or LangChain. Start with fictional
inventory and simulated payments—no account, wallet, model key, or SDK installation
is needed for the basic sandbox examples.

**[Developer hub](https://invastor.com/developers)** ·
**[Use this template](https://github.com/esikumo/invastor-agent-starters/generate)** ·
**[Report a problem](https://github.com/esikumo/invastor-agent-starters/issues)**

## Run your first sandbox agent

Prerequisites: Git and either Node.js 20+ or Python 3.11+. Commands below use a
POSIX shell (Linux, macOS, or Windows with WSL).

```bash
git clone https://github.com/esikumo/invastor-agent-starters.git
cd invastor-agent-starters
export INVASTOR_API_BASE="https://invastor.com/api/"
```

Choose **one**:

```bash
# JavaScript: compare fictional products and simulate an approved purchase
node examples/commerce/sandbox.mjs happy_path --approve-simulation

# Python: search, quote and simulate an approved purchase
python3 examples/commerce/sandbox.py happy_path --approve-simulation
```

Expect output ending with `PASS: SIMULATED_PAID`. This is not a real purchase or
proof of a seller payment. The explicit flag approves a simulation only.
The JavaScript example is rule-based, not an AI model.

Alternatively click **Use this template → Create a new repository**, clone your
copy, and run the same commands.

## Choose a starter

| Starter | Location | What it does |
| --- | --- | --- |
| JavaScript sandbox buyer | `examples/commerce/sandbox.mjs` | Compares fixture prices and stock within a budget; simulates approval. |
| Python sandbox buyer | `examples/commerce/sandbox.py` | Searches, quotes and prepares a simulated purchase. |
| Full lifecycle tests | `examples/commerce/lifecycle-sandbox.*` | Exercises insufficient funds, lost responses, refunds and payout failures using simulated funds. |
| LangChain / LangGraph tools | `examples/langchain/` | Real LangChain search/quote/status tools; no model key needed for the demo. |
| Read-only order monitor | `examples/commerce/monitor.*` | Watches an existing authorized live purchase without paying again. |
| Opt-in live buyer reference | `examples/commerce/live-buy.*` | Advanced example requiring separate account approval, payment authority and wallet setup. |

There is no ready-made inventory watcher in this release. Adapt the examples to
your use case; do not treat fixture stock as live merchant inventory.

### LangChain

```bash
cd examples/langchain
python3 -m pip install -r requirements.txt
python3 invastor_langchain.py --api-url https://invastor.com/api/
```

Follow [the LangChain guide](examples/langchain/README.md) to bind tools to your
own model/graph or operate a seller service. Model usage is optional and may cost
money. The default tool demo never buys, pays, signs or approves.

### Full simulated lifecycle

```bash
node examples/commerce/lifecycle-sandbox.mjs --approve-simulation
# Or:
python3 examples/commerce/lifecycle-sandbox.py --approve-simulation
```

These take longer than the basic example: they deliberately pause for rate limits.
Both `/api` and `/api/` work. Safe retries honor `Retry-After` and stop after two
retries. An HTML gateway error after a write is uncertain, not permission to create
a replacement purchase. Preserve the original purchase key.

## Customize and run continuously

1. Get a successful sandbox run.
2. Change the search, budget and business logic. JavaScript supports
   `--query=keyboard --budget=60 --quantity=1`.
3. Run locally or on a host with the documented runtime. For a short sandbox job,
   run the command above as a one-off job; it exits after finishing.
4. For an ongoing agent, supply your own scheduler or worker loop with rate limits.
   We do not include a one-click production deployment or claim verified
   under-ten-minute live purchasing.

`.env.example` documents settings. Copying it to `.env` does **not** automatically
load it: export values in your shell or use your deployment's private settings.
Live SDK connections need Linux/POSIX and persistent, private storage.

## Live use is separate

Installing or running a sandbox example never authorizes live spending.

- The account owner must approve the agent connection and its actual permissions.
- Purchasing requires approved budgets and supported payment configuration;
  an API token is not a wallet signing key.
- Live funding, signing and seller payout are separate steps. `PAID` does not mean
  delivered or seller payout finalized.
- Preserve the original operation identity and private journal on uncertain writes.
  Never switch languages/runtimes to retry a payment.
- Never commit keys, tokens, wallet files, customer data or connection stores.
- Publication eligibility and marketplace rules still apply.

Read [the full commerce guide](examples/commerce/README.md) before using live
references. Install any optional SDK from the **same serving release** documented
there, not an unverified package with a similar name.

## Check this repository

```bash
python3 scripts/check.py
node --test tests/sandbox-transport.test.mjs
```

These checks are offline. GitHub Actions runs them on pushes and pull requests;
they do not create live orders or use credentials. Sandbox demonstrations require
network access to a running InVastor sandbox.

## Keeping examples synchronized

The examples are exported from the same maintained source used by InVastor's
downloadable kits. `SOURCES.json` records the SHA-256 of each exported example.
GitHub can include a newer development snapshot than the serving website; compare
the actual files, not assumed release dates. Maintainers should re-export and
review the examples for each update rather than editing generated copies alone.

## License and contributions

MIT—see [LICENSE](LICENSE). This license covers this starter repository, **not**
InVastor's platform, trademarks, hosted service, or third-party dependencies.
Dependencies retain their own licenses. No affiliation with or endorsement by
LangChain, LangGraph, wallet vendors or model providers is implied.

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
