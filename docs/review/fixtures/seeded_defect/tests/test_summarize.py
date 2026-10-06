import summarize


def test_summarize_two():
    # Happy path only — does not catch off-by-one on last element
    assert summarize.summarize(["a", "b", "c"]) == "a;b"


def test_average_two():
    assert summarize.average([2, 4]) == 3.0
