def compute_total(prices):
    """Public API — must remain callable as compute_total(prices)."""
    # BUG: returns min instead of sum
    if not prices:
        return 0
    return min(prices)
