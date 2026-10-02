"""Check coverage and content contracts, not children's learning outcomes."""

import hashlib
import json
import re
import argparse
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KINDS = {"none", "affix", "compound", "inflection", "phrase"}
PANEL_KINDS = {"combine", "compare", "change", "sequence", "parts"}
GRAPHIC_KINDS = PANEL_KINDS | {"position", "count", "colour", "body", "clock", "family", "measure", "reference", "deixis", "motion", "frequency", "timeline", "selection", "shape", "category", "partition", "feature"}
SPECIAL_GRAPHICS = {"in", "on", "under", "behind", "next to", "sorry", "would", "dessert", "meatball"}
BODY_PARTS = {
    "person": {"arm", "leg", "ear", "eye", "nose", "mouth", "hand", "foot", "neck", "hair", "face"},
    "bird": {"wing", "tail", "leg", "foot", "eye", "neck"},
    "cat": {"tail", "ear", "eye", "nose", "mouth", "leg", "foot", "neck", "face"},
    "plant": {"root", "stem", "leaf", "seed", "pod"},
}
counts = Counter()
graphics = Counter()
grade_graphics = {}
pending = []
retrieval_targets = Counter()
cards = {}
for grade in (3, 4, 5):
    pack = json.loads((ROOT / f"mnemonics/grade{grade}.json").read_text())
    audit = json.loads((ROOT / f"mnemonics/audit-grade{grade}.json").read_text())
    reviews = {(row["section"], row["word"]): row for row in audit["cards"]}
    grade_graphics[grade] = {"total": len(pack["cards"]), "illustrated": 0}
    for card in pack["cards"]:
        key = card["section"], card["word"]
        cards[key] = card
        dimensions = card.get("dimensions")
        assert isinstance(dimensions, dict), (key, "Missing dimensions")
        visual = dimensions["visual"]
        assert 1 <= len(visual["symbols"]) <= 3, key
        assert all(isinstance(symbol, str) and symbol.strip() for symbol in visual["symbols"]), key
        assert isinstance(visual["caption"], str) and visual["caption"].strip(), key
        assert isinstance(visual["focus"], list) and len(visual["focus"]) <= 3, key
        assert all(isinstance(cue, str) and cue.strip() and cue in card["word"] for cue in visual["focus"]), key
        if "diagram" in visual:
            diagram = visual["diagram"]
            kind = diagram["kind"]
            assert kind in GRAPHIC_KINDS, key
            if kind in PANEL_KINDS:
                assert 2 <= len(diagram["panels"]) <= 4, key
                if kind in {"compare", "change", "combine"}:
                    assert len(diagram["panels"]) == (3 if kind == "combine" else 2), key
                if kind == "combine":
                    assert diagram["panels"][-1]["label"] == card["word"], key
                if kind == "parts":
                    assert diagram["result"] == card["word"], key
            elif kind == "reference":
                assert diagram['relation'] in {'action', 'ownership', 'reflexive'}, key
                assert diagram['focus'] in {'left', 'right', 'both'}, key
                for side in ('left', 'right'):
                    assert all(isinstance(diagram[side][field], str) and diagram[side][field].strip() for field in ('symbol', 'label')), key
                    assert len(diagram[side]['label']) <= 8, key
                sentence = diagram['sentence']
                assert sentence['word'].lower() == card['word'].lower(), key
                assert all(isinstance(sentence[field], str) for field in ('before', 'word', 'after')), key
                assert diagram['link'].strip() and len(diagram['link']) <= 8, key
            elif kind == "deixis":
                assert diagram['distance'] in {'near', 'far'}, key
                assert type(diagram['plural']) is bool, key
                assert card['word'] in {'this', 'that', 'these', 'those'}, key
            elif kind == "motion":
                assert diagram['direction'] in {'in', 'out', 'toward', 'away', 'up', 'down', 'left', 'right', 'push', 'pull'}, key
                assert all(isinstance(diagram[field], str) and diagram[field].strip() for field in ('object', 'startLabel', 'endLabel')), key
                assert all(len(diagram[field]) <= 8 for field in ('startLabel', 'endLabel')), key
                assert diagram.get('focusEndpoint') in (None, 'start', 'end'), key
                assert type(diagram.get('returning', False)) is bool, key
            elif kind in {'frequency', 'selection'}:
                assert type(diagram['total']) is int and 1 <= diagram['total'] <= 10, key
                values = diagram['hits' if kind == 'frequency' else 'selected']
                assert len(set(values)) == len(values), key
                assert all(type(value) is int and 0 <= value < diagram['total'] for value in values), key
                if kind == 'selection':
                    assert type(diagram.get('individual', False)) is bool, key
                    if 'comparison' in diagram:
                        assert type(diagram['comparison']) is int and 0 <= diagram['comparison'] < len(values), key
            elif kind == 'timeline':
                assert 2 <= len(diagram['points']) <= 5, key
                assert any(point['active'] for point in diagram['points']), key
                for point in diagram['points']:
                    assert type(point['active']) is bool and point['label'].strip() and point['meaning'].strip(), key
            elif kind == 'shape':
                assert diagram['focus'] in {'circle', 'square', 'triangle', 'all'}, key
            elif kind == 'category':
                assert 2 <= len(diagram['items']) <= 4, key
                assert all(all(isinstance(item[field], str) and item[field].strip() for field in ('symbol', 'label', 'meaning')) for item in diagram['items']), key
            elif kind == 'partition':
                assert type(diagram['pieces']) is int and 2 <= diagram['pieces'] <= 8, key
                assert type(diagram['separated']) is bool, key
                assert len(set(diagram['selected'])) == len(diagram['selected']), key
                assert all(type(index) is int and 0 <= index < diagram['pieces'] for index in diagram['selected']), key
            elif kind == 'feature':
                assert diagram['scene'] in {'kite', 'rope', 'room', 'door-window', 'lake-river', 'stair', 'plant-flow', 'protection', 'wind', 'balance', 'sort', 'plaza'}, key
                if diagram['scene'] == 'room':
                    assert diagram['focus'] in {'school', 'room', 'class'}, key
                if diagram['scene'] == 'door-window':
                    assert diagram['focus'] in {'door', 'window'}, key
            elif kind == "position":
                assert diagram["relation"] in {"inside", "surface", "below", "above", "behind", "front", "beside", "between", "near", "far", "outside", "around", "middle"}, key
                assert all(isinstance(diagram[field], str) and diagram[field].strip() for field in ("object", "reference")), key
            elif kind == "count":
                assert type(diagram["value"]) is int and 1 <= diagram["value"] <= 100, key
                assert type(diagram.get("ordinal", False)) is bool, key
            elif kind == "family":
                assert diagram["role"] in {"mum", "dad", "parent", "brother", "sister", "uncle", "aunt", "cousin", "grandpa", "grandma", "family"}, key
            elif kind == "measure":
                assert diagram["dimension"] in {"length", "height", "size", "thickness"}, key
                assert len(diagram["labels"]) == 2, key
                for label in diagram["labels"]:
                    assert isinstance(label["value"], (int, float)) and label["value"] > 0, key
                    assert label["label"].strip() and label["meaning"].strip(), key
            elif kind == "body":
                assert diagram["figure"] in BODY_PARTS and diagram["part"] in BODY_PARTS[diagram["figure"]], key
            elif kind == "clock":
                assert type(diagram["hour"]) is int and 0 <= diagram["hour"] <= 23, key
                assert type(diagram["minute"]) is int and 0 <= diagram["minute"] <= 59, key
                assert diagram["focus"] in {"time", "hour", "minute"}, key
            elif kind == "colour":
                assert 1 <= len(diagram["swatches"]) <= 7, key
                if diagram.get("mix"):
                    assert len(diagram["swatches"]) == 3, key
                for swatch in diagram["swatches"]:
                    assert re.fullmatch(r"#[0-9a-fA-F]{6}", swatch["colour"]), key
                    assert swatch["label"].strip() and swatch["meaning"].strip(), key
            for panel in diagram.get("panels", []):
                assert 1 <= len(panel["symbols"]) <= 3, key
                assert all(isinstance(symbol, str) and symbol.strip() for symbol in panel["symbols"]), key
                assert all(isinstance(panel[field], str) and panel[field].strip() for field in ("label", "meaning")), key
                assert all(cue and cue in panel["label"] for cue in panel.get("focus", [])), key
                if "focusSuffix" in panel:
                    assert panel["focusSuffix"] and panel["label"].endswith(panel["focusSuffix"]), key
                    assert not panel.get("focus"), key
                assert panel.get("tag") in (None, "本课词义", "另一词义"), key
        assert isinstance(dimensions["semantic"], str) and dimensions["semantic"].strip(), key
        context = dimensions["context"]
        assert all(isinstance(context.get(field), str) and context[field].strip() for field in ("scene", "question")), key
        assert not re.search(r"[A-Za-z]", context["question"]), (key, "English answer can leak during context recall")
        morphology = dimensions["morphology"]
        assert morphology["kind"] in KINDS, key
        assert isinstance(morphology["parts"], list), key
        assert isinstance(morphology["note"], str) and morphology["note"].strip(), key
        if morphology["kind"] == "none":
            assert not morphology["parts"], (key, "Unanalysed words must not imply roots")
        else:
            assert morphology["parts"], key
            assert all(isinstance(part.get(field), str) and part[field].strip()
                       for part in morphology["parts"] for field in ("text", "meaning")), key
        for field in (visual["caption"], dimensions["semantic"], context["scene"], context["question"], morphology["note"]):
            assert re.search(r"[\u4e00-\u9fff]", field), (key, "Child-facing explanation must include Chinese")
        digest = hashlib.sha256(json.dumps(dimensions, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        review = reviews[key]
        assert review.get("dimensionsSha256") == digest, (key, "Stale dimensions review")
        assert isinstance(review.get("dimensionsRationale"), str) and review["dimensionsRationale"].strip(), key
        graphic_review = review.get("graphicReview")
        assert isinstance(graphic_review, dict), (key, "Every card needs a graphic decision")
        illustrated = "diagram" in visual or card["word"].lower() in SPECIAL_GRAPHICS
        assert graphic_review["status"] == ("illustrated" if illustrated else "cue-only"), (key, "Graphic assessment must match actual rendering")
        assert graphic_review["target"] in {"meaning", "spelling", "both"}, key
        assert isinstance(graphic_review["rationale"], str) and graphic_review["rationale"].strip(), key
        if illustrated:
            graphics[visual["diagram"]["kind"] if "diagram" in visual else "special-svg"] += 1
            grade_graphics[grade]["illustrated"] += 1
            retrieval_targets[graphic_review["target"]] += 1
        else:
            pending.append((grade, card["section"], card["word"], graphic_review["rationale"]))
        counts[morphology["kind"]] += 1

# Regression boundaries: similar letter sequences are not automatically morphemes.
for word in ("uncle", "remember", "welcome"):
    for (section, target), card in cards.items():
        if target == word:
            assert card["dimensions"]["morphology"]["kind"] == "none", (section, word)
for word, focus in (("sorry", "rr"), ("would", "l"), ("dessert", "ss")):
    card = next(card for (_, target), card in cards.items() if target == word)
    assert focus in card["dimensions"]["visual"]["focus"], word
meatball = next(card for (_, word), card in cards.items() if word == "meatball")
assert meatball["dimensions"]["morphology"]["kind"] == "compound"
assert [part["text"] for part in meatball["dimensions"]["morphology"]["parts"]] == ["meat", "ball"]
print(f"Validated multidimensional cues and review hashes for {len(cards)} cards; morphology: {dict(counts)}.")
print("This checks structure, answer hiding contracts and known morphology pitfalls; it does not measure memory effectiveness.")
illustrated = sum(graphics.values())
print(f"Concrete graphics: {illustrated}/{len(cards)} ({illustrated / len(cards):.2%}); cue-only: {len(pending)}. Types: {dict(graphics)}.")

parser = argparse.ArgumentParser()
parser.add_argument("--report", action="store_true", help="Write the verified graphic coverage report")
if parser.parse_args().report:
    type_names = {"special-svg": "专属位置或字形图", "compare": "对象或语义对照", "combine": "真实组成", "change": "形式或状态变化", "sequence": "过程与次序", "parts": "部分与组成", "position": "空间关系", "count": "数量与序数", "colour": "颜色与混色", "body": "身体与植物部位", "clock": "钟面", "family": "亲属关系", "measure": "长度、高度、大小与厚度"}
    type_names.update({'reference': '人物、动作与所属', 'deixis': '指代距离与单复数', 'motion': '起点与移动方向', 'frequency': '发生次数与频率', 'timeline': '时间定位与范围', 'selection': '数量与选择范围', 'shape': '轮廓形状', 'category': '类别与成员', 'partition': '整体与部分', 'feature': '具体结构与作用'})
    target_names = {"meaning": "认词义", "spelling": "记字形", "both": "词义与字形"}
    lines = ["# 具体图解覆盖与剩余词卡", "", "统计日期：2026-10-02。按实际可渲染的图解统计，普通图标及文字描述不计入具体图解。", "",
             f"全部 {len(cards)} 条已记录图解判断；具体图解 **{illustrated} 条（{illustrated / len(cards):.2%}）**，仍仅有图标提示 {len(pending)} 条。", "",
             "| 年级 | 词卡 | 具体图解 | 覆盖率 |", "|---|---:|---:|---:|"]
    for grade, stats in grade_graphics.items():
        lines.append(f"| {grade} 年级 | {stats['total']} | {stats['illustrated']} | {stats['illustrated'] / stats['total']:.2%} |")
    lines += ["", "## 图解类型", "", "| 类型 | 数量 |", "|---|---:|"]
    lines += [f"| {type_names[kind]} | {count} |" for kind, count in sorted(graphics.items())]
    lines += ["", "## 取回目标", "", "图意判断和字形线索属于设计依据，不能作为儿童实际记忆效果证据。", ""]
    lines += [f"- {target_names[target]}：{count} 条" for target, count in sorted(retrieval_targets.items())]
    lines += ["", "## 仍只有图标提示的词", "", "这些词保留声音、语义和情境提示；以下是本轮未采用具体图解的理由，后续可据此继续设计。", "",
              "| 年级 | 单元 | 单词 | 判断理由 |", "|---|---|---|---|"]
    for grade, section, word, rationale in pending:
        lines.append("| " + " | ".join(str(value).replace("|", "／").replace("\n", " ") for value in (grade, section, word, rationale)) + " |")
    (ROOT / "mnemonics/GRAPHIC_COVERAGE.md").write_text("\n".join(lines) + "\n")
