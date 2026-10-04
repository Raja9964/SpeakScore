import copy
import json

import pytest

from speakscore.rubric import DEFAULT_RUBRIC_PATH, RubricError, load_rubric, parse_rubric


@pytest.fixture(scope="module")
def raw():
    return json.loads(DEFAULT_RUBRIC_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def data(raw):
    return copy.deepcopy(raw)


def test_default_rubric_is_consistent():
    rubric = load_rubric()
    assert rubric.total_weight == 100
    for criterion in rubric.criteria:
        assert sum(c.points for c in criterion.checks) == criterion.weight
    assert {c.id for c in rubric.criteria} == {
        "content",
        "speech_rate",
        "language",
        "clarity",
        "engagement",
    }
    assert rubric.sections[-1].zone == "closing"


def test_band_scoring_uses_half_open_ranges():
    pace = next(c for c in load_rubric().criteria if c.id == "speech_rate").checks[0]
    assert pace.fraction(110) == 1.0
    assert pace.fraction(149.9) == 1.0
    assert pace.fraction(150) == 0.7
    assert pace.fraction(20) == 0.1


def test_linear_scoring_supports_lower_is_better():
    language = next(c for c in load_rubric().criteria if c.id == "language")
    grammar = language.checks[0]
    assert grammar.linear == (6.0, 0.0)
    assert grammar.fraction(0) == 1.0
    assert grammar.fraction(3) == pytest.approx(0.5)
    assert grammar.fraction(12) == 0.0


def test_grade_lookup():
    rubric = load_rubric()
    assert rubric.grade_for(85).grade == "A"
    assert rubric.grade_for(84.9).grade == "B"
    assert rubric.grade_for(0).grade == "E"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d["criteria"][0].update(weight=50), "check points add up"),
        (
            lambda d: (
                d["criteria"][3]["checks"][0].update(points=20)
                or d["criteria"][3].update(weight=20)
            ),
            "add up to 100",
        ),
        (lambda d: d["criteria"][1]["checks"][0]["bands"][0].pop("score"), "'score' is required"),
        (lambda d: d["criteria"][1]["checks"][0]["bands"][-1].update(min=0), "catch-all"),
        (lambda d: d["criteria"][1]["checks"][0]["bands"][0].update(score=2), "between 0 and 1"),
        (lambda d: d["criteria"][0]["checks"][1].update(linear=[1, 1]), "must differ"),
        (lambda d: d["criteria"][0]["checks"][0].pop("metric"), "missing 'metric'"),
        (lambda d: d["sections"][0]["patterns"].append("(unclosed"), "invalid pattern"),
        (lambda d: d["sections"][0].update(zone="middle"), "'zone' must be one of"),
        (lambda d: d["sections"][1].update(id="name"), "duplicate section id"),
        (lambda d: d["grades"].reverse(), "highest to lowest"),
        (lambda d: d["reliability"].update(min_words="many"), "must be an integer"),
        (lambda d: d.update(criteria=[]), "non-empty list"),
    ],
)
def test_invalid_rubrics_are_rejected(data, mutate, message):
    mutate(data)
    with pytest.raises(RubricError, match=message):
        parse_rubric(data)


def test_load_rubric_reports_bad_files(tmp_path):
    with pytest.raises(RubricError, match="Cannot read"):
        load_rubric(tmp_path / "missing.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(RubricError, match="not valid JSON"):
        load_rubric(broken)
