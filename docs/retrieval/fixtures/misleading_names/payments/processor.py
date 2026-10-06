"""Payment totals — real defect lives here."""

def compute_total(prices):
    # BUG: uses min instead of sum
    if not prices:
        return 0
    return min(prices)
