"""Check that authored mnemonics cover every textbook entry and story word."""

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKS = [ROOT / "mnemonics" / f"grade{grade}.json" for grade in (3, 4, 5, 6)]
METHODS = {"拼读", "构词", "词源", "故事联想", "词组"}


def key(section, word):
    return section, word.strip().casefold()


def story_token(word):
    # Textbook notation indexes entries; stories use real spoken forms.
    aliases = {
        "life (pl. lives)": r"(?:life|lives)",
        "be interested in": r"(?:be|am|is|are|was|were) interested in",
        "take ... lesson": r"(?:take|takes|took) (?:[A-Za-z]+ )+lessons?",
        "save ... from": r"(?:save|saves|saved) people from",
        "keep ... away": r"(?:keep|keeps|kept) children away",
        "vr (= virtual reality)": r"(?:VR \(= Virtual Reality\)|Virtual Reality|VR)",
        "beidou navigation satellite system (abbr. bds)": r"(?:BeiDou Navigation Satellite System(?: \(abbr\. BDS\))?|BDS)",
        "who (world health organization)": r"(?:(?-i:WHO)(?: \(World Health Organization\))?|World Health Organization)",
    }
    return rf"(?<![A-Za-z]){aliases.get(word.casefold(), re.escape(word))}(?![A-Za-z])"


with (ROOT / "词库.md").open(encoding="utf-8-sig", newline="") as source:
    rows = [row for row in csv.DictReader(source)
            if row["section"][:1] in "三四五六" and row["section"][1:2] in "上下"]

expected = {key(row["section"], row["english_word"]) for row in rows}
assert len(rows) == len(expected), "The textbook source has duplicate section/word pairs"
assert len({row['id'] for row in rows}) == len(rows), "Textbook words sharing an ID would disappear from learning and print selection"
expected_by_section = defaultdict(set)
for section, word in expected:
    expected_by_section[section].add(word)

cards = []
stories = []
for path in PACKS:
    pack = json.loads(path.read_text(encoding="utf-8"))
    cards.extend(pack["cards"])
    stories.extend(pack["stories"])

card_keys = [key(card["section"], card["word"]) for card in cards]
assert Counter(card_keys) == Counter(expected), "Cards must cover every textbook entry exactly once"
for card in cards:
    assert card["method"] in METHODS, card
    assert card["hint"].strip() and card["example"].strip(), card
    if card.get("spellingParts"):
        assert "".join(part["text"] for part in card["spellingParts"]) == card["word"], card
        assert any(part["focus"] for part in card["spellingParts"]), card
    assert any("\u4e00" <= char <= "\u9fff" for char in card["example"]), card
    if card["method"] == "词源":
        assert card.get("sourceUrl", "").startswith("https://"), card

assert Counter(story["section"] for story in stories) == Counter(expected_by_section.keys()), \
    "Every textbook unit needs exactly one story"
for story in stories:
    section = story["section"]
    seen = []
    assert story["chapters"], section
    for chapter in story["chapters"]:
        assert chapter["text"].strip() and chapter["words"], section
        assert 4 <= len(chapter["words"]) <= 7, (section, chapter["words"])
        assert len(chapter.get("cues", [])) == len(chapter["words"]), section
        for cue in chapter["cues"]:
            assert isinstance(cue, str) and cue.strip(), (section, cue)
            assert re.search(r"[\u4e00-\u9fff]", cue), (section, cue)
            if chapter.get("cueType") != "spelling":
                assert not re.search(r"[A-Za-z]", cue), (section, cue)
        for word in chapter["words"]:
            token = story_token(word)
            assert re.search(token, chapter["text"], re.IGNORECASE), (section, word)
            seen.append(word.casefold())
    assert Counter(seen) == Counter(expected_by_section[section]), \
        f"Story coverage differs for {section}"

books = {section.split("Unit", 1)[0] for section in expected_by_section}
print(f"Validated {len(cards)} cards and {len(stories)} unit stories across {len(books)} books.")
