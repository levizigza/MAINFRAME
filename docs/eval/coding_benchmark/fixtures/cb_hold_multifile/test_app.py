from app import headline


def test_headline():
    assert headline("main") == "** main **"
