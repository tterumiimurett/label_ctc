#!/usr/bin/env python3
"""Create private annotator tokens and their individual annotation URLs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
from urllib.parse import quote


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Public app URL, without query parameters")
    parser.add_argument("--output", type=Path, default=Path("annotators.json"))
    parser.add_argument("names", nargs="+", help="Names used only in the private administrator file")
    args = parser.parse_args()
    entries = []
    for name in args.names:
        token = secrets.token_urlsafe(24)
        entries.append({
            "display_name": name,
            "token": token,
            "url": f"{args.base_url.rstrip('/')}?annotator={quote(token)}",
        })
    args.output.write_text(
        json.dumps({"schema": "lab-ctc-annotators-v1", "annotators": entries}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(entries)} private annotator links to {args.output}")


if __name__ == "__main__":
    main()
