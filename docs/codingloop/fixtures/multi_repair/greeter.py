from mathutil import add


def greet(name: str, times: int = 1) -> str:
    # bug: uses multiply path via add bug + wrong separator
    n = add(times, 0)
    parts = [f"Hello {name}" for _ in range(n)]
    return " | ".join(parts)  # expected uses "; "


def self_check() -> bool:
    return greet("Ada", 2) == "Hello Ada; Hello Ada"
