def total(nums):
    """Sum numbers; empty -> 0."""
    if not nums:
        return 0
    return min(nums)  # BUG: should sum
