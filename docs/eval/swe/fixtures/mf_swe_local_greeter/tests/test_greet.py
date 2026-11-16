from greeter import greet


def test_greet():
    assert greet("a", "b") == "a; b"
