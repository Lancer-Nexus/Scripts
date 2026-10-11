#!/usr/bin/env python3
"""Collect read-only source-reference evidence for unlisted Freelancer goods."""

import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path


TEXT_SUFFIXES = {".ini", ".thn", ".lua", ".txt"}
WORD_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_")


class AhoCorasick:
    """Small case-insensitive multi-pattern matcher for exact good nicknames."""

    def __init__(self, patterns):
        self.transitions = [{}]
        self.failures = [0]
        self.outputs = [[]]
        for pattern in patterns:
            state = 0
            for char in pattern.lower():
                next_state = self.transitions[state].get(char)
                if next_state is None:
                    next_state = len(self.transitions)
                    self.transitions[state][char] = next_state
                    self.transitions.append({})
                    self.failures.append(0)
                    self.outputs.append([])
                state = next_state
            self.outputs[state].append(pattern)

        pending = deque()
        for state in self.transitions[0].values():
            pending.append(state)
        while pending:
            state = pending.popleft()
            for char, next_state in self.transitions[state].items():
                pending.append(next_state)
                fallback = self.failures[state]
                while fallback and char not in self.transitions[fallback]:
                    fallback = self.failures[fallback]
                self.failures[next_state] = self.transitions[fallback].get(char, 0)
                self.outputs[next_state].extend(self.outputs[self.failures[next_state]])

    def find(self, text):
        state = 0
        lowered = text.lower()
        for index, char in enumerate(lowered):
            while state and char not in self.transitions[state]:
                state = self.failures[state]
            state = self.transitions[state].get(char, 0)
            for pattern in self.outputs[state]:
                start = index - len(pattern) + 1
                end = index + 1
                if ((start == 0 or lowered[start - 1] not in WORD_CHARS) and
                        (end == len(lowered) or lowered[end] not in WORD_CHARS)):
                    yield pattern


def build_usage_report(review_bytes, data_root):
    review = json.loads(review_bytes)
    if review.get("schemaVersion") != 1 or not isinstance(review.get("goods"), list):
        raise ValueError("Unsupported or malformed unlisted-goods review document")
    rows = review["goods"]
    good_ids = [row.get("goodId") if isinstance(row, dict) else None for row in rows]
    if any(not isinstance(good_id, str) or not good_id for good_id in good_ids):
        raise ValueError("Review contains an invalid goodId")
    normalized_ids = [good_id.lower() for good_id in good_ids]
    if len(set(normalized_ids)) != len(normalized_ids):
        raise ValueError("Review contains duplicate goodId values")

    data_root = data_root.resolve(strict=True)
    if not data_root.is_dir():
        raise ValueError("Freelancer DATA path is not a directory")
    matcher = AhoCorasick(good_ids)
    references = {
        good_id: {"externalReferenceCount": 0, "externalReferenceFileCount": 0, "assetGroupCounts": {}}
        for good_id in good_ids
    }
    inventory_hash = hashlib.sha256()
    scanned_files = 0

    paths = sorted(path for path in data_root.rglob("*")
                   if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES)
    for path in paths:
        relative = path.relative_to(data_root).as_posix()
        raw = path.read_bytes()
        inventory_hash.update(relative.encode("utf-8"))
        inventory_hash.update(b"\0")
        inventory_hash.update(raw)
        inventory_hash.update(b"\0")
        scanned_files += 1
        text = raw.decode("utf-8-sig", errors="replace")
        matches = Counter(matcher.find(text))
        if not matches:
            continue
        first_group = Path(relative).parts[0].lower() if Path(relative).parts else "root"
        # The Good definitions themselves are inventory, not evidence of use.
        if first_group == "equipment":
            continue
        for good_id, count in matches.items():
            evidence = references[good_id]
            evidence["externalReferenceCount"] += count
            evidence["externalReferenceFileCount"] += 1
            groups = evidence["assetGroupCounts"]
            groups[first_group] = groups.get(first_group, 0) + count

    goods = []
    totals = Counter()
    for row in sorted(rows, key=lambda item: item["goodId"]):
        evidence = references[row["goodId"]]
        evidence["assetGroupCounts"] = dict(sorted(evidence["assetGroupCounts"].items()))
        totals["goods"] += 1
        totals["withExternalReferences"] += evidence["externalReferenceFileCount"] > 0
        totals["withoutExternalReferences"] += evidence["externalReferenceFileCount"] == 0
        goods.append({
            "goodId": row["goodId"],
            "reviewClass": row.get("reviewClass", "manual_classification_required"),
            **evidence,
        })

    return {
        "schemaVersion": 1,
        "reviewDocumentSha256": hashlib.sha256(review_bytes).hexdigest(),
        "sourceDataSha256": inventory_hash.hexdigest(),
        "sourceTextFileCount": scanned_files,
        "referenceScope": "exact whole-goodId references outside EQUIPMENT definitions in INI/THN/LUA/TXT files; reference evidence is not market authorization",
        "totals": dict(totals),
        "goods": goods,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path, help="review JSON generated by review-unlisted-market-goods.py")
    parser.add_argument("--data-dir", type=Path, required=True, help="Freelancer DATA directory; read only")
    parser.add_argument("--output", type=Path, required=True, help="usage evidence JSON output path")
    args = parser.parse_args()
    report = build_usage_report(args.review.read_bytes(), args.data_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote usage evidence for {report['totals']['goods']} goods; this does not enable market offers.")


if __name__ == "__main__":
    main()
