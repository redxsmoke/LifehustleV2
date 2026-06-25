import discord
from discord.ui import View, Button
import random

# ------------------------------
# Regular Snake Breakroom Minigame
# ------------------------------
class SnakeBreakroomView(View):
    def __init__(self, pool, guild_id, user_id, user_occupation_id, pay_rate):
        super().__init__(timeout=60)
        self.pool = pool
        self.guild_id = guild_id
        self.user_id = user_id
        self.user_occupation_id = user_occupation_id
        self.pay_rate = pay_rate
        self.outcome_summary = None
        self.helper_member = None  # store actual helper object

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    # ------------------------------
    # Get a RANDOM helper from all Animal Control workers
    # ------------------------------
    async def get_random_helper(self, interaction):
        async with self.pool.acquire() as conn:
            helpers = await conn.fetch(
                """
                SELECT discord_id FROM user_occupations
                WHERE cd_occupation_id = 31
                AND guild_id = $1
                AND discord_id != $2
                """,
                self.guild_id,
                self.user_id,
            )

        if not helpers:
            return None

        chosen = random.choice(helpers)
        helper_id = chosen["discord_id"]

        member = interaction.guild.get_member(helper_id)
        if not member:
            try:
                member = await interaction.guild.fetch_member(helper_id)
            except discord.NotFound:
                return None

        return member

    # ------------------------------
    # Reward helper with XP + cash + broadcast message
    # ------------------------------
    async def reward_helper(self, helper: discord.Member, player_succeeded: bool, interaction):
        if helper is None:
            return

        # Bigger rewards if the PLAYER succeeded
        if player_succeeded:
            xp_mult = random.uniform(2.0, 8.5)
            cash_mult = random.uniform(2.0, 4.25)
        else:
            xp_mult = random.uniform(1.25, 4.0)
            cash_mult = random.uniform(1.25, 2.5)

        xp_reward = int(50 * xp_mult)
        cash_reward = int(1000 * cash_mult)  # cents

        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE users
                SET xp = xp + $1
                WHERE discord_id = $2 AND guild_id = $3
            """, xp_reward, helper.id, self.guild_id)

            await conn.execute("""
                UPDATE users
                SET checking_account_balance = checking_account_balance + $1
                WHERE discord_id = $2 AND guild_id = $3
            """, cash_reward, helper.id, self.guild_id)

        # Funny messages
        success_msgs = [
            f"{helper.mention} expertly assisted with the snake removal. The snake now respects them.",
            f"{helper.mention} showed up, handled business, and left like a legend.",
            f"{helper.mention} removed the snake so smoothly that HR asked for a tutorial."
        ]

        fail_msgs = [
            f"{helper.mention} tried to remove the snake… the snake filed a complaint.",
            f"{helper.mention} gave it their best shot. The snake gave them side‑eye.",
            f"{helper.mention} attempted snake removal. Luckily Animal Control is paid hourly, not per snake."
        ]

        chosen_line = random.choice(success_msgs if player_succeeded else fail_msgs)

        # Broadcast in channel instead of DM
        await interaction.followup.send(
            f"{chosen_line}\n\n"
            f"**Animal Control Bonus:** {helper.mention} earned **{xp_reward} XP** and **${cash_reward/100:,.2f}** for assisting!"
        )

    # ------------------------------
    # Outcome handler (patched to reward helper)
    # ------------------------------
    async def handle_outcome(self, interaction: discord.Interaction, outcomes):
        try:
            choice = random.choices(outcomes, k=1)[0]

            await interaction.response.defer()

            async with self.pool.acquire() as conn:
                # pick helper
                helper = await self.get_random_helper(interaction)
                self.helper_member = helper
                helper_name = helper.mention if helper else "Animal Control"

                # Positive outcome → bonus in cents
                if choice['type'] == 'positive':
                    multiplier = random.randint(2, 8)
                    self.bonus_amount = 105 * multiplier * 100  # cents
                    formatted_amount = f"{self.bonus_amount / 100:,.2f}"
                    desc = choice['text'].format(helper=helper_name, amount=formatted_amount)

                # Negative outcome → penalty in cents
                elif choice['type'] == 'negative':
                    multiplier = random.randint(2, 8)
                    self.bonus_amount = -15 * multiplier * 100  # cents
                    formatted_amount = f"{self.bonus_amount / 100:,.2f}"
                    desc = choice['text'].format(helper=helper_name, amount=formatted_amount)

                # Neutral → no money shown
                else:
                    multiplier = random.randint(1, 10)
                    self.bonus_amount = 10 * multiplier * 100  # cents
                    desc = choice['text'].format(helper=helper_name)

                self.outcome_type = choice['type']
                self.outcome_summary = desc

            # reward helper regardless of outcome
            await self.reward_helper(helper, player_succeeded=(self.outcome_type == "positive"), interaction=interaction)

            self.stop()

        except Exception as e:
            print(f"Error in handle_outcome: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Something went wrong!", ephemeral=True)
                self.stop()

    # ------------------------------
    # Buttons (unchanged)
    # ------------------------------
    @discord.ui.button(label="📱 Call Animal Control", style=discord.ButtonStyle.primary)
    async def call_animal_control(self, interaction: discord.Interaction, button: discord.ui.Button):
        outcomes = [
            {"type": "positive", "text": "{helper} arrived just in time and saved the day. You earned a bonus of ${amount}."},
            {"type": "positive", "text": "With {helper}'s help, the snake was removed safely. You got a bonus of ${amount}!"},
            {"type": "neutral",  "text": "{helper} responded and handled the snake. No bonus, but no trouble either."},
            {"type": "neutral",  "text": "You and {helper} watched the snake crawl away. Oddly peaceful. No bonus."},
            {"type": "negative", "text": "{helper} showed up late to remove the snake, and your boss docked your pay by ${amount}."},
            {"type": "negative", "text": "{helper} scared the snake into the vents. Chaos ensued. You were fined ${amount}."},
        ]
        await self.handle_outcome(interaction, outcomes)

    @discord.ui.button(label="🤚 Grab it by the neck", style=discord.ButtonStyle.primary)
    async def grab_by_neck(self, interaction: discord.Interaction, button: discord.ui.Button):
        outcomes = [
            {"type": "positive", "text": "You grabbed the snake and danced with it. Somehow this earned you a bonus of ${amount}."},
            {"type": "positive", "text": "You became a snake whisperer for a moment. Bonus: ${amount}."},
            {"type": "neutral",  "text": "You missed, but no one saw. Just walk away."},
            {"type": "neutral",  "text": "You lunged, it slithered. A draw. No pay changes."},
            {"type": "negative", "text": "The snake bit you. You needed a tetanus shot. Pay docked by ${amount} for medical bills."},
            {"type": "negative", "text": "HR saw you and thought it was animal cruelty. You were written up and fined ${amount}."},
        ]
        await self.handle_outcome(interaction, outcomes)

    @discord.ui.button(label="🪣 Put a bucket over it", style=discord.ButtonStyle.primary)
    async def put_bucket(self, interaction: discord.Interaction, button: discord.ui.Button):
        outcomes = [
            {"type": "positive", "text": "Genius! The bucket trap worked. Bonus awarded: ${amount}."},
            {"type": "positive", "text": "You saved the day with a bucket and got ${amount}. The janitor is proud."},
            {"type": "neutral",  "text": "The bucket fell over. Snake vanished. Nobody knows, nobody cares."},
            {"type": "neutral",  "text": "You put a bucket over something, but it wasn’t the snake. Oh well."},
            {"type": "negative", "text": "Snake escaped and your boss blamed you. You’re down ${amount}."},
            {"type": "negative", "text": "You used the good bucket. The janitor reported you. Pay docked ${amount}."},
        ]
        await self.handle_outcome(interaction, outcomes)

    @discord.ui.button(label="🥨 Distract it with snacks", style=discord.ButtonStyle.primary)
    async def distract_with_snacks(self, interaction: discord.Interaction, button: discord.ui.Button):
        outcomes = [
            {"type": "positive", "text": "Snake loves chips! You bought time and earned a bonus of ${amount}."},
            {"type": "positive", "text": "You fed it gummy worms and it fell asleep. ${amount} bonus!"},
            {"type": "neutral",  "text": "The snake ignored the snacks. At least no one was hurt."},
            {"type": "neutral",  "text": "You distracted the snake, but now it lives in the vending machine."},
            {"type": "negative", "text": "Snake choked on snacks and your boss blamed you. Lost ${amount}."},
            {"type": "negative", "text": "You dropped company snacks. Inventory fine: ${amount}."},
        ]
        await self.handle_outcome(interaction, outcomes)


async def play_snake_breakroom(pool, guild_id, user_id, user_occupation_id, pay_rate):
    embed = discord.Embed(
        title="🐍 Snake in the Break Room",
        description=(
            "You find a snake in the break room during your shift! What do you want to do?\n\n"
            "1️⃣ Call Animal Control\n"
            "2️⃣ Grab it by the neck\n"
            "3️⃣ Put a bucket over it\n"
            "4️⃣ Distract it with snacks\n\n"
            "Choose wisely!"
        )
    )
    view = SnakeBreakroomView(pool, guild_id, user_id, user_occupation_id, pay_rate)
    return embed, view

# ------------------------------
# Animal Control Snake Minigame Variant
# ------------------------------
class AnimalControlSnakeView(View):
    def __init__(self, pool, guild_id, user_id, user_occupation_id, pay_rate):
        super().__init__(timeout=60)
        self.pool = pool
        self.guild_id = guild_id
        self.user_id = user_id
        self.user_occupation_id = user_occupation_id
        self.pay_rate = pay_rate
        self.outcome_summary = None
        self.bonus_amount = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    def calculate_bonus(self):
        return random.randint(20, 500) * random.randint(1, 4)

    def calculate_penalty(self):
        return random.randint(20, 100) * random.randint(1, 3)

    @discord.ui.button(label="🪤 Safely capture the snake", style=discord.ButtonStyle.primary)
    async def safe_capture(self, interaction: discord.Interaction, button: discord.ui.Button):
        outcomes = [
            ("positive", "You flawlessly capture the snake. Textbook execution."),
            ("positive", "You gently relocate the snake to the wild. It winks at you. Weird."),
            ("neutral", "You hesitated a little, but the snake cooperated. No harm done."),
            ("neutral", "You used the capture pole slightly incorrectly, but it still worked."),
            ("negative", "You botch the capture and the snake slithers into the vending machine."),
            ("negative", "You forgot your gloves and got nipped. You're fine. Your pride isn't."),
        ]
        await self.resolve(interaction, outcomes)

    @discord.ui.button(label="🧘 Calm the freaked out employee", style=discord.ButtonStyle.primary)
    async def calm_employee(self, interaction: discord.Interaction, button: discord.ui.Button):
        outcomes = [
            ("positive", "You bring calm with a clipboard and confidence. Bonus time."),
            ("positive", "You distract the employee with a hilarious snake pun. They're fine."),
            ("neutral", "The employee slowly calms down after you hand them a stress ball."),
            ("neutral", "You just stand near them until they stop yelling. Effective? Sure."),
            ("negative", "They scream louder after you mention how venom works. Whoops."),
            ("negative", "You panic slightly and scream too. The supervisor is disappointed."),
        ]
        await self.resolve(interaction, outcomes)

    @discord.ui.button(label="📱 Call for backup", style=discord.ButtonStyle.primary)
    async def call_backup(self, interaction: discord.Interaction, button: discord.ui.Button):
        outcomes = [
            ("positive", "Backup arrives and handles everything perfectly. Like clockwork."),
            ("positive", "You and backup play rock-paper-scissors for who handles the snake. You win."),
            ("neutral", "Backup arrives late, but everything still gets sorted."),
            ("neutral", "The snake just chills while you wait for backup. It’s oddly patient."),
            ("negative", "Backup trips on arrival and breaks the coffee machine. Yikes."),
            ("negative", "You accidentally call pest control instead. They run screaming."),
        ]
        await self.resolve(interaction, outcomes)

    @discord.ui.button(label="📝 Focus on paperwork", style=discord.ButtonStyle.primary)
    async def paperwork(self, interaction: discord.Interaction, button: discord.ui.Button):
        outcomes = [
            ("positive", "You handle the backlog while someone else catches the snake. Genius."),
            ("positive", "Your paperwork is so thorough, you get praised even with a loose snake."),
            ("neutral", "You stay laser-focused while chaos unfolds around you."),
            ("neutral", "You pretend to not notice the snake and finish a full report."),
            ("negative", "Your boss finds out you ignored the snake. Not a great look."),
            ("negative", "Snake climbs into your paperwork bin. You're startled. A report is ruined."),
        ]
        await self.resolve(interaction, outcomes)

    async def resolve(self, interaction, outcome_pool):
        category, message = random.choice(outcome_pool)
        bonus = penalty = 0

        if category == "positive":
            bonus = 0
        elif category == "negative":
            penalty = 0

        self.outcome_summary = message
        self.outcome_type = category
        await interaction.response.defer()
        self.stop()

# ------------------------------
# Dispatcher function
# ------------------------------
async def play(pool, guild_id, user_id, user_occupation_id, pay_rate):
    if user_occupation_id == 31:
        return await play_animal_control_snake(pool, guild_id, user_id, user_occupation_id, pay_rate)
    else:
        return await play_snake_breakroom(pool, guild_id, user_id, user_occupation_id, pay_rate)
