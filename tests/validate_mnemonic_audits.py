"""Audit traceability checks, not a test of children's memory performance.

Pedagogical judgments must be made by reviewing each actual card. This check
only ensures the recorded judgments cover the current text, without stale rows.
"""

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
total = 0
for grade in (3, 4, 5):
    pack = json.loads((ROOT / f"mnemonics/grade{grade}.json").read_text())
    audit = json.loads((ROOT / f"mnemonics/audit-grade{grade}.json").read_text())
    key = lambda item: (item["section"], item["word"])
    assert Counter(map(key, audit["cards"])) == Counter(map(key, pack["cards"])), \
        f"Grade {grade}: missing or duplicate card audits"
    cards = {key(card): card for card in pack["cards"]}
    for row in audit["cards"]:
        card = cards[key(row)]
        assert row["status"] == "pass", (key(row), row["status"])
        assert isinstance(row["changed"], bool), key(row)
        for field in ("recognitionCue", "spellingCue", "recallTask", "rationale"):
            assert isinstance(row.get(field), str) and row[field].strip(), (key(row), field)
        actual_hash = hashlib.sha256(card["hint"].encode("utf-8")).hexdigest()
        assert row["hintSha256"] == actual_hash, f"Stale review: {key(row)}"
        content = row["contentReview"]
        assert content["reviewScope"] == ["hint", "visual", "semantic", "context", "morphology"], key(row)
        assert content["decision"] in {"revised", "retained"}, key(row)
        digest = hashlib.sha256(json.dumps(card, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        assert content["cardSha256"] == digest, f"Stale whole-card content review: {key(row)}"
        assert content["primaryEvidence"] in card["hint"], f"Spelling evidence absent: {key(row)}"
        assert content["contextEvidence"] == card["dimensions"]["context"]["question"], key(row)
        if card.get("spellingCue"):
            assert card["spellingCue"] == row["spellingCue"], f"Stale spelling cue: {key(row)}"
            assert card["spellingCue"] in card["hint"], f"Spelling cue absent from reviewed hint: {key(row)}"
        if card.get("spellingImage"):
            assert card["spellingImage"] in card["hint"], f"Spelling image absent from reviewed hint: {key(row)}"
    assert Counter(row["section"] for row in audit["stories"]) == \
        Counter(story["section"] for story in pack["stories"]), f"Grade {grade}: story audit missing"
    stories = {story["section"]: story for story in pack["stories"]}
    for row in audit["stories"]:
        assert row["status"] == "pass" and isinstance(row["changed"], bool), row["section"]
        assert isinstance(row.get("rationale"), str) and row["rationale"].strip(), row["section"]
        actual_hash = hashlib.sha256(json.dumps(stories[row["section"]], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        assert row["storySha256"] == actual_hash, f"Stale story review: {row['section']}"
    total += len(cards)
print(f"Traceability verified for {total} card reviews and 36 story reviews; effectiveness is not measured by this check.")
