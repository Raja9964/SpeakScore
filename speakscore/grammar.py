import re
from dataclasses import dataclass

from .text import Document, words_in

RUN_ON_WORDS = 40
MIN_FRAGMENT_WORDS = 5

_FLAGS = re.IGNORECASE
_PATTERN_RULES = [
    (
        "double comparative",
        re.compile(
            r"\b(?:more|most) (?:better|best|worse|worst|bigger|biggest|easier|easiest|"
            r"harder|hardest|happier|happiest|smaller|faster|larger|stronger)\b",
            _FLAGS,
        ),
    ),
    ("'of' instead of 'have'", re.compile(r"\b(?:could|should|would|must|might) of\b", _FLAGS)),
    ("'alot' should be 'a lot'", re.compile(r"\balot\b", _FLAGS)),
    (
        "progressive 'having' for possession",
        re.compile(
            r"(?:\bam|\bis|\bare|'m|'re|'s) having (?:a|an|one|two|three|four|five|\d+) "
            r"(?:brothers?|sisters?|siblings?|members?|kids|children|pets?|dogs?|cats?)\b",
            _FLAGS,
        ),
    ),
]

_REPEATED_RE = re.compile(r"\b(\w+)\s+\1\b", _FLAGS)
_ALLOWED_REPEATS = {"that", "had", "bye"}
_ARTICLE_RE = re.compile(r"\b(a|an)\s+([A-Za-z]+)", _FLAGS)
_SOFT_VOWEL_START = ("uni", "use", "usu", "uti", "eu", "one", "once", "ure")
_SILENT_H_START = ("hour", "honest", "honor", "honour", "heir")
_AGREEMENT_RE = re.compile(
    r"(?:\b(\w+)\s+)?\b(i|he|she|it|we|they|you)\s+(is|are|was|has|have|do|does|don't|doesn't)\b",
    _FLAGS,
)
_BAD_AGREEMENT = {
    "i": {"is", "are", "has", "does", "doesn't"},
    "he": {"are", "have", "do", "don't"},
    "she": {"are", "have", "do", "don't"},
    "it": {"are", "have", "do", "don't"},
    "we": {"is", "was", "has", "does", "doesn't"},
    "they": {"is", "was", "has", "does", "doesn't"},
    "you": {"is", "was", "has", "does", "doesn't"},
}
# Words that legitimately precede "he have", "does she do", "let them do" and similar.
_AGREEMENT_EXEMPT = {
    "does", "did", "do", "will", "would", "can", "could", "should", "shall", "may", "might",
    "must", "let", "make", "made", "help", "helps", "watch", "see", "saw", "hear", "heard",
    "thank", "thanks", "if", "what", "how", "where", "when", "why", "who",
}  # fmt: skip
_LOWER_I_RE = re.compile(r"(?<![\w'.])i(?=\s|'|[,;:!?]|$)")
_VERB_HINTS = {
    "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "can", "could", "will", "would", "shall", "should", "may", "might", "must", "i", "we",
    "he", "she", "they", "thank", "thanks", "like", "love", "enjoy", "want", "live", "study",
    "work", "play", "go", "went", "hope", "plan", "believe", "think", "feel", "make", "made",
    "spend", "spent", "learn", "learned", "learnt", "became", "become", "started", "joined",
    "moved", "call", "called", "born", "grew", "raised", "help", "helps", "keep", "keeps",
}  # fmt: skip


@dataclass(frozen=True)
class Issue:
    rule: str
    excerpt: str


def find_issues(doc: Document) -> list[Issue]:
    text = doc.text
    issues: list[Issue] = []

    for rule, pattern in _PATTERN_RULES:
        issues += [Issue(rule, m.group()) for m in pattern.finditer(text)]

    for m in _REPEATED_RE.finditer(text):
        if m.group(1).lower() not in _ALLOWED_REPEATS:
            issues.append(Issue("repeated word", m.group()))

    for m in _ARTICLE_RE.finditer(text):
        article, word = m.group(1).lower(), m.group(2)
        lower = word.lower()
        if word.isupper() and len(word) > 1:
            continue  # acronyms like "an MBA" depend on pronunciation
        starts_with_vowel = lower[0] in "aeiou" and not lower.startswith(_SOFT_VOWEL_START)
        if (article == "a" and starts_with_vowel) or (
            article == "an" and not starts_with_vowel and not lower.startswith(_SILENT_H_START)
        ):
            issues.append(Issue(f"use '{'an' if article == 'a' else 'a'}' here", m.group()))

    for m in _AGREEMENT_RE.finditer(text):
        before, subject, verb = (g.lower() if g else "" for g in m.groups())
        if verb in _BAD_AGREEMENT[subject] and before not in _AGREEMENT_EXEMPT:
            issues.append(Issue("subject-verb agreement", f"{subject} {verb}"))

    if any(c.isupper() for c in text):
        # Only judge capitalisation when the transcript uses capitals at all.
        issues += [Issue("lowercase 'i'", "i") for _ in _LOWER_I_RE.finditer(text)]
        for sentence in doc.sentences:
            first = next((c for c in sentence if c.isalpha()), "")
            if first.islower():
                issues.append(Issue("sentence starts lowercase", _clip(sentence)))

    last = len(doc.sentences) - 1
    for i, sentence in enumerate(doc.sentences):
        words = words_in(sentence)
        if len(words) > RUN_ON_WORDS:
            issues.append(Issue("run-on sentence", _clip(sentence)))
        elif (
            0 < i < last
            and len(words) >= MIN_FRAGMENT_WORDS
            and not any(w in _VERB_HINTS or "'" in w for w in words)
        ):
            issues.append(Issue("sentence without a verb", _clip(sentence)))

    return issues


def _clip(sentence: str, n_words: int = 6) -> str:
    parts = sentence.split()
    return " ".join(parts[:n_words]) + (" ..." if len(parts) > n_words else "")
