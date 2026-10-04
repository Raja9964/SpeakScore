import pytest
from conftest import load_sample

from speakscore.engine import METRICS, InvalidInput, Scorer, score_transcript
from speakscore.rubric import RubricError, load_rubric

KEYWORD_LIST = (
    "hello good morning name age school college family father mother hobbies cricket music "
    "goals dream engineer thank you name family hobbies goals school college thank you hello "
    "hobbies goals family awesome great amazing"
)
REPEATED_PHRASES = "my name is my family my hobbies my goal my dream I want to thank you " * 6


def test_strong_sample_scores_high():
    report = score_transcript(*load_sample("strong"))
    assert report.score >= 75
    assert report.grade in {"A", "B"}
    assert report.warnings == []


def test_weak_sample_scores_low():
    report = score_transcript(*load_sample("weak"))
    assert report.score < 40
    assert report.improvements


def test_samples_are_ranked_in_order():
    scores = [score_transcript(*load_sample(n)).score for n in ("strong", "average", "weak")]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize("junk", [KEYWORD_LIST, REPEATED_PHRASES])
def test_keyword_stuffing_scores_low(junk):
    report = score_transcript(junk, 40)
    assert report.score < 40
    assert report.reliability["factor"] < 0.6
    assert report.warnings


@pytest.mark.parametrize("transcript", ["", "   \n ", "... !!!", None, 42])
def test_empty_or_non_text_transcripts_are_rejected(transcript):
    with pytest.raises(InvalidInput):
        score_transcript(transcript)


@pytest.mark.parametrize("duration", [0, -5, 7200, float("nan"), True, "52"])
def test_bad_durations_are_rejected(duration):
    with pytest.raises(InvalidInput):
        score_transcript("My name is Asha.", duration)


def test_missing_duration_skips_speech_rate_and_rescales():
    text, _ = load_sample("strong")
    report = score_transcript(text)
    rate = next(c for c in report.criteria if c.id == "speech_rate")
    assert not rate.scored
    assert rate.score is None
    assert "duration" in rate.checks[0].feedback
    scored = [c for c in report.criteria if c.scored]
    assert report.score == pytest.approx(
        100 * sum(c.score for c in scored) / sum(c.max for c in scored), abs=0.1
    )


def test_report_shape():
    data = score_transcript(*load_sample("average")).to_dict()
    assert set(data) == {
        "score",
        "grade",
        "label",
        "criteria",
        "improvements",
        "reliability",
        "stats",
        "warnings",
        "rubric",
    }
    assert sum(c["max"] for c in data["criteria"]) == 100
    for criterion in data["criteria"]:
        assert 0 <= criterion["score"] <= criterion["max"]
        for check in criterion["checks"]:
            assert check["feedback"]
            assert "{" not in check["feedback"]
            assert isinstance(check["metrics"], dict)


def test_unknown_metric_is_rejected():
    rubric = load_rubric()
    registry = {k: v for k, v in METRICS.items() if k != "sentiment"}
    with pytest.raises(RubricError, match="unknown metric 'sentiment'"):
        Scorer(rubric, registry)
