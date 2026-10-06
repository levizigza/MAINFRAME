def adjust_balance(account, delta):
    # BUG: abs() drops sign so withdrawals increase balance
    new_val = account["balance"] + abs(delta)
    if new_val < 0:
        raise ValueError("negative balance")
    account["balance"] = new_val
    return account
