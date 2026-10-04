import re
from dataclasses import dataclass
from functools import cached_property

_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)*")
_SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?])\s+|(?<=[.!?][\"')\]])\s+|\n{2,}")
_TYPOGRAPHIC = str.maketrans(
    {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"}
)

FUNCTION_WORDS = frozenset(
    """
    a an the and or but nor so yet if then than because as while although though since until
    unless whether of in on at to from by with about into onto through after before over under
    between during without within up down out off for near around
    i me my mine myself we us our ours you your yours he him his she her hers it its they them
    their theirs this that these those there here who whom whose which what when where why how
    am is are was were be been being have has had do does did will would shall should can could
    may might must not no very too also just all some any each every both few more most much
    many such own same other another only even still really quite
    i'm i've i'd i'll it's that's there's we're we've they're they've you're you've he's she's
    don't doesn't didn't can't won't isn't aren't wasn't weren't haven't hasn't couldn't
    """.split()
)


def normalize(text: str) -> str:
    text = text.translate(_TYPOGRAPHIC).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    # Single line breaks are usually just wrapping; blank lines separate paragraphs.
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class Document:
    text: str
    tokens: tuple[Token, ...]
    sentences: tuple[str, ...]
    duration_seconds: float | None = None

    @classmethod
    def from_text(cls, text: str, duration_seconds: float | None = None) -> "Document":
        text = normalize(text)
        tokens = tuple(
            Token(m.group().lower(), m.start(), m.end()) for m in _WORD_RE.finditer(text)
        )
        sentences = tuple(s.strip() for s in _SENTENCE_BREAK_RE.split(text) if s.strip())
        return cls(text, tokens, sentences, duration_seconds)

    @cached_property
    def words(self) -> tuple[str, ...]:
        return tuple(t.text for t in self.tokens)

    @property
    def word_count(self) -> int:
        return len(self.tokens)

    def head_end(self, n_words: int) -> int:
        if not self.tokens:
            return 0
        return self.tokens[min(n_words, len(self.tokens)) - 1].end

    def tail_start(self, n_words: int) -> int:
        if not self.tokens:
            return 0
        return self.tokens[-min(n_words, len(self.tokens))].start


def words_in(text: str) -> list[str]:
    return [m.group().lower() for m in _WORD_RE.finditer(text)]


def function_word_ratio(words: tuple[str, ...] | list[str]) -> float:
    if not words:
        return 0.0
    return sum(w in FUNCTION_WORDS for w in words) / len(words)


def mattr(words: tuple[str, ...] | list[str], window: int = 50) -> float:
    # Moving-average TTR, so long transcripts aren't penalised just for being long.
    if not words:
        return 0.0
    if len(words) <= window:
        return len(set(words)) / len(words)

    counts: dict[str, int] = {}
    for w in words[:window]:
        counts[w] = counts.get(w, 0) + 1
    total = len(counts)
    for i in range(window, len(words)):
        out, new = words[i - window], words[i]
        counts[out] -= 1
        if not counts[out]:
            del counts[out]
        counts[new] = counts.get(new, 0) + 1
        total += len(counts)
    return total / ((len(words) - window + 1) * window)
