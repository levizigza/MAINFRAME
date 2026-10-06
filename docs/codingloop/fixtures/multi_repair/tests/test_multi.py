import greeter
import mathutil


def test_add():
    assert mathutil.add(2, 3) == 5


def test_greet():
    assert greeter.greet("Ada", 2) == "Hello Ada; Hello Ada"


def test_self_check():
    assert greeter.self_check() is True
