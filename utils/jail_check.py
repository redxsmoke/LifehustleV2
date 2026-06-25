import discord
from db.connection import get_pool

# Import buttons from GoFreeMe system
from cogs.gofreeme import BribeDAButton, CreateGoFreeMeButton

# Item IDs
GET_OUT_OF_JAIL_FREE_CARD_ID = 10
BAIL_COUPON_ITEM_ID = 14


class UseJailCardButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Use Escape Jail",
            style=discord.ButtonStyle.green,
            emoji="🃏"
        )

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT quantity
                FROM user_items
                WHERE discord_id = $1 AND guild_id = $2 AND item_id = $3
            """, interaction.user.id, interaction.guild.id, GET_OUT_OF_JAIL_FREE_CARD_ID)

            if not row or row["quantity"] <= 0:
                return await interaction.response.send_message(
                    "You don't have a Get Out of Jail Free Card.",
                    ephemeral=True
                )

            await conn.execute("""
                UPDATE user_items
                SET quantity = quantity - 1
                WHERE discord_id = $1 AND guild_id = $2 AND item_id = $3
            """, interaction.user.id, interaction.guild.id, GET_OUT_OF_JAIL_FREE_CARD_ID)

            await conn.execute("""
                UPDATE users
                SET is_incarcerated = FALSE
                WHERE discord_id = $1 AND guild_id = $2
            """, interaction.user.id, interaction.guild.id)

            await conn.execute("""
                DELETE FROM user_bail
                WHERE discord_id = $1 AND guild_id = $2
            """, interaction.user.id, interaction.guild.id)

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🃏 You're Free!",
                description="Your **Escape Jail** card has been used. You're no longer incarcerated.",
                color=discord.Color.green()
            ),
            ephemeral=True
        )


class BailCouponButton(discord.ui.Button):
    def __init__(self, bail_remaining):
        super().__init__(
            label="Use Bail Coupon (Save 50%)",
            style=discord.ButtonStyle.green,
            emoji="🧾"
        )
        self.bail_remaining = bail_remaining

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT quantity
                FROM user_items
                WHERE discord_id = $1 AND guild_id = $2 AND item_id = $3
            """, interaction.user.id, interaction.guild.id, BAIL_COUPON_ITEM_ID)

            if not row or row["quantity"] <= 0:
                return await interaction.response.send_message(
                    "You don't have a Bail Coupon.",
                    ephemeral=True
                )

            original_bail = self.bail_remaining
            discounted_bail = original_bail // 2

            user_row = await conn.fetchrow("""
                SELECT checking_account_balance, savings_account_balance
                FROM users
                WHERE discord_id = $1 AND guild_id = $2
            """, interaction.user.id, interaction.guild.id)

            checking = user_row["checking_account_balance"]
            savings = user_row["savings_account_balance"]
            total = checking + savings

            if total < discounted_bail:
                return await interaction.response.send_message(
                    "You don't have enough money to use the Bail Coupon.",
                    ephemeral=True
                )

            remaining = discounted_bail

            if checking >= remaining:
                checking -= remaining
                remaining = 0
            else:
                remaining -= checking
                checking = 0
                savings -= remaining

            await conn.execute("""
                UPDATE user_items
                SET quantity = quantity - 1
                WHERE discord_id = $1 AND guild_id = $2 AND item_id = $3
            """, interaction.user.id, interaction.guild.id, BAIL_COUPON_ITEM_ID)

            await conn.execute("""
                UPDATE users
                SET checking_account_balance = $1,
                    savings_account_balance = $2,
                    is_incarcerated = FALSE
                WHERE discord_id = $3 AND guild_id = $4
            """, checking, savings, interaction.user.id, interaction.guild.id)

            await conn.execute("""
                DELETE FROM user_bail
                WHERE discord_id = $1 AND guild_id = $2
            """, interaction.user.id, interaction.guild.id)

            await conn.execute("""
                DELETE FROM user_criminal_record
                WHERE discord_id = $1 AND guild_id = $2
            """, interaction.user.id, interaction.guild.id)

        embed = discord.Embed(
            title="🧾 Bail Coupon Used!",
            description=(
                f"You received **50% off** your bail.\n\n"
                f"**Original Bail:** ${original_bail/100:,.2f}\n"
                f"**Your Cost:** ${discounted_bail/100:,.2f}\n\n"
                f"You're now free!"
            ),
            color=discord.Color.green()
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


class JailView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int, bail_remaining: int, has_jail_card: bool, has_bail_coupon: bool):
        super().__init__(timeout=None)

        self.add_item(BribeDAButton(bail_remaining))
        self.add_item(CreateGoFreeMeButton())

        if has_jail_card:
            self.add_item(UseJailCardButton())

        if has_bail_coupon:
            self.add_item(BailCouponButton(bail_remaining))


async def check_if_in_jail(interaction: discord.Interaction) -> bool:
    pool = get_pool()

    async with pool.acquire() as conn:
        user = await conn.fetchrow("""
            SELECT is_incarcerated
            FROM users
            WHERE discord_id = $1 AND guild_id = $2
        """, interaction.user.id, interaction.guild.id)

        if not user or not user["is_incarcerated"]:
            return False

        bail_row = await conn.fetchrow("""
            SELECT bail_total, bail_paid
            FROM user_bail
            WHERE discord_id = $1 AND guild_id = $2
        """, interaction.user.id, interaction.guild.id)

        bail_total = bail_row["bail_total"] if bail_row else 0
        bail_paid = bail_row["bail_paid"] if bail_row else 0
        bail_remaining = max(bail_total - bail_paid, 0)

        jail_card_row = await conn.fetchrow("""
            SELECT quantity
            FROM user_items
            WHERE discord_id = $1 AND guild_id = $2 AND item_id = $3
        """, interaction.user.id, interaction.guild.id, GET_OUT_OF_JAIL_FREE_CARD_ID)

        has_jail_card = jail_card_row and jail_card_row["quantity"] > 0

        bail_coupon_row = await conn.fetchrow("""
            SELECT quantity
            FROM user_items
            WHERE discord_id = $1 AND guild_id = $2 AND item_id = $3
        """, interaction.user.id, interaction.guild.id, BAIL_COUPON_ITEM_ID)

        has_bail_coupon = bail_coupon_row and bail_coupon_row["quantity"] > 0

    embed = discord.Embed(
        title="🚔 You Are Incarcerated",
        description=(
            f"**Bail Remaining:** ${bail_remaining/100:,.2f}\n\n"
            "You cannot perform this action while in jail.\n\n"
            "**Options:**\n"
            "• Bribe the District Attorney\n"
            "• Create a Go Free Me\n"
            "• Use a Get Out of Jail Free Card\n"
            "• Use a Bail Coupon (50% off bail)"
        ),
        color=discord.Color.red()
    )

    view = JailView(
        user_id=interaction.user.id,
        guild_id=interaction.guild.id,
        bail_remaining=bail_remaining,
        has_jail_card=has_jail_card,
        has_bail_coupon=has_bail_coupon
    )

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    return True
