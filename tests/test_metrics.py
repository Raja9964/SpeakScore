import pytest

from speakscore import metrics
from speakscore.grammar import find_issues
from speakscore.rubric import load_rubric
from speakscore.text import Document

RUBRIC = load_rubric()


def doc(text, duration=None):
    return Document.from_text(text, duration)


@pytest.mark.parametrize(
    ("text", "level"),
    [
        ("Good morning everyone, I'm glad to be here. My name is Asha.", 3),
        ("Good afternoon. My name is Asha.", 2),
        ("Hi, my name is Asha.", 1),
        ("My name is Asha and I live in Kochi.", 0),
    ],
)
def test_salutation_levels(text, level):
    assert metrics.salutation(doc(text), RUBRIC.salutations).value == level


def test_salutation_only_counts_the_opening():
    late = "My name is Asha. " + "I live in a small town by the sea. " * 5 + "Good morning."
    assert metrics.salutation(doc(late), RUBRIC.salutations).value == 0


def test_coverage_reports_found_and_missing_sections():
    text = (
        "My name is Asha and I am sixteen years old. I study at Lakeside Grove School. "
        "In my free time I paint. Thank you."
    )
    result = metrics.coverage(doc(text), RUBRIC.sections)
    assert result.metrics["missing"] == ["Family", "Goals"]
    assert result.value == pytest.approx(18 / 25)


def test_closing_must_come_at_the_end():
    text = "Thank you for the chance to speak. " + "I enjoy painting landscapes. " * 10
    assert "Closing" in metrics.coverage(doc(text), RUBRIC.sections).metrics["missing"]


def test_section_order_flags_misplaced_sections():
    ordered = "My name is Asha. I am from Kochi. I study at Lakeside Grove School. Thank you."
    shuffled = "I study at Lakeside Grove School. My name is Asha. I am from Kochi. Thanks."
    assert metrics.section_order(doc(ordered), RUBRIC.sections).value == 1
    result = metrics.section_order(doc(shuffled), RUBRIC.sections)
    assert result.value == pytest.approx(3 / 4)
    assert result.metrics["out_of_order"] == ["Education or work"]


def test_section_order_needs_enough_sections():
    assert metrics.section_order(doc("My name is Asha. Thank you."), RUBRIC.sections).value == 0


def test_speech_rate():
    text = " ".join(["word"] * 130)
    assert metrics.speech_rate(doc(text, 60)).value == 130
    missing = metrics.speech_rate(doc(text))
    assert missing.value is None
    assert "duration" in missing.note


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("She are my best friend.", "subject-verb agreement"),
        ("I is happy.", "subject-verb agreement"),
        ("I have a apple.", "use 'an' here"),
        ("It was an big day.", "use 'a' here"),
        ("I like the the park.", "repeated word"),
        ("This is more better.", "double comparative"),
        ("I could of gone.", "'of' instead of 'have'"),
        ("I am having two brothers.", "progressive 'having' for possession"),
        ("Then i went home.", "lowercase 'i'"),
        ("Hello. my name is Asha.", "sentence starts lowercase"),
        ("Hi. Name age school college family hobbies goals. Bye.", "sentence without a verb"),
    ],
)
def test_grammar_rules(text, rule):
    assert rule in [issue.rule for issue in find_issues(doc(text))]


@pytest.mark.parametrize(
    "text",
    [
        "I am an engineer at a university and I spent an hour with a European team.",
        "Does she have a dog? I wonder if he does.",
        "Good morning everyone. I enjoy reading and I want to travel.",
        "i am writing in lowercase only so capitals are not judged here",
    ],
)
def test_grammar_avoids_false_positives(text):
    assert find_issues(doc(text)) == []


def test_run_on_sentence():
    long_sentence = "and I went to the shop " * 9
    assert "run-on sentence" in [i.rule for i in find_issues(doc(long_sentence))]


def test_grammar_rate_is_per_hundred_words():
    result = metrics.grammar(doc("I is happy. " + "I like the sea. " * 12))
    assert result.metrics["issues"] == 1
    assert result.value == pytest.approx(100 / 51)


def test_vocabulary():
    varied = metrics.vocabulary(doc("Every single word here is completely different from others."))
    repeated = metrics.vocabulary(doc("good good good good good good good good"))
    assert varied.value == 1
    assert repeated.value == pytest.approx(1 / 8)


def test_fillers_count_phrases_but_not_verb_like():
    text = "Um, I like painting and, uh, you know, I like, really enjoy it. Basically yes."
    result = metrics.fillers(doc(text), RUBRIC.fillers)
    assert result.metrics["fillers"] == 5
    assert result.metrics["found"][0] in {"um x1", "uh x1", "you know x1", "like x1"}
    assert metrics.fillers(doc("I like painting."), RUBRIC.fillers).value == 0


def test_sentiment_direction():
    positive = metrics.sentiment(doc("I love my work and I am excited about the future."))
    negative = metrics.sentiment(doc("I hate this, it is boring and awful."))
    assert positive.value > 0.5
    assert negative.value < -0.5
