import random


# ==========================================
# MONEY FORMATTER
# ==========================================
def format_money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


# ==========================================
# CONFIG
# ==========================================
CLEAN_CHANGE_CHANCE = 0.60

MIN_BILL = 5000      # $50.00
MAX_BILL = 10000     # $100.00

# NEW ECONOMY SCALING
MIN_ECON_BASE = 10000     # $100
MAX_ECON_BASE = 50000     # $500

MIN_MULT = 1.4
MAX_MULT = 3.7

CLEAN_CHANGE_AMOUNTS = [
    100, 500, 1000, 2000, 5000, 10000
]

MESSY_PAYMENT_AMOUNTS = [
    10000,
    20000,
    50000,
]


# ==========================================
# GENERATE GAME
# ==========================================
def generate_make_change_game():
    """
    Returns:
    {
        bill_cents,
        payment_cents,
        change_cents,
        options,
        reward_cents,
        penalty_cents
    }
    """

    # ==========================================
    # BILL
    # ==========================================
    bill_cents = random.randint(MIN_BILL, MAX_BILL)

    clean_change = random.random() < CLEAN_CHANGE_CHANCE

    # ==========================================
    # CLEAN ROUND
    # ==========================================
    if clean_change:
        change_cents = random.choice(CLEAN_CHANGE_AMOUNTS)
        payment_cents = bill_cents + change_cents

    # ==========================================
    # MESSY ROUND
    # ==========================================
    else:
        payment_cents = None

        for amount in MESSY_PAYMENT_AMOUNTS:
            if amount > bill_cents:
                payment_cents = amount
                break

        if payment_cents is None:
            payment_cents = bill_cents + 1000

        change_cents = payment_cents - bill_cents

    # ==========================================
    # OPTIONS
    # ==========================================
    options = {change_cents}

    while len(options) < 4:
        variation = random.choice([
            -1000, -500, -250, -100,
             100,  250,  500, 1000
        ])

        wrong = change_cents + variation
        if wrong > 0:
            options.add(wrong)

    options = list(options)
    random.shuffle(options)

    # ==========================================
    # ECONOMY REWARD / PENALTY (NEW SYSTEM)
    # ==========================================
    base = random.randint(MIN_ECON_BASE, MAX_ECON_BASE)
    multiplier = random.uniform(MIN_MULT, MAX_MULT)

    econ_value = int(base * multiplier)

    reward_cents = econ_value
    penalty_cents = econ_value

    # ==========================================
    # RETURN
    # ==========================================
    return {
        "bill_cents": bill_cents,
        "payment_cents": payment_cents,
        "change_cents": change_cents,
        "options": options,

        # economy impact
        "reward_cents": reward_cents,
        "penalty_cents": penalty_cents,

        # debug hooks
        "econ_base": base,
        "econ_multiplier": multiplier
    }


# ==========================================
# DEBUG
# ==========================================
if __name__ == "__main__":
    for _ in range(10):
        game = generate_make_change_game()

        print("=" * 50)
        print(f"Bill:    {format_money(game['bill_cents'])}")
        print(f"Payment: {format_money(game['payment_cents'])}")
        print(f"Correct: {format_money(game['change_cents'])}")
        print(f"Reward:  {format_money(game['reward_cents'])}")
        print(f"Penalty: {format_money(game['penalty_cents'])}")
        print(f"Mult:    {game['econ_multiplier']:.2f}")
        print()

        for option in game["options"]:
            print(format_money(option))

        print()