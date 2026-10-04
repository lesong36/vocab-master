"""Verify bundled whole-word IPA coverage and sense-sensitive textbook readings."""

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "phonetics.json").read_text())
entries = data["entries"]
unavailable = data.get("unavailable", {})
with (ROOT / "词库.md").open(encoding="utf-8-sig", newline="") as source:
    rows = [row for row in csv.DictReader(source)
            if row["section"][:1] in "三四五六" and row["section"][1:2] in "上下"]
keys = {re.sub(r"\s*\(pl\..*\)\s*$", "", row["english_word"].strip().lower()) for row in rows}
assert not any("/" in key for key in keys), "Alternative English forms must be separate entries"
assert not (set(entries) & set(unavailable)), "Unavailable readings must not have fabricated IPA"
assert keys <= (set(entries) | set(unavailable)), sorted(keys - set(entries) - set(unavailable))
for key in keys & set(entries):
    ipa = entries[key]
    assert isinstance(ipa, str) and re.fullmatch(r"/[^/\r\n]+/", ipa), (key, ipa)
    assert "..." not in ipa, (key, ipa)
for key in keys & set(unavailable):
    assert isinstance(unavailable[key], str) and unavailable[key].strip(), key
for word, expected in {"use": "/juːz/", "live": "/lɪv/", "read": "/riːd/"}.items():
    assert entries[word] == expected, (word, entries[word], expected)
assert entries["who"] == "/huː/", "The pronoun who must retain its reading"
assert entries["who (world health organization)"] != entries["who"], "WHO needs letter-name pronunciation"
print(f"Validated {len(keys & set(entries))}/{len(keys)} textbook readings; explicitly unavailable: {sorted(keys & set(unavailable))}")
