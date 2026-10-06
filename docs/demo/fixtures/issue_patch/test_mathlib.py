from mathlib import multiply


def test_multiply() -> None:
    assert multiply(3, 4) == 12


if __name__ == "__main__":
    test_multiply()
    print("OK")
