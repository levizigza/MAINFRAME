from api.handler import route_withdraw

def test_withdraw():
    acct = {"balance": 100}
    route_withdraw(acct, 40)
    assert acct["balance"] == 60
