import random

class VaultGame:
    def __init__(self):
        self.code = [random.randint(0, 9) for _ in range(3)]
        self.attempts = 0
        self.max_attempts = 5

    def check_guess(self, guess_str: str):
        """
        Returns:
            "unlocked"     → correct code
            "locked_out"   → too many attempts
            string message → clue feedback
        """

        self.attempts += 1

        # Validate input
        if len(guess_str) != 3 or not guess_str.isdigit():
            return "❌ Invalid guess. Enter a 3-digit code like `382`."

        guess = [int(d) for d in guess_str]
        clues = []

        # Build clue feedback
        for i in range(3):
            if guess[i] == self.code[i]:
                clues.append("✅")  # correct digit, correct place
            elif guess[i] in self.code:
                clues.append("⚠️")  # correct digit, wrong place
            else:
                clues.append("❌")  # digit not in code

        # Win condition
        if guess == self.code:
            return "unlocked"

        # Lose condition
        if self.attempts >= self.max_attempts:
            return "locked_out"

        # Feedback
        return f"Attempt {self.attempts}/{self.max_attempts}: {' '.join(clues)}"
