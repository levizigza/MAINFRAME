from payments.processor import compute_total

def test_total():
    assert compute_total([10, 20, 30]) == 60
