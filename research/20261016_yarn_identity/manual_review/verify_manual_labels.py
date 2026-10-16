"""Verify manually reviewed pair-link truth without treating unknown as negative."""
from __future__ import annotations
import csv
from collections import Counter
from pathlib import Path

FILE = Path(__file__).parent / "review_labels.csv"
with FILE.open("r", encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))

assert len(rows) == 29, f"Expected 29 stable candidates, got {len(rows)}"
assert len({row["review_id"] for row in rows}) == 29, "Duplicate review_id"
counts = Counter(row["verdict"].strip() or "unreviewed" for row in rows)
assert counts["different"] == 24, counts
assert counts["unreviewed"] == 5, counts
assert counts["same"] == 0, counts
assert set(counts) == {"different", "unreviewed"}, counts
assert all(row["A_x"] and row["A_y"] and row["B_x"] and row["B_y"] for row in rows)
print("PASS: 29 stable candidates = 24 manually confirmed DIFFERENT + 5 unreviewed.")
print("No confirmed positive same-yarn links; recall cannot be estimated.")
