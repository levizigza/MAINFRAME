from lib.calc import adjust_balance

def route_withdraw(account, amount):
    return adjust_balance(account, -amount)
