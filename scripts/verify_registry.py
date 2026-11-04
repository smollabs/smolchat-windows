"""Re-check every entry in resources/models.json against the Hugging Face Hub.

Confirms that each repository exists at the pinned revision and that every
file's size and SHA-256 (the LFS object id) match the registry. Requires
network access; run before releasing a registry update:

    python scripts/verify_registry.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://huggingface.co/api/models/{repo}/tree/{rev}"


def main() -> int:
    registry = json.loads((ROOT / "resources" / "models.json").read_text())
    failures = 0
    for model in registry["models"]:
        url = API.format(repo=model["repo"], rev=model["revision"])
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                tree = {f["path"]: f for f in json.load(resp)}
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {model['id']}: {model['repo']}@{model['revision'][:8]} – {exc}")
            failures += 1
            continue
        for f in model["files"]:
            remote = tree.get(f["filename"])
            if remote is None:
                print(f"FAIL {model['id']}: missing {f['filename']}")
                failures += 1
            elif remote["size"] != f["size"] or (remote.get("lfs") or {}).get("oid") != f["sha256"]:
                print(f"FAIL {model['id']}: {f['filename']} size/sha256 mismatch")
                failures += 1
        if not failures:
            print(f"ok   {model['id']}")
    print("All entries verified." if not failures else f"{failures} problem(s) found.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
