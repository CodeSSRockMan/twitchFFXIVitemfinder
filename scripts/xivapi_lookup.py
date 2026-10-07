#!/usr/bin/env python3
"""xivapi_lookup.py

Quick script to query XIVAPI (v2) for an item name and print results.

It will try a few probable endpoints (v2 and fallback v1) and print the first
successful JSON response for inspection. Useful to see what data needs parsing.

Usage:
  python scripts/xivapi_lookup.py Laurel
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
import ssl
import traceback
from typing import Optional, Tuple

ENDPOINT_CANDIDATES = [
    "https://v2.xivapi.com/search",
    "https://v2.xivapi.com/api/search",
    "https://xivapi.com/search",
    "https://v1.xivapi.com/search",
    # fallback generic sheet search (some APIs expose sheet endpoints)
    "https://v2.xivapi.com/api/sheet/Item",
]


def http_get(url: str, params: dict) -> Tuple[int, str, str]:
    """Perform a GET request. Prefer requests if available, else use urllib."""
    try:
        import requests
    except Exception:
        requests = None

    headers = {"User-Agent": "xivapi-lookup/0.1"}
    if requests:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        return r.status_code, r.headers.get("Content-Type", ""), r.text

    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    full = f"{url}?{query}"
    req = urllib.request.Request(full, headers=headers)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        data = resp.read()
        return resp.getcode(), resp.getheader("Content-Type", ""), data.decode("utf-8")


def try_search(name: str) -> Optional[dict]:
    name = name.strip()
    for url in ENDPOINT_CANDIDATES:
        # Try multiple common query parameter names used by different XIVAPI versions
        param_variants = [
            {"string": name, "indexes": "Item", "limit": 50},
            {"query": name, "indexes": "Item", "limit": 50},
            {"q": name, "indexes": "Item", "limit": 50},
        ]
        for params in param_variants:
            # special-case sheet endpoint: it expects an id suffix or 'search' won't work
            try_url = url
            try:
                status, ctype, text = http_get(try_url, params)
            except Exception as e:
                print(f"Request to {try_url} failed: {e}")
                traceback.print_exc()
                time.sleep(0.1)
                continue

        print(f"Tried {try_url} -> status {status}, content-type {ctype}")
        if status != 200:
            # print a short excerpt for debugging
            print((text or "")[:1000])
            continue

        try:
            j = json.loads(text)
        except Exception:
            print("Response is not valid JSON; printing raw (truncated):")
            print((text or "")[:4000])
            continue

        # Heuristics: search responses commonly include keys like 'Results' or 'results'
        if isinstance(j, dict) and any(k.lower() in ("results", "data", "pagination") for k in j.keys()):
            return {"endpoint": try_url, "response": j}

        # If response looks like a sheet / single object, still return it
        if isinstance(j, dict) and len(j) > 0:
            # If this is a sheet-like response with 'rows', try to locate matching rows by Name
            rows = j.get("rows") or j.get("Rows")
            if isinstance(rows, list):
                matches = []
                low = name.lower()
                for r in rows:
                    fields = r.get("fields") if isinstance(r, dict) else None
                    if not isinstance(fields, dict):
                        continue
                    item_name = fields.get("Name") or fields.get("name") or ""
                    if item_name and low in str(item_name).lower():
                        matches.append({"row_id": r.get("row_id"), "fields": fields})
                if matches:
                    return {"endpoint": try_url, "response": {"matches": matches, "source": j}}
            return {"endpoint": try_url, "response": j}

    return None


def main(argv: list[str]):
    if len(argv) < 2:
        print("Usage: python scripts/xivapi_lookup.py <search-name>")
        return 2
    name = " ".join(argv[1:]).strip()
    print(f"Searching XIVAPI for '{name}'...")
    res = try_search(name)
    if not res:
        print("No usable response from XIVAPI endpoints tried.")
        return 1

    endpoint = res.get("endpoint")
    j = res.get("response")
    out_path = f"tmp/xivapi_search_{urllib.parse.quote(name)}.json"
    try:
        import os
        os.makedirs("tmp", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(j, fh, ensure_ascii=False, indent=2)
        print(f"Saved full JSON to {out_path}")
    except Exception as e:
        print("Could not save JSON to tmp/ - continuing:", e)

    print(f"Endpoint: {endpoint}\n--- JSON (truncated) ---")
    print(json.dumps(j, indent=2)[:4000])
    # If the response has a Results/data list, print a short table of entries
    if isinstance(j, dict):
        results = j.get("Results") or j.get("results") or j.get("data") or j.get("Data")
        if isinstance(results, list):
            print(f"\nFound {len(results)} result(s). Showing up to 10:\n")
            for r in results[:10]:
                # print common fields if present
                name_field = r.get("Name") or r.get("name") or r.get("Name_en") or r.get("EnglishName")
                print(json.dumps({k: r.get(k) for k in ("ID", "Id", "ID", "ItemId", "Name", "name") if k in r}, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
