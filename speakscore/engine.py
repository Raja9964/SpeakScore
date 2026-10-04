import math
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from functools import cache
from typing import Any

from . import metrics
from .rubric import Check, Criterion, Rubric, RubricError, load_rubric
from .text import Document, function_word_ratio, mattr

MAX_DURATION_SECONDS = 3600

MetricFn = Callable[[Document, Rubric], metrics.Measurement]

METRICS: dict[str, MetricFn] = {
    "salutation": lambda doc, rubric: metrics.salutation(doc, rubric.salutations),
    "coverage": lambda doc, rubric: metrics.coverage(doc, rubric.sections),
    "order": lambda doc, rubric: metrics.section_order(doc, rubric.sections),
    "speech_rate": lambda doc, _: metrics.speech_rate(doc),
    "grammar": lambda doc, _: metrics.grammar(doc),
    "vocabulary": lambda doc, _: metrics.vocabulary(doc),
    "fillers": lambda doc, rubric: metrics.fillers(doc, rubric.fillers),
    "sentiment": lambda doc, _: metrics.sentiment(doc),
}


class InvalidInput(ValueError):
    pass


@dataclass(frozen=True)
class CheckResult:
    id: str
    label: str
    score: float | None
    max: float
    value: float | None
    metrics: dict[str, Any]
    feedback: str


@dataclass(frozen=True)
class CriterionResult:
    id: str
    name: str
    score: float | None
    max: float
    scored: bool
    checks: list[CheckResult]


@dataclass(frozen=True)
class Report:
    score: float
    grade: str
    label: str
    criteria: list[CriterionResult]
    improvements: list[str]
    reliability: dict[str, float]
    stats: dict[str, Any]
    warnings: list[str]
    rubric: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Scorer:
    def __init__(self, rubric: Rubric, registry: Mapping[str, MetricFn] = METRICS):
        for criterion in rubric.criteria:
            for check in criterion.checks:
                if check.metric not in registry:
                    raise RubricError(
                        f"check '{check.id}' uses unknown metric '{check.metric}'; "
                        f"available: {', '.join(sorted(registry))}"
                    )
        self.rubric = rubric
        self._registry = registry

    def score(self, transcript: str, duration_seconds: float | None = None) -> Report:
        doc = self._document(transcript, duration_seconds)
        factor, reliability, warnings = self._reliability(doc)

        criteria: list[CriterionResult] = []
        lost: list[tuple[float, str]] = []
        earned = available = 0.0
        for criterion in self.rubric.criteria:
            checks = [self._check(check, doc, factor) for check in criterion.checks]
            result = _combine(criterion, checks)
            criteria.append(result)
            if result.scored:
                earned += result.score
                available += criterion.weight
            lost += [(c.max - c.score, c.feedback) for c in checks if c.score is not None]

        if doc.duration_seconds is None:
            warnings.append("No duration given, so speech rate was not scored.")

        overall = 100 * earned / available if available else 0.0
        grade = self.rubric.grade_for(overall)
        lost.sort(key=lambda item: item[0], reverse=True)
        return Report(
            score=round(overall, 1),
            grade=grade.grade,
            label=grade.label,
            criteria=criteria,
            improvements=[feedback for gap, feedback in lost[:3] if gap >= 1],
            reliability=reliability,
            stats=_stats(doc),
            warnings=warnings,
            rubric={"name": self.rubric.name, "version": self.rubric.version},
        )

    def _document(self, transcript: Any, duration: Any) -> Document:
        if not isinstance(transcript, str) or not transcript.strip():
            raise InvalidInput("Transcript must be a non-empty string.")
        if duration is not None:
            if isinstance(duration, bool) or not isinstance(duration, int | float):
                raise InvalidInput("duration_seconds must be a number.")
            if not math.isfinite(duration) or not 0 < duration <= MAX_DURATION_SECONDS:
                raise InvalidInput(
                    f"duration_seconds must be greater than 0 and at most {MAX_DURATION_SECONDS}."
                )
        doc = Document.from_text(transcript, float(duration) if duration is not None else None)
        if not doc.word_count:
            raise InvalidInput("Transcript must contain at least one word.")
        return doc

    def _reliability(self, doc: Document) -> tuple[float, dict[str, float], list[str]]:
        # Scales every score down when the text is too short, reads like a keyword
        # list, or repeats itself. Real introductions sit at 1.0 on all three.
        limits = self.rubric.reliability
        length = min(1.0, doc.word_count / limits.min_words)
        naturalness = min(1.0, function_word_ratio(doc.words) / limits.min_function_word_ratio)
        diversity = min(1.0, mattr(doc.words, metrics.VOCAB_WINDOW) / limits.min_lexical_diversity)

        warnings = []
        if length < 1:
            warnings.append(
                f"Only {doc.word_count} words; scores are scaled down below "
                f"{limits.min_words} words."
            )
        if naturalness < 1:
            warnings.append("Reads like a list of keywords rather than speech; scores scaled down.")
        if diversity < 1:
            warnings.append("Heavy repetition detected; scores scaled down.")

        factor = length * naturalness * diversity
        signals = {"length": length, "naturalness": naturalness, "diversity": diversity}
        return factor, {k: round(v, 3) for k, v in {"factor": factor, **signals}.items()}, warnings

    def _check(self, check: Check, doc: Document, factor: float) -> CheckResult:
        measured = self._registry[check.metric](doc, self.rubric)
        if measured.value is None:
            return CheckResult(
                check.id,
                check.label,
                None,
                check.points,
                None,
                measured.metrics,
                measured.note or "",
            )
        points = check.points * check.fraction(measured.value) * factor
        feedback = check.band_for(measured.value).feedback.format_map(_Fields(measured.metrics))
        return CheckResult(
            id=check.id,
            label=check.label,
            score=round(points, 1),
            max=check.points,
            value=round(measured.value, 3),
            metrics=measured.metrics,
            feedback=feedback,
        )


def _combine(criterion: Criterion, checks: list[CheckResult]) -> CriterionResult:
    scored = [c for c in checks if c.score is not None]
    if not scored:
        return CriterionResult(criterion.id, criterion.name, None, criterion.weight, False, checks)
    # Unscored checks don't count against the criterion; the rest are scaled up to its weight.
    share = sum(c.score for c in scored) / sum(c.max for c in scored)
    return CriterionResult(
        criterion.id,
        criterion.name,
        round(share * criterion.weight, 1),
        criterion.weight,
        True,
        checks,
    )


def _stats(doc: Document) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "words": doc.word_count,
        "sentences": len(doc.sentences),
        "duration_seconds": doc.duration_seconds,
    }
    if doc.duration_seconds:
        stats["wpm"] = round(doc.word_count / (doc.duration_seconds / 60))
    return stats


class _Fields(dict):
    def __getitem__(self, key: str) -> str:
        value = super().get(key)
        if isinstance(value, list):
            return ", ".join(map(str, value)) or "none"
        if isinstance(value, float):
            return f"{value:g}"
        return "n/a" if value is None else str(value)

    def __missing__(self, key: str) -> str:
        return "n/a"


@cache
def default_scorer() -> Scorer:
    return Scorer(load_rubric())


def score_transcript(transcript: str, duration_seconds: float | None = None) -> Report:
    return default_scorer().score(transcript, duration_seconds)
