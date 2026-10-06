def validate_isbn(code: str) -> bool:
    digits = code.replace("-", "")
    return digits.isdigit() and len(digits) in (10, 13)
