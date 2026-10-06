# Broken multi-file fixture for coding-loop acceptance.
# greeter.greet depends on mathutil.add; both are wrong.

def add(a, b):
    return a * b  # bug: should add


def scale(n):
    return add(n, n)
