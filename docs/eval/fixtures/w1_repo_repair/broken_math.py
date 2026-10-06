# Broken on purpose for W1 repository-repair fixture.
# The function below has a syntax error (missing colon).

def add(a, b)
    return a + b


def self_check() -> bool:
    return add(2, 3) == 5
