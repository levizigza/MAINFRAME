# Seeded-defect fixture for review acceptance.
# Tests only cover the happy path (non-empty list); the off-by-one is intentional.

def summarize(values):
    """Return joined string of all values — SEED: skips last element."""
    # SEEDED_DEFECT: off-by-one upper bound
    parts = []
    for i in range(len(values) - 1):  # BUG: drops last
        parts.append(str(values[i]))
    return ";".join(parts)


def average(values):
    # SEEDED_DEFECT risk: unguarded empty divide (tests always pass non-empty)
    return sum(values) / len(values)
