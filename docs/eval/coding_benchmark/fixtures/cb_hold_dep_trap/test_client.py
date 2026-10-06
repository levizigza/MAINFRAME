from model import Row, export


def test_export():
    assert export(Row("alpha")) == {"name": "alpha"}
