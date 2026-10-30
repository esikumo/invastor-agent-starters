"""Offline checks only: no wallets, account approvals, or marketplace calls."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "SOURCES.json").read_text())
for name, digest in manifest["files"].items():
    path = root / name
    assert path.is_file(), f"Missing exported example: {name}"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, f"Source mismatch: {name}"

for path in root.rglob("*.py"):
    ast.parse(path.read_text(), filename=str(path))
for path in root.rglob("*.mjs"):
    subprocess.run(["node", "--check", str(path)], check=True)
assert not (root / ".env").exists(), "Never commit a real .env"
assert "SIMULATION ONLY" in (root / "examples/commerce/sandbox.mjs").read_text()
assert "SANDBOX_INVALID_RESPONSE" in (root / "examples/commerce/lifecycle-sandbox.mjs").read_text()
print(f"PASS: {len(manifest['files'])} exported examples match their source hashes; Python and JS syntax valid")
