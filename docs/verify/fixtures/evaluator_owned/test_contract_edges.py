import sys
from pathlib import Path
# Target injected via PYTHONPATH
from mathlib import total

def test_empty():
    assert total([]) == 0

def test_single():
    assert total([7]) == 7

def test_negatives():
    assert total([-1, -2, 5]) == 2
