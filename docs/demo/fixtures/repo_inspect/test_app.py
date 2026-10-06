from app import greet


def test_greet() -> None:
    assert greet("mainframe") == "hello,mainframe"


if __name__ == "__main__":
    test_greet()
    print("OK")
