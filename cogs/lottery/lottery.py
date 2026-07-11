import random
import discord
from datetime import datetime, timedelta
import pytz
import traceback

LOTTO_COST = 25000 * 100
TEST_MODE = True
EST = pytz.timezone("America/New_York")


def log_error(where, error):
    print(f"[LOTTERY][ERROR] {where}: {error}")
    traceback.print_exc()


# ---------------------------------------------------------
# get_next_draw_from_db — TEST_MODE draw creation removed
# ---------------------------------------------------------

async def get_next_draw_from_db(pool):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT lottery_results_id, draw_date, ran_status
            FROM lottery_results
            WHERE ran_status = 'not ran'
            ORDER BY draw_date ASC
            LIMIT 1
            """
        )

        # ⭐ No Python-created draws anymore
        return row


def fmt(n):
    return f"{n:02d}"


# ---------------------------------------------------------
# QUANTITY SELECT — MUST BE ABOVE LottoView
# ---------------------------------------------------------

class QuantitySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=str(x), value=str(x))
            for x in [1, 5, 10, 20, 50, 100, 250]
        ]

        # ⭐ NEW OPTION — All Remaining
        options.append(discord.SelectOption(
            label="All Remaining",
            value="ALL"
        ))

        super().__init__(
            placeholder="Select ticket bundle",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction):
        view: LottoView = self.view

        if self.values[0] == "ALL":
            view.quantity = "ALL"
            self.placeholder = "All remaining tickets selected"

            embed = discord.Embed(
                title="🎟️ All Remaining Selected",
                description="Click **Generate For Me** to purchase **all remaining tickets** allowed for this draw.",
                color=discord.Color.blurple()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        view.quantity = int(self.values[0])
        self.placeholder = f"{view.quantity} ticket bundle selected"

        embed = discord.Embed(
            title="🎟️ Ticket Bundle Selected",
            description=f"Click **Generate For Me** to purchase **{view.quantity}** ticket(s).",
            color=discord.Color.blurple()
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------
# NUMBER PAD UI
# ---------------------------------------------------------

class NumberPadView(discord.ui.View):
    def __init__(self, user_id, guild_id, pool, parent_view):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.guild_id = guild_id
        self.pool = pool
        self.parent_view = parent_view

        self.current_digits = ""
        self.numbers = ["--"] * 5
        self.bigballz = "--"

        for idx, num in enumerate(["1","2","3","4","5","6","7","8","9"]):
            self.add_item(NumberButton(num, row=idx // 3))

        self.add_item(NumberButton("0", row=3))
        self.add_item(PlaceholderButton(row=3))
        self.add_item(PlaceholderButton(row=3))

        self.add_item(ClearNumberButton(row=4))
        self.add_item(ClearAllButton(row=4))

        self.submit_button = SubmitButton(row=4)
        self.submit_button.disabled = True
        self.add_item(self.submit_button)

        self.add_item(CancelButton(row=4))

    def get_embed(self):
        embed = discord.Embed(
            title="🔢 Pick Your Numbers",
            description=(
                "Select **5 numbers (01–69)** and **1 BigBallz (01–26)**.\n"
                "Numbers 1–9 must be entered as **01–09**.\n\n"
                "Each number is **two digits**. After two presses, it auto‑moves to the next."
            ),
            color=discord.Color.blurple()
        )

        for i in range(5):
            embed.add_field(name=f"Number {i+1}", value=f"**{self.numbers[i]}**", inline=True)

        embed.add_field(name="BigBallz", value=f"**{self.bigballz}**", inline=True)

        return embed

    async def send_invalid(self, interaction):
        self.current_digits = ""
        await interaction.response.send_message(
            embed=discord.Embed(
                title="❌ Invalid Number Selected",
                description="Valid range: **01–69** for main numbers, **01–26** for BigBallz.",
                color=discord.Color.red()
            ),
            ephemeral=True
        )

    async def commit_number(self, interaction):
        num = int(self.current_digits)
        filling_main = any(n == "--" for n in self.numbers)

        if filling_main:
            if not (1 <= num <= 69):
                return await self.send_invalid(interaction)

            for i in range(5):
                if self.numbers[i] == "--":
                    self.numbers[i] = fmt(num)
                    break

        else:
            if not (1 <= num <= 26):
                return await self.send_invalid(interaction)

            self.bigballz = fmt(num)

        self.current_digits = ""

    def update_submit_state(self):
        self.submit_button.disabled = not (
            all(n != "--" for n in self.numbers) and self.bigballz != "--"
        )


class NumberButton(discord.ui.Button):
    def __init__(self, number, row):
        super().__init__(label=number, style=discord.ButtonStyle.secondary, row=row)
        self.number = number

    async def callback(self, interaction):
        view: NumberPadView = self.view
        view.current_digits += self.number

        if len(view.current_digits) == 2:
            await view.commit_number(interaction)

        view.update_submit_state()

        await interaction.response.edit_message(embed=view.get_embed(), view=view)


class PlaceholderButton(discord.ui.Button):
    def __init__(self, row):
        super().__init__(label="​", style=discord.ButtonStyle.secondary, disabled=True, row=row)


class ClearNumberButton(discord.ui.Button):
    def __init__(self, row):
        super().__init__(label="Clear Number", style=discord.ButtonStyle.danger, row=row)

    async def callback(self, interaction):
        view: NumberPadView = self.view

        if view.current_digits:
            view.current_digits = ""
        else:
            if view.bigballz != "--":
                view.bigballz = "--"
            else:
                for i in reversed(range(5)):
                    if view.numbers[i] != "--":
                        view.numbers[i] = "--"
                        break

        view.update_submit_state()
        await interaction.response.edit_message(embed=view.get_embed(), view=view)


class ClearAllButton(discord.ui.Button):
    def __init__(self, row):
        super().__init__(label="Clear All", style=discord.ButtonStyle.danger, row=row)

    async def callback(self, interaction):
        view: NumberPadView = self.view
        view.current_digits = ""
        view.numbers = ["--"] * 5
        view.bigballz = "--"
        view.update_submit_state()

        await interaction.response.edit_message(embed=view.get_embed(), view=view)


class SubmitButton(discord.ui.Button):
    def __init__(self, row):
        super().__init__(label="Submit", style=discord.ButtonStyle.success, row=row)

    async def callback(self, interaction):
        view: NumberPadView = self.view

        if view.submit_button.disabled:
            return await interaction.response.send_message(
                "You must enter **5 numbers** and **1 BigBallz**.",
                ephemeral=True
            )

        nums = [int(n) for n in view.numbers]
        pb = int(view.bigballz)

        await view.parent_view.process_ticket(interaction, nums=nums, pb=pb)


class CancelButton(discord.ui.Button):
    def __init__(self, row):
        super().__init__(label="Cancel", style=discord.ButtonStyle.secondary, row=row)

    async def callback(self, interaction):
        await interaction.response.send_message("Number selection cancelled.", ephemeral=True)
        await interaction.message.delete()


class LottoView(discord.ui.View):
    def __init__(self, user_id, guild_id, pool):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.guild_id = guild_id
        self.pool = pool
        self.quantity = 1

        self.next_draw_row = None
        self.draw_pk = None
        self.draw_date = None
        self.next_draw = None
        self.cutoff = None

        self.add_item(QuantitySelect())

    async def load_draw_info(self):
        row = await get_next_draw_from_db(self.pool)

        if row is None:
            raise RuntimeError("No upcoming draw found.")

        self.next_draw_row = row
        self.draw_pk = row["lottery_results_id"]
        self.draw_date = row["draw_date"]

        if row["ran_status"] != "not ran":
            raise RuntimeError("Next draw is already closed.")

        if TEST_MODE:
            now_est = datetime.now(EST).replace(tzinfo=None)

            minutes = (now_est.minute // 3) * 3
            next_cycle = now_est.replace(minute=minutes, second=0, microsecond=0)
            self.next_draw = next_cycle + timedelta(minutes=3)

            self.cutoff = self.next_draw - timedelta(minutes=1)
            self.draw_date = self.next_draw.date()

        else:
            self.next_draw = datetime.combine(
                self.draw_date,
                datetime.min.time()
            ).replace(hour=20, minute=0)
            self.cutoff = self.next_draw - timedelta(minutes=30)

    async def process_ticket(self, interaction, nums=None, pb=None):
        try:
            await self.load_draw_info()

            now_est = datetime.now(EST).replace(tzinfo=None)

            if now_est >= self.cutoff:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⛔ Ticket Sales Closed",
                        description="Ticket sales are closed for this draw.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

            purchase_ts = now_est
            draw_dt = self.draw_date
            draw_pk = self.draw_pk

            async with self.pool.acquire() as conn:

                existing_count = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM lottery
                    WHERE discord_id = $1 AND guild_id = $2 AND lottery_results_id = $3
                    """,
                    self.user_id, self.guild_id, draw_pk
                )

                # ⭐ HARD LIMIT: cannot exceed 250 total tickets
                if existing_count >= 250:
                    return await interaction.response.send_message(
                        embed=discord.Embed(
                            title="❌ Purchase Failed",
                            description=(
                                f"You already purchased **{existing_count}** tickets for this draw.\n"
                                f"The maximum allowed is **250**."
                            ),
                            color=discord.Color.red()
                        ),
                        ephemeral=True
                    )

                # ⭐ ALL remaining logic stays the same
                if self.quantity == "ALL":
                    remaining_allowed = max(0, 250 - existing_count)

                    if remaining_allowed <= 0:
                        return await interaction.response.send_message(
                            embed=discord.Embed(
                                title="❌ Limit Reached",
                                description="You cannot buy any more tickets for this draw.",
                                color=discord.Color.red()
                            ),
                            ephemeral=True
                        )

                    self.quantity = remaining_allowed

                # ⭐ NEW GUARD: prevent existing_count + quantity > 250
                if existing_count + (self.quantity if isinstance(self.quantity, int) else 0) > 250:
                    allowed = max(0, 250 - existing_count)
                    return await interaction.response.send_message(
                        embed=discord.Embed(
                            title="❌ Purchase Failed",
                            description=(
                                f"This purchase would exceed the **250 ticket** limit for this draw.\n"
                                f"You may only buy **{allowed}** more ticket(s)."
                            ),
                            color=discord.Color.red()
                        ),
                        ephemeral=True
                    )

                total_cost = LOTTO_COST * self.quantity

                user = await conn.fetchrow(
                    """
                    SELECT checking_account_balance
                    FROM users
                    WHERE discord_id = $1 AND guild_id = $2
                    """,
                    self.user_id, self.guild_id
                )

                if not user:
                    return await interaction.response.send_message(
                        embed=discord.Embed(
                            title="❌ Account Error",
                            description="Could not find your account.",
                            color=discord.Color.red()
                        ),
                        ephemeral=True
                    )

                balance = user["checking_account_balance"] or 0

                if balance < total_cost:
                    return await interaction.response.send_message(
                        embed=discord.Embed(
                            title="❌ Insufficient Funds",
                            description=f"You need **${total_cost/100:,.2f}**.",
                            color=discord.Color.red()
                        ),
                        ephemeral=True
                    )

                new_balance = balance - total_cost

                await conn.execute(
                    """
                    UPDATE users
                    SET checking_account_balance = $1
                    WHERE discord_id = $2 AND guild_id = $3
                    """,
                    new_balance, self.user_id, self.guild_id
                )

                for _ in range(self.quantity):
                    if nums is None or pb is None:
                        ticket_nums = sorted(random.sample(range(1, 70), 5))
                        ticket_pb = random.randint(1, 26)
                    else:
                        ticket_nums = nums
                        ticket_pb = pb

                    await conn.execute(
                        """
                        INSERT INTO lottery (
                            lottery_results_id,
                            discord_id, guild_id,
                            draw_date, purchase_date,
                            num1, num2, num3, num4, num5,
                            powerball,
                            ticket_status
                        )
                        VALUES (
                            $1, $2, $3,
                            $4::date, $5,
                            $6, $7, $8, $9, $10,
                            $11,
                            'active'
                        )
                        """,
                        draw_pk, self.user_id, self.guild_id,
                        draw_dt, purchase_ts,
                        ticket_nums[0], ticket_nums[1], ticket_nums[2],
                        ticket_nums[3], ticket_nums[4],
                        ticket_pb
                    )

            new_total = existing_count + self.quantity
            remaining = max(0, 250 - new_total)

            embed = discord.Embed(
                title="💸 PowerBallz Ticket Purchased!",
                description=f"Your purchase of **{self.quantity} Ticket(s)** was successful!",
                color=discord.Color.gold()
            )

            embed.add_field(
                name="🎯 Next Draw",
                value=f"`{self.next_draw.strftime('%A %B %d, %Y at %I:%M %p EST')}`",
                inline=False
            )

            embed.add_field(
                name="Cost",
                value=f"**${total_cost/100:,.2f}**",
                inline=False
            )

            embed.add_field(
                name="🏦 Updated Checking Account Balance",
                value=f"**${new_balance/100:,.2f}**",
                inline=False
            )

            embed.add_field(
                name="🎟️ Tickets Remaining",
                value=f"You can buy **{remaining}** more ticket(s) for the upcoming draw.",
                inline=False
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            log_error("process_ticket", e)
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Error",
                    description="Something went wrong processing your ticket.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

    @discord.ui.button(label="Pick My Numbers", style=discord.ButtonStyle.primary)
    async def pick_numbers(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Not Allowed",
                    description="This is not your lotto session.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

        pad = NumberPadView(self.user_id, self.guild_id, self.pool, parent_view=self)

        await interaction.response.send_message(
            embed=pad.get_embed(),
            view=pad,
            ephemeral=True
        )

    @discord.ui.button(label="Generate For Me", style=discord.ButtonStyle.success)
    async def generate(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Not Allowed",
                    description="This is not your lotto session.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

        await self.process_ticket(interaction, None, None)
