import discord
from discord.ext import commands
from db.connection import get_pool


def log(msg: str):
    print(f"[GOFREEME] {msg}", flush=True)


class GoFreeMeCreateModal(discord.ui.Modal, title="📝 Create Go Free Me"):
    reason = discord.ui.TextInput(
        label="Why should people help you?",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=250
    )

    def __init__(self, target_user: discord.User, guild_id: int):
        super().__init__()
        self.target_user = target_user
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        log("CreateModal.on_submit fired")

        pool = get_pool()
        async with pool.acquire() as conn:
            bail_row = await conn.fetchrow("""
                SELECT bail_total, bail_paid
                FROM user_bail
                WHERE discord_id = $1 AND guild_id = $2
            """, self.target_user.id, self.guild_id)

        if not bail_row:
            return await interaction.response.send_message(
                "No bail record found.", ephemeral=True
            )

        bail_total = bail_row["bail_total"]
        bail_paid = bail_row["bail_paid"]
        bail_remaining = bail_total - bail_paid

        if bail_remaining <= 0:
            return await interaction.response.send_message(
                "Your bail is already covered.", ephemeral=True
            )

        embed = discord.Embed(
            title="🪪 Go Free Me",
            description=(
                f"{self.target_user.mention} is locked up and needs help posting bail.\n\n"
                f"**Bail Needed:** ${bail_remaining/100:,.2f}\n\n"
                f"{self.reason.value if self.reason.value else '*No sob story provided.*'}"
            ),
            color=discord.Color.orange()
        )

        view = GoFreeMeContributionView(self.target_user.id, self.guild_id)

        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            "Your Go Free Me has been posted.", ephemeral=True
        )


class DeclineModal(discord.ui.Modal, title="Decline Go Free Me"):
    message = discord.ui.TextInput(
        label="Optional message",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=100
    )

    def __init__(self, target_user_id: int, guild_id: int):
        super().__init__()
        self.target_user_id = target_user_id
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):

        decline_msg = self.message.value.strip() if self.message.value else None

        if decline_msg:
            await interaction.response.send_message(
                f"You declined with message:\n> {decline_msg}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "You declined without a message.",
                ephemeral=True
            )

        channel = interaction.channel

        try:
            await channel.send(
                f"❌ **{interaction.user.mention} declined to contribute** "
                f"to <@{self.target_user_id}>'s Go Free Me.\n"
                f"{f'**Message:** {decline_msg}' if decline_msg else '*No message provided.*'}"
            )
        except Exception as e:
            print(f"[ERROR][DeclineModal] Failed to broadcast decline message: {e}")


class ContributeModal(discord.ui.Modal, title="Contribute to Go Free Me"):
    amount = discord.ui.TextInput(
        label="Contribution amount (in dollars)",
        required=True,
        max_length=10
    )
    message = discord.ui.TextInput(
        label="Optional message",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=100
    )

    def __init__(self, target_user_id: int, guild_id: int):
        super().__init__()
        self.target_user_id = target_user_id
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        log("ContributeModal.on_submit fired")

        try:
            dollars = float(self.amount.value)
            if dollars <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "Invalid amount.", ephemeral=True
            )

        contribution_cents = int(dollars * 100)
        pool = get_pool()

        async with pool.acquire() as conn:
            contributor = await conn.fetchrow("""
                SELECT checking_account_balance
                FROM users
                WHERE discord_id = $1 AND guild_id = $2
            """, interaction.user.id, interaction.guild.id)

        if not contributor:
            return await interaction.response.send_message(
                "You don't have an account.", ephemeral=True
            )

        checking = contributor["checking_account_balance"]
        if checking < contribution_cents:
            return await interaction.response.send_message(
                "Insufficient funds.", ephemeral=True
            )

        async with pool.acquire() as conn:
            bail_row = await conn.fetchrow("""
                SELECT bail_total, bail_paid
                FROM user_bail
                WHERE discord_id = $1 AND guild_id = $2
            """, self.target_user_id, self.guild_id)

        if not bail_row:
            return await interaction.response.send_message(
                "This Go Free Me is closed.", ephemeral=True
            )

        bail_total = bail_row["bail_total"]
        bail_paid = bail_row["bail_paid"]
        new_bail_paid = bail_paid + contribution_cents

        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE users
                SET checking_account_balance = $1
                WHERE discord_id = $2 AND guild_id = $3
            """, checking - contribution_cents, interaction.user.id, interaction.guild.id)

            await conn.execute("""
                UPDATE user_bail
                SET bail_paid = $1
                WHERE discord_id = $2 AND guild_id = $3
            """, new_bail_paid, self.target_user_id, self.guild_id)

            if new_bail_paid >= bail_total:

                await conn.execute("""
                    UPDATE users
                    SET is_incarcerated = FALSE
                    WHERE discord_id = $1 AND guild_id = $2
                """, self.target_user_id, self.guild_id)

                await conn.execute("""
                    DELETE FROM user_bail
                    WHERE discord_id = $1 AND guild_id = $2
                """, self.target_user_id, self.guild_id)

                await conn.execute("""
                    DELETE FROM user_criminal_record
                    WHERE discord_id = $1 AND guild_id = $2
                """, self.target_user_id, self.guild_id)

        progress_ratio = new_bail_paid / bail_total
        filled = int(progress_ratio * 20)
        empty = 20 - filled
        bar = "█" * filled + "░" * empty

        remaining = bail_total - new_bail_paid

        await interaction.channel.send(
            f"💸 {interaction.user.mention} contributed **${contribution_cents/100:,.2f}** "
            f"towards <@{self.target_user_id}>'s Go Free Me!\n"
            f"Message: {self.message.value or 'No message provided'}\n\n"
            f"**Progress:** ${new_bail_paid/100:,.2f} / ${bail_total/100:,.2f}\n"
            f"**Remaining:** ${remaining/100:,.2f}\n"
            f"`{bar}` **{progress_ratio*100:.1f}%**"
        )

        await interaction.response.send_message(
            f"You used money from your **checking account** to contribute.\n"
            f"Your updated checking balance is **${(checking - contribution_cents)/100:,.2f}**.",
            ephemeral=True
        )


class GoFreeMeContributionView(discord.ui.View):
    def __init__(self, target_user_id: int, guild_id: int):
        super().__init__(timeout=600)
        self.target_user_id = target_user_id
        self.guild_id = guild_id

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.grey, emoji="❌")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            DeclineModal(self.target_user_id, self.guild_id)
        )

    @discord.ui.button(label="Contribute", style=discord.ButtonStyle.green, emoji="💸")
    async def contribute(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            ContributeModal(self.target_user_id, self.guild_id)
        )


class CreateGoFreeMeButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Create Go Free Me",
            style=discord.ButtonStyle.blurple,
            emoji="🪪"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            GoFreeMeCreateModal(interaction.user, interaction.guild.id)
        )


class BribeDAButton(discord.ui.Button):
    def __init__(self, bail_amount):
        super().__init__(
            label=f"Bribe District Attorney (${bail_amount/100:,.2f})",
            style=discord.ButtonStyle.red,
            emoji="⚖️"
        )
        self.bail_amount = bail_amount

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()

        async with pool.acquire() as conn:
            user = await conn.fetchrow("""
                SELECT checking_account_balance,
                       savings_account_balance
                FROM users
                WHERE discord_id = $1 AND guild_id = $2
            """, interaction.user.id, interaction.guild.id)

        checking = user["checking_account_balance"] or 0
        savings = user["savings_account_balance"] or 0
        total = checking + savings

        if total < self.bail_amount:
            embed = discord.Embed(
                title="❌ Not Enough for the DA",
                description=(
                    "You don't have enough money to bribe the District Attorney.\n\n"
                    "Maybe it's time to start a **Go Free Me**."
                ),
                color=discord.Color.red()
            )

            view = discord.ui.View()
            view.add_item(CreateGoFreeMeButton())

            return await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        remaining = self.bail_amount

        original_checking = checking
        original_savings = savings

        if checking >= remaining:
            checking -= remaining
            remaining = 0
            account_used = "checking account"
        else:
            remaining -= checking
            checking = 0
            savings -= remaining
            account_used = "savings account"

        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE users
                SET checking_account_balance = $1,
                    savings_account_balance = $2,
                    is_incarcerated = FALSE
                WHERE discord_id = $3 AND guild_id = $4
            """, checking, savings, interaction.user.id, interaction.guild.id)

            await conn.execute("""
                DELETE FROM user_criminal_record
                WHERE discord_id = $1 AND guild_id = $2
            """, interaction.user.id, interaction.guild.id)

            await conn.execute("""
                DELETE FROM user_bail
                WHERE discord_id = $1 AND guild_id = $2
            """, interaction.user.id, interaction.guild.id)

        # ⭐ UPDATED — DA bribe now clearly shows bail payment
        await interaction.response.send_message(
            embed=discord.Embed(
                title="💵 DA Bribed Successfully",
                description=(
                    f"You used money from your **{account_used}** to pay off the DA.\n\n"
                    f"**Updated Balances:**\n"
                    f"•💰 Checking: ${checking/100:,.2f}\n"
                    f"•🏛️ Savings: ${savings/100:,.2f}\n\n"
                    "You're free again — stay out of trouble."
                ),
                color=discord.Color.green()
            ),
            ephemeral=True
        )


class GoFreeMe(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


async def setup(bot):
    await bot.add_cog(GoFreeMe(bot))
    log("GoFreeMe cog loaded")
