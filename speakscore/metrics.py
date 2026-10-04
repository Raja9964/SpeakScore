import re
from collections import Counter
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from . import grammar as grammar_rules
from .rubric import Salutation, Section
from .text import Document, mattr

ZONE_WORDS = 30
MIN_SECTIONS_FOR_ORDER = 3
VOCAB_WINDOW = 50


@dataclass(frozen=True)
class Measurement:
    value: float | None
    metrics: dict[str, Any] = field(default_factory=dict)
    note: str | None = None


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    body = r"\s+".join(re.escape(part) for part in phrase.split())
    return re.compile(rf"(?<![\w']){body}(?![\w'])", re.IGNORECASE)


@cache
def _compiled(phrases: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(_phrase_pattern(p) for p in phrases)


@cache
def _analyzer() -> SentimentIntensityAnalyzer:
    return SentimentIntensityAnalyzer()


def salutation(doc: Document, levels: tuple[Salutation, ...]) -> Measurement:
    opening = doc.text[: doc.head_end(ZONE_WORDS)]
    best: tuple[Salutation, str] | None = None
    for level in sorted(levels, key=lambda lv: lv.level, reverse=True):
        for pattern in _compiled(level.phrases):
            if m := pattern.search(opening):
                best = (level, m.group().lower())
                break
        if best:
            break
    if best is None:
        return Measurement(0, {"level": 0, "style": "None", "matched": None})
    level, matched = best
    return Measurement(
        level.level, {"level": level.level, "style": level.label, "matched": matched}
    )


def find_sections(doc: Document, sections: tuple[Section, ...]) -> dict[str, int]:
    """Map each detected section id to the offset of its first mention."""
    bounds = {
        "any": (0, len(doc.text)),
        "opening": (0, doc.head_end(ZONE_WORDS)),
        "closing": (doc.tail_start(ZONE_WORDS), len(doc.text)),
    }
    found = {}
    for section in sections:
        start, end = bounds[section.zone]
        hits = [m.start() for p in section.patterns if (m := p.search(doc.text, start, end))]
        if hits:
            found[section.id] = min(hits)
    return found


def coverage(doc: Document, sections: tuple[Section, ...]) -> Measurement:
    found = find_sections(doc, sections)
    total = sum(s.points for s in sections)
    earned = sum(s.points for s in sections if s.id in found)
    return Measurement(
        earned / total,
        {
            "coverage": round(earned / total, 3),
            "found": [s.label for s in sections if s.id in found],
            "missing": [s.label for s in sections if s.id not in found],
        },
    )


def section_order(doc: Document, sections: tuple[Section, ...]) -> Measurement:
    found = find_sections(doc, sections)
    expected = {s.id: i for i, s in enumerate(sections)}
    spoken = sorted(found, key=found.get)
    kept = _longest_increasing([expected[sid] for sid in spoken])
    labels = {s.id: s.label for s in sections}
    out_of_order = [labels[sid] for i, sid in enumerate(spoken) if i not in kept]
    metrics = {"sections_found": len(spoken), "in_order": len(kept), "out_of_order": out_of_order}
    if len(spoken) < MIN_SECTIONS_FOR_ORDER:
        return Measurement(0.0, metrics)
    return Measurement(len(kept) / len(spoken), metrics)


def _longest_increasing(seq: list[int]) -> set[int]:
    # O(n^2) is plenty for a handful of sections; returns the kept positions.
    if not seq:
        return set()
    best = [1] * len(seq)
    prev = [-1] * len(seq)
    for i in range(len(seq)):
        for j in range(i):
            if seq[j] < seq[i] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    i = max(range(len(seq)), key=best.__getitem__)
    kept = set()
    while i != -1:
        kept.add(i)
        i = prev[i]
    return kept


def speech_rate(doc: Document) -> Measurement:
    if not doc.duration_seconds:
        return Measurement(
            None,
            {"wpm": None, "words": doc.word_count, "duration_seconds": None},
            note="Add the recording length (duration_seconds) to score speaking pace.",
        )
    wpm = doc.word_count / (doc.duration_seconds / 60)
    return Measurement(
        wpm,
        {"wpm": round(wpm), "words": doc.word_count, "duration_seconds": doc.duration_seconds},
    )


def grammar(doc: Document) -> Measurement:
    issues = grammar_rules.find_issues(doc)
    rate = 100 * len(issues) / max(doc.word_count, 1)
    return Measurement(
        rate,
        {
            "issues": len(issues),
            "per_100_words": round(rate, 2),
            "examples": [f'"{i.excerpt}" ({i.rule})' for i in issues[:3]],
        },
    )


def vocabulary(doc: Document) -> Measurement:
    score = mattr(doc.words, VOCAB_WINDOW)
    unique = len(set(doc.words))
    return Measurement(
        score,
        {
            "mattr": round(score, 3),
            "ttr": round(unique / max(doc.word_count, 1), 3),
            "unique_words": unique,
        },
    )


def fillers(doc: Document, phrases: tuple[str, ...]) -> Measurement:
    counts = Counter()
    for phrase, pattern in zip(phrases, _compiled(phrases), strict=True):
        if n := len(pattern.findall(doc.text)):
            counts[phrase.rstrip(",")] += n
    total = sum(counts.values())
    rate = 100 * total / max(doc.word_count, 1)
    return Measurement(
        rate,
        {
            "fillers": total,
            "per_100_words": round(rate, 2),
            "found": [f"{w} x{n}" for w, n in counts.most_common()],
        },
    )


def sentiment(doc: Document) -> Measurement:
    scores = _analyzer().polarity_scores(doc.text)
    return Measurement(
        scores["compound"],
        {
            "compound": round(scores["compound"], 3),
            "positive": round(scores["pos"], 3),
            "neutral": round(scores["neu"], 3),
            "negative": round(scores["neg"], 3),
        },
    )
