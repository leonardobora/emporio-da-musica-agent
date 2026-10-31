#!/usr/bin/env python3
"""Profile every CSV in a directory: shape, empties, key duplicates, ranges.

Usage: python3 csv_profile.py <dir>

Prints a Markdown-ready report for pasting into docs/notes/01-data-audit.md.
Stdlib only. It finds the generic shape; the planted traps (totals vs line items,
status vs stock, dates vs today, flag columns) still need hand-written checks.
"""
import csv
import os
import re
import sys
from collections import defaultdict

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
IDLIKE_RE = re.compile(r"(^id$|_id$|^email$|_code$)")


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def profile(name, rows):
    if not rows:
        print(f"\n## {name} — EMPTY\n")
        return {}
    cols = list(rows[0].keys())
    print(f"\n## {name} — {len(rows)} rows x {len(cols)} cols\n")
    print("| column | empty | distinct | sample | range / note |")
    print("|---|---|---|---|---|")
    keys = {}
    for c in cols:
        vals = [(r.get(c) or "").strip() for r in rows]
        filled = [v for v in vals if v]
        empties = len(vals) - len(filled)
        distinct = len(set(filled))
        sample = next((v for v in filled if v), "")[:40]
        note = ""
        nums = [as_float(v) for v in filled]
        dates = [v for v in filled if DATE_RE.match(v)]
        if filled and all(n is not None for n in nums):
            note = f"numeric {min(nums):g} .. {max(nums):g}"
        elif filled and len(dates) == len(filled):
            note = f"dates {min(dates)} .. {max(dates)}"
        if distinct < len(filled):
            note = (note + "; " if note else "") + f"{len(filled) - distinct} repeated values"
        if IDLIKE_RE.search(c):
            keys[c] = set(filled)
        print(f"| {c} | {empties} | {distinct} | {sample} | {note} |")
    return keys


def dupes(name, rows):
    seen = defaultdict(int)
    for r in rows:
        seen[tuple(r.values())] += 1
    full = sum(1 for v in seen.values() if v > 1)
    if full:
        print(f"\n- {name}: {full} duplicated whole rows")
    for c in rows[0].keys():
        if IDLIKE_RE.search(c) and not c.endswith("_id"):
            vals = [(r.get(c) or "").strip() for r in rows if (r.get(c) or "").strip()]
            rep = sorted({v for v in vals if vals.count(v) > 1})
            if rep:
                print(f"- {name}.{c}: reused by several rows -> {rep[:5]}")


def fk_check(keysets):
    """Report *_id values absent from every other file exposing the same column."""
    for name, keys in keysets.items():
        for col, vals in keys.items():
            if not col.endswith("_id"):
                continue
            others = [n for n, k in keysets.items() if n != name and col in k]
            if not others:
                continue
            universe = set()
            for n in others:
                universe |= keysets[n][col]
            orphans = sorted(vals - universe, key=lambda x: (len(x), x))
            if orphans:
                print(f"\n- {name}.{col}: {len(orphans)} values absent from {others}: {orphans[:5]}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    root = sys.argv[1]
    files = sorted(f for f in os.listdir(root) if f.lower().endswith(".csv"))
    if not files:
        print(f"no CSV files in {root}")
        return 1
    tables, keysets = {}, {}
    for f in files:
        rows = load(os.path.join(root, f))
        tables[f] = rows
        keysets[f] = profile(f, rows)
    print("\n## Cross-file checks\n")
    for f, rows in tables.items():
        if rows:
            dupes(f, rows)
    fk_check(keysets)
    print("\nNow hand-write: totals vs line items, status x stock, dates vs today, flag columns.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
