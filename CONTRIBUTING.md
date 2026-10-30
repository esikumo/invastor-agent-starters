# Contributing

Start with the sandbox and keep live spending explicitly opt-in.
Report the runtime version, example command and sanitized error in an issue.
Never include tokens, wallet material, customer details or private journals.

Before a pull request:

```bash
python3 scripts/check.py
node --test tests/sandbox-transport.test.mjs
```

Describe how you verified the behavior. A simulation is not proof of live
funding or seller payout. Do not fix a flaky test by weakening spending,
ownership, idempotency, account approval or settlement checks.

Example files are exported from the maintained InVastor download sources.
Maintainers must reconcile changes with those sources and regenerate
`SOURCES.json`; it is not a substitute for reviewing the changes.

Please keep contributions focused and compatible with the MIT license.
