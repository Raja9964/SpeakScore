import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_RUBRIC_PATH = Path(__file__).resolve().parent / "rubric.json"
ZONES = ("any", "opening", "closing")


class RubricError(ValueError):
    pass


@dataclass(frozen=True)
class Band:
    feedback: str
    min: float | None = None
    max: float | None = None
    score: float | None = None

    def contains(self, value: float) -> bool:
        return (self.min is None or value >= self.min) and (self.max is None or value < self.max)


@dataclass(frozen=True)
class Check:
    id: str
    label: str
    metric: str
    points: float
    bands: tuple[Band, ...]
    linear: tuple[float, float] | None = None

    def band_for(self, value: float) -> Band:
        # The loader guarantees the last band is a catch-all.
        return next(b for b in self.bands if b.contains(value))

    def fraction(self, value: float) -> float:
        if self.linear is not None:
            lo, hi = self.linear
            return min(max((value - lo) / (hi - lo), 0.0), 1.0)
        return self.band_for(value).score


@dataclass(frozen=True)
class Criterion:
    id: str
    name: str
    weight: float
    checks: tuple[Check, ...]


@dataclass(frozen=True)
class Section:
    id: str
    label: str
    points: float
    patterns: tuple[re.Pattern[str], ...]
    zone: str = "any"


@dataclass(frozen=True)
class Salutation:
    level: int
    label: str
    phrases: tuple[str, ...]


@dataclass(frozen=True)
class Grade:
    min: float
    grade: str
    label: str


@dataclass(frozen=True)
class Reliability:
    min_words: int
    min_function_word_ratio: float
    min_lexical_diversity: float


@dataclass(frozen=True)
class Rubric:
    name: str
    version: str
    criteria: tuple[Criterion, ...]
    sections: tuple[Section, ...]
    salutations: tuple[Salutation, ...]
    fillers: tuple[str, ...]
    grades: tuple[Grade, ...]
    reliability: Reliability

    @property
    def total_weight(self) -> float:
        return sum(c.weight for c in self.criteria)

    def grade_for(self, score: float) -> Grade:
        return next(g for g in self.grades if score >= g.min)


def load_rubric(path: str | Path | None = None) -> Rubric:
    path = Path(path) if path else DEFAULT_RUBRIC_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RubricError(f"Cannot read rubric file {path}: {exc.strerror or exc}") from exc
    except json.JSONDecodeError as exc:
        raise RubricError(f"Rubric file {path} is not valid JSON: {exc}") from exc
    return parse_rubric(data)


def parse_rubric(data: Any) -> Rubric:
    _expect(isinstance(data, dict), "rubric must be a JSON object")
    criteria = tuple(
        _criterion(c, f"criteria[{i}]") for i, c in enumerate(_items(data, "criteria", "rubric"))
    )
    _unique((c.id for c in criteria), "criterion")
    total = sum(c.weight for c in criteria)
    _expect(math.isclose(total, 100), f"criterion weights must add up to 100, got {total:g}")

    sections = tuple(
        _section(s, f"sections[{i}]") for i, s in enumerate(_items(data, "sections", "rubric"))
    )
    _unique((s.id for s in sections), "section")

    salutations = tuple(
        _salutation(s, f"salutations[{i}]")
        for i, s in enumerate(_items(data, "salutations", "rubric"))
    )
    fillers = tuple(_strings(data, "fillers", "rubric"))

    grades = tuple(
        _grade(g, f"grades[{i}]") for i, g in enumerate(_items(data, "grades", "rubric"))
    )
    mins = [g.min for g in grades]
    _expect(mins == sorted(mins, reverse=True), "grades must be ordered from highest to lowest")
    _expect(mins[-1] == 0, "the last grade must start at 0")

    return Rubric(
        name=_field(data, "name", str, "rubric"),
        version=_field(data, "version", str, "rubric"),
        criteria=criteria,
        sections=sections,
        salutations=salutations,
        fillers=fillers,
        grades=grades,
        reliability=_reliability(_field(data, "reliability", dict, "rubric"), "reliability"),
    )


def _criterion(data: Any, where: str) -> Criterion:
    _expect(isinstance(data, dict), f"{where} must be an object")
    cid = _field(data, "id", str, where)
    where = f"criterion '{cid}'"
    weight = _positive(data, "weight", where)
    checks = tuple(
        _check(c, f"{where} checks[{i}]") for i, c in enumerate(_items(data, "checks", where))
    )
    _unique((c.id for c in checks), f"check in {where}")
    points = sum(c.points for c in checks)
    _expect(
        math.isclose(points, weight),
        f"{where}: check points add up to {points:g}, expected its weight of {weight:g}",
    )
    return Criterion(cid, _field(data, "name", str, where), weight, checks)


def _check(data: Any, where: str) -> Check:
    _expect(isinstance(data, dict), f"{where} must be an object")
    cid = _field(data, "id", str, where)
    where = f"check '{cid}'"
    linear = data.get("linear")
    if linear is not None:
        _expect(
            isinstance(linear, list) and len(linear) == 2 and all(_is_number(v) for v in linear),
            f"{where}: 'linear' must be a pair of numbers",
        )
        _expect(linear[0] != linear[1], f"{where}: 'linear' bounds must differ")
        linear = (float(linear[0]), float(linear[1]))

    bands = tuple(
        _band(b, f"{where} bands[{i}]", needs_score=linear is None)
        for i, b in enumerate(_items(data, "bands", where))
    )
    last = bands[-1]
    _expect(
        last.min is None and last.max is None,
        f"{where}: the last band must be a catch-all with no 'min' or 'max'",
    )
    return Check(
        id=cid,
        label=_field(data, "label", str, where),
        metric=_field(data, "metric", str, where),
        points=_positive(data, "points", where),
        bands=bands,
        linear=linear,
    )


def _band(data: Any, where: str, *, needs_score: bool) -> Band:
    _expect(isinstance(data, dict), f"{where} must be an object")
    low = _field(data, "min", float, where, None)
    high = _field(data, "max", float, where, None)
    if low is not None and high is not None:
        _expect(low < high, f"{where}: 'min' must be below 'max'")
    score = _field(data, "score", float, where, None)
    if needs_score:
        _expect(score is not None, f"{where}: 'score' is required unless the check is linear")
    if score is not None:
        _expect(0 <= score <= 1, f"{where}: 'score' must be between 0 and 1")
    return Band(_field(data, "feedback", str, where), low, high, score)


def _section(data: Any, where: str) -> Section:
    _expect(isinstance(data, dict), f"{where} must be an object")
    sid = _field(data, "id", str, where)
    where = f"section '{sid}'"
    zone = _field(data, "zone", str, where, "any")
    _expect(zone in ZONES, f"{where}: 'zone' must be one of {', '.join(ZONES)}")
    patterns = []
    for pattern in _strings(data, "patterns", where):
        try:
            patterns.append(re.compile(pattern, re.IGNORECASE))
        except re.error as exc:
            raise RubricError(f"{where}: invalid pattern {pattern!r}: {exc}") from exc
    return Section(
        sid,
        _field(data, "label", str, where),
        _positive(data, "points", where),
        tuple(patterns),
        zone,
    )


def _salutation(data: Any, where: str) -> Salutation:
    _expect(isinstance(data, dict), f"{where} must be an object")
    level = _field(data, "level", int, where)
    _expect(level >= 1, f"{where}: 'level' must be 1 or higher")
    return Salutation(
        level, _field(data, "label", str, where), tuple(_strings(data, "phrases", where))
    )


def _grade(data: Any, where: str) -> Grade:
    _expect(isinstance(data, dict), f"{where} must be an object")
    return Grade(
        _field(data, "min", float, where),
        _field(data, "grade", str, where),
        _field(data, "label", str, where),
    )


def _reliability(data: dict, where: str) -> Reliability:
    min_words = _field(data, "min_words", int, where)
    _expect(min_words >= 1, f"{where}: 'min_words' must be at least 1")
    ratios = {}
    for key in ("min_function_word_ratio", "min_lexical_diversity"):
        ratios[key] = _field(data, key, float, where)
        _expect(0 < ratios[key] <= 1, f"{where}: '{key}' must be between 0 and 1")
    return Reliability(min_words, **ratios)


_MISSING = object()
_TYPE_NAMES = {str: "a string", int: "an integer", float: "a number", dict: "an object"}


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _field(data: dict, key: str, kind: Any, where: str, default: Any = _MISSING) -> Any:
    if key not in data:
        if default is _MISSING:
            raise RubricError(f"{where}: missing '{key}'")
        return default
    value = data[key]
    if kind is float:
        valid = _is_number(value)
    elif kind is int:
        valid = isinstance(value, int) and not isinstance(value, bool)
    else:
        valid = isinstance(value, kind)
    if not valid:
        raise RubricError(f"{where}: '{key}' must be {_TYPE_NAMES.get(kind, 'valid')}")
    return float(value) if kind is float else value


def _positive(data: dict, key: str, where: str) -> float:
    value = _field(data, key, float, where)
    _expect(value > 0, f"{where}: '{key}' must be greater than 0")
    return value


def _items(data: dict, key: str, where: str) -> list:
    value = data.get(key)
    _expect(isinstance(value, list) and value, f"{where}: '{key}' must be a non-empty list")
    return value


def _strings(data: dict, key: str, where: str) -> list[str]:
    values = _items(data, key, where)
    _expect(
        all(isinstance(v, str) and v.strip() for v in values),
        f"{where}: '{key}' must only contain non-empty strings",
    )
    return values


def _unique(ids: Any, kind: str) -> None:
    seen: set[str] = set()
    for item in ids:
        _expect(item not in seen, f"duplicate {kind} id '{item}'")
        seen.add(item)


def _expect(condition: Any, message: str) -> None:
    if not condition:
        raise RubricError(message)
