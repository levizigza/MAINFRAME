# Holdout: dependency-version trap

`constraints.txt` pins **no third-party upgrades**. Code incorrectly calls a Pydantic v2-style API.
Fix `model.py` using the local `Row.as_dict()` helper — do **not** change `constraints.txt`.
