import pytest

from speakscore.text import Document, function_word_ratio, mattr, normalize


def test_normalize_unwraps_lines_and_straightens_quotes():
    raw = "Hello—everyone.\r\nI’m Asha,\nand I   sing.\n\n\n\nThanks."
    assert normalize(raw) == "Hello-everyone. I'm Asha, and I sing.\n\nThanks."


def test_document_splits_sentences_and_words():
    doc = Document.from_text('Hi there! I\'m Asha. She said "hello." Bye\n\nNew paragraph')
    assert doc.sentences == ("Hi there!", "I'm Asha.", 'She said "hello."', "Bye", "New paragraph")
    assert doc.words[:4] == ("hi", "there", "i'm", "asha")
    assert doc.word_count == 10


def test_head_and_tail_offsets():
    doc = Document.from_text("one two three four five")
    assert doc.text[: doc.head_end(2)] == "one two"
    assert doc.text[doc.tail_start(2) :] == "four five"
    assert doc.head_end(99) == len(doc.text)
    assert Document.from_text("").head_end(3) == 0


def test_function_word_ratio():
    assert function_word_ratio(["i", "like", "the", "sea"]) == 0.5
    assert function_word_ratio(["name", "school", "hobbies"]) == 0
    assert function_word_ratio([]) == 0


def test_mattr_matches_ttr_for_short_texts():
    assert mattr(["a", "b", "a", "c"]) == 0.75


def test_mattr_uses_moving_window():
    words = ["a", "b", "c", "d"] * 30
    assert mattr(words, window=4) == pytest.approx(1.0)
    assert mattr(["a", "a"] * 60, window=10) == pytest.approx(0.1)
