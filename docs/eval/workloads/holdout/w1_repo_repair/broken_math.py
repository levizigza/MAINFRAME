# Held-out: repository repair
# Bug: multiply uses addition; test expects product.
# Distinct from scorecard W1 (missing colon) and demo issue_patch.

def multiply(a, b):
    return a + b  # BUG: should multiply


def self_check() -> bool:
    return multiply(3, 4) == 12 and multiply(0, 5) == 0 and multiply(-2, 3) == -6
