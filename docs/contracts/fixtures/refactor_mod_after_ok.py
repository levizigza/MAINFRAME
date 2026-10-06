HELPER_CONST = 42

def public_api(x, y):
    """Stable public entry."""
    return _compute_double(x) + y

def _compute_double(x):
    return x * 2
