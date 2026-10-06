HELPER_CONST = 42

def public_api(x, y):
    """Stable public entry."""
    return _hidden(x) + y

def _hidden(x):
    return x * 2
