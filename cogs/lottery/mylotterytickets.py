import asyncio
import traceback
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from db.connection import get_pool

MONEY = "💰"


def log_error(prefix: str, error: Exception):
    print(f"[LotteryError] {prefix}: {error}")
    traceback.print_exc()


def fmt_number(n: int) -> str:
    return f"{n:02d}"


def fmt_money_cents(amount: int) -> str:
    return f"${amount / 100:,.2f}"


class TicketStatus:
    ACTIVE = "active"
    LOST = "lose"
    WINNER = "winner"
    CLAIMED = "claimed"


class TicketRecord:
    def __init__(self, row, is_winning: bool):
        self.is_winning = is_winning

        if is_winning:
            self.winning_ticket_id = row["winning_ticket_id"]
            self.lottery_results_id = row["lottery_results_id"]
            self.draw_date = row["draw_date"]
            self.discord_id = row["discord_id"]
            self.guild_id = row["guild_id"]
            self.num1 = row["num1"]
            self.num2 = row["num2"]
            self.num3 = row["num3"]
            self.num4 = row["num4"]
            self.num5 = row["num5"]
            self.powerball = row["powerball"]
            self.amount_won = row["amount_won"]
            self.paid = row["paid"]
            self.status = row["status"]
            self.ticket_status = (
                TicketStatus.WINNER if not self.paid else TicketStatus.CLAIMED
            )
        else:
            self.lottery_ticket_id = row["lottery_ticket_id"]
            self.lottery_results_id = row["lottery_results_id"]
            self.draw_date = row["draw_date"]
            self.discord_id = row["discord_id"]
            self.guild_id = row["guild_id"]
            self.num1 = row["num1"]
            self.num2 = row["num2"]
            self.num3 = row["num3"]
            self.num4 = row["num4"]
            self.num5 = row["num5"]
            self.powerball = row["powerball"]
            self.ticket_status = row["ticket_status"]


# ---------------------------------------------------------
# SAFE EMBED FIELD CHUNKING
# ---------------------------------------------------------

def add_safe_field(embed: discord.Embed, name: str, text: str):
    """Ensures embed fields never exceed Discord's 1024-character limit."""
    if len(text) <= 1024:
        embed.add_field(name=name, value=text, inline=False)
        return

    chunks = [text[i:i+1024] for i in range(0, len(text), 1024)]
    for idx, chunk in enumerate(chunks):
        embed.add_field(
            name=f"{name} (Part {idx+1})",
            value=chunk,
            inline=False
        )


class TicketStatusSelect(discord.ui.Select):
    def __init__(self, current_status: str):
        options = [
            discord.SelectOption(label="Active", value=TicketStatus.ACTIVE),
            discord.SelectOption(label="Lost", value=TicketStatus.LOST),
            discord.SelectOption(label="Winner", value=TicketStatus.WINNER),
            discord.SelectOption(label="Claimed", value=TicketStatus.CLAIMED),
        ]
        super().__init__(
            placeholder="Select ticket status",
            min_values=1,
            max_values=1,
            options=options,
        )

        for opt in self.options:
            if opt.value == current_status:
                opt.default = True

    async def callback(self, interaction: discord.Interaction):
        try:
            view: "TicketView" = self.view  # type: ignore
            if interaction.user.id != view.user.id:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⛔ Not Allowed",
                        description="This view is not for you.",
                        color=discord.Color.red(),
                    ),
                    ephemeral=True,
                )

            view.status = self.values[0]
            view.page = 0
            await view.refresh(interaction)
        except Exception as e:
            log_error("TicketStatusSelect.callback", e)
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⚠️ Error",
                        description="Error switching status.",
                        color=discord.Color.red(),
                    ),
                    ephemeral=True,
                )
            except:
                pass


class TicketClaimSelect(discord.ui.Select):
    def __init__(self, tickets: List[TicketRecord]):
        options = []
        for t in tickets[:25]:
            # ⭐ CHANGED: replaced draw_date with Draw ID
            label = (
                f"Draw ID: {t.lottery_results_id} - "
                f"{fmt_number(t.num1)} {fmt_number(t.num2)} {fmt_number(t.num3)} "
                f"{fmt_number(t.num4)} {fmt_number(t.num5)} PB {fmt_number(t.powerball)}"
            )

            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(t.winning_ticket_id),
                )
            )

        super().__init__(
            placeholder="Select a winning ticket to claim",
            min_values=1,
            max_values=1,
            options=options,
        )


    async def callback(self, interaction: discord.Interaction):
        try:
            view: "TicketView" = self.view  # type: ignore
            if interaction.user.id != view.user.id:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⛔ Not Allowed",
                        description="This view is not for you.",
                        color=discord.Color.red(),
                    ),
                    ephemeral=True,
                )

            winning_ticket_id = int(self.values[0])
            await view.handle_claim(interaction, winning_ticket_id)
        except Exception as e:
            log_error("TicketClaimSelect.callback", e)
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⚠️ Error",
                        description="Error claiming ticket.",
                        color=discord.Color.red(),
                    ),
                    ephemeral=True,
                )
            except:
                pass


class TicketView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        user: discord.User,
        guild: discord.Guild,
        status: str,
    ):
        super().__init__(timeout=300)
        self.bot = bot
        self.user = user
        self.guild = guild
        self.status = status
        self.page = 0
        self.per_page = 25
        self.tickets: List[TicketRecord] = []

        self.add_item(TicketStatusSelect(status))

    async def fetch_tickets(self):
        try:
            pool = get_pool()
            async with pool.acquire() as conn:
                if self.status == TicketStatus.ACTIVE:
                    rows = await conn.fetch(
                        """
                        SELECT lottery_results_id, lottery_ticket_id, discord_id, guild_id,
                               draw_date, num1, num2, num3, num4, num5, powerball,
                               ticket_status
                        FROM lottery
                        WHERE discord_id = $1
                          AND guild_id = $2
                          AND ticket_status = 'active'
                        ORDER BY draw_date DESC, lottery_ticket_id DESC
                        """,
                        self.user.id,
                        self.guild.id,
                    )
                    self.tickets = [TicketRecord(r, False) for r in rows]

                elif self.status == TicketStatus.LOST:
                    rows = await conn.fetch(
                        """
                        SELECT lottery_results_id, lottery_ticket_id, discord_id, guild_id,
                               draw_date, num1, num2, num3, num4, num5, powerball,
                               ticket_status
                        FROM lottery
                        WHERE discord_id = $1
                          AND guild_id = $2
                          AND ticket_status = 'lost'
                        ORDER BY draw_date DESC, lottery_ticket_id DESC
                        """,
                        self.user.id,
                        self.guild.id,
                    )
                    self.tickets = [TicketRecord(r, False) for r in rows]

                elif self.status == TicketStatus.WINNER:
                    rows = await conn.fetch(
                        """
                        SELECT winning_ticket_id, lottery_results_id, draw_date,
                               num1, num2, num3, num4, num5, powerball,
                               amount_won, discord_id, guild_id,
                               paid, paid_date, status
                        FROM winning_lottery_tickets
                        WHERE discord_id = $1
                          AND guild_id = $2
                          AND paid = FALSE
                        ORDER BY draw_date DESC, winning_ticket_id DESC
                        """,
                        self.user.id,
                        self.guild.id,
                    )
                    self.tickets = [TicketRecord(r, True) for r in rows]

                elif self.status == TicketStatus.CLAIMED:
                    rows = await conn.fetch(
                        """
                        SELECT winning_ticket_id, lottery_results_id, draw_date,
                               num1, num2, num3, num4, num5, powerball,
                               amount_won, discord_id, guild_id,
                               paid, paid_date, status
                        FROM winning_lottery_tickets
                        WHERE discord_id = $1
                          AND guild_id = $2
                          AND status = 'claimed'
                        ORDER BY paid_date DESC, winning_ticket_id DESC
                        """,
                        self.user.id,
                        self.guild.id,
                    )
                    self.tickets = [TicketRecord(r, True) for r in rows]

        except Exception as e:
            log_error("TicketView.fetch_tickets", e)
            self.tickets = []

    def get_page_tickets(self) -> List[TicketRecord]:
        start = self.page * self.per_page
        end = start + self.per_page
        return self.tickets[start:end]

    def build_embed(self) -> discord.Embed:
        try:
            total_pages = max(1, (len(self.tickets) - 1) // self.per_page + 1)

            embed = discord.Embed(
                title=f"{MONEY} My Lottery Tickets",
                description=(
                    f"**Status:** {self.status.capitalize()}\n"
                    f"**Page:** {self.page + 1}/{total_pages}"
                ),
                color=discord.Color.gold(),
            )

            page_tickets = self.get_page_tickets()

            if not page_tickets:
                note = (
                    "All losing lottery tickets are automatically deleted after 2 weeks."
                    if self.status == TicketStatus.LOST
                    else "No tickets found for this status."
                )
                embed.add_field(name="Tickets", value=note, inline=False)
                return embed

            lines = []
            for t in page_tickets:
                nums = sorted([t.num1, t.num2, t.num3, t.num4, t.num5])
                num_string = ", ".join(fmt_number(n) for n in nums)
                pb_string = fmt_number(t.powerball)

                status_label = (
                    "Active"
                    if self.status == TicketStatus.ACTIVE
                    else "Lost"
                    if self.status == TicketStatus.LOST
                    else "Winner"
                    if self.status == TicketStatus.WINNER
                    else "Claimed"
                )

                line = (
                    f"**Draw ID:** {t.lottery_results_id}\n"
                    f"**Draw Date:** {t.draw_date}\n"
                    f"**Numbers:** {num_string} | PB {pb_string}\n"
                    f"**Status:** {status_label}\n"
                    f"────────────────────"
                )
                lines.append(line)

            add_safe_field(embed, "Tickets", "\n".join(lines))

            return embed

        except Exception as e:
            log_error("TicketView.build_embed", e)
            return discord.Embed(
                title="My Lottery Tickets",
                description="⚠️ Error building ticket view.",
                color=discord.Color.red(),
            )

    async def refresh(self, interaction: discord.Interaction):
        try:
            await self.fetch_tickets()

            # Remove old status selector
            for item in list(self.children):
                if isinstance(item, TicketStatusSelect):
                    self.remove_item(item)

            # Add fresh status selector
            self.add_item(TicketStatusSelect(self.status))

            # Remove old claim selectors
            for item in list(self.children):
                if isinstance(item, TicketClaimSelect):
                    self.remove_item(item)

            page_tickets = self.get_page_tickets()

            # Add claim selector only for winners
            if self.status == TicketStatus.WINNER and page_tickets:
                self.add_item(TicketClaimSelect(page_tickets))

            await interaction.response.edit_message(
                embed=self.build_embed(),
                view=self
            )

        except Exception as e:
            log_error("TicketView.refresh", e)
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⚠️ Error",
                        description="Error refreshing view.",
                        color=discord.Color.red(),
                    ),
                    ephemeral=True,
                )
            except:
                pass

        except Exception as e:
            log_error("TicketView.refresh", e)
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⚠️ Error",
                        description="Error refreshing view.",
                        color=discord.Color.red(),
                    ),
                    ephemeral=True,
                )
            except:
                pass

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        try:
            if interaction.user.id != self.user.id:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⛔ Not Allowed",
                        description="This view is not for you.",
                        color=discord.Color.red(),
                    ),
                    ephemeral=True,
                )

            if self.page > 0:
                self.page -= 1

            await self.refresh(interaction)
        except Exception as e:
            log_error("TicketView.previous_page", e)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        try:
            if interaction.user.id != self.user.id:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⛔ Not Allowed",
                        description="This view is not for you.",
                        color=discord.Color.red(),
                    ),
                    ephemeral=True,
                )

            max_page = max(0, (len(self.tickets) - 1) // self.per_page)
            if self.page < max_page:
                self.page += 1

            await self.refresh(interaction)
        except Exception as e:
            log_error("TicketView.next_page", e)

    @discord.ui.button(label="Delete Losing Tickets", style=discord.ButtonStyle.danger)
    async def delete_lost(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        try:
            if interaction.user.id != self.user.id:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⛔ Not Allowed",
                        description="This view is not for you.",
                        color=discord.Color.red(),
                    ),
                    ephemeral=True,
                )

            pool = get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    DELETE FROM lottery
                    WHERE discord_id = $1
                      AND guild_id = $2
                      AND ticket_status = 'lost'
                    """,
                    self.user.id,
                    self.guild.id,
                )

            embed = discord.Embed(
                title="🗑️ Losing Tickets Deleted",
                description=(
                    "All losing tickets have been removed.\n\n"
                    "Note: Losing tickets auto-delete after 2 weeks."
                ),
                color=discord.Color.red(),
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

            await self.fetch_tickets()

            if interaction.message:
                await interaction.message.edit(
                    embed=self.build_embed(),
                    view=self
                )
        except Exception as e:
            log_error("TicketView.delete_lost", e)

    async def handle_claim(
        self, interaction: discord.Interaction,
        winning_ticket_id: int
    ):
        try:
            pool = get_pool()
            async with pool.acquire() as conn:
                ticket_row = await conn.fetchrow(
                    """
                    SELECT winning_ticket_id, lottery_results_id, draw_date,
                           num1, num2, num3, num4, num5, powerball,
                           amount_won, discord_id, guild_id,
                           paid, paid_date, status
                    FROM winning_lottery_tickets
                    WHERE winning_ticket_id = $1
                      AND discord_id = $2
                      AND guild_id = $3
                    """,
                    winning_ticket_id,
                    self.user.id,
                    self.guild.id,
                )

                if not ticket_row:
                    return await interaction.response.send_message(
                        embed=discord.Embed(
                            title="❌ Ticket Not Found",
                            description="That winning ticket could not be found.",
                            color=discord.Color.red(),
                        ),
                        ephemeral=True,
                    )

                if ticket_row["paid"]:
                    return await interaction.response.send_message(
                        embed=discord.Embed(
                            title="✅ Already Claimed",
                            description="This ticket has already been claimed.",
                            color=discord.Color.green(),
                        ),
                        ephemeral=True,
                    )

                user_row = await conn.fetchrow(
                    """
                    SELECT savings_account_balance,
                           checking_account_balance,
                           max_savings_amount
                    FROM users
                    WHERE discord_id = $1
                      AND guild_id = $2
                    """,
                    self.user.id,
                    self.guild.id,
                )

                if not user_row:
                    return await interaction.response.send_message(
                        embed=discord.Embed(
                            title="❌ Account Not Found",
                            description="Your user account could not be found.",
                            color=discord.Color.red(),
                        ),
                        ephemeral=True,
                    )

                savings = user_row["savings_account_balance"]
                checking = user_row["checking_account_balance"]
                max_savings = user_row["max_savings_amount"]

                amount_won = int(ticket_row["amount_won"])

                deposit_to_savings = 0
                deposit_to_checking = 0

                if savings + amount_won <= max_savings:
                    savings += amount_won
                    deposit_to_savings = amount_won
                else:
                    space_left = max_savings - savings
                    if space_left < 0:
                        space_left = 0

                    savings = max_savings
                    overflow = amount_won - space_left
                    checking += overflow

                    deposit_to_savings = space_left
                    deposit_to_checking = overflow

                await conn.execute(
                    """
                    UPDATE users
                    SET savings_account_balance = $1,
                        checking_account_balance = $2
                    WHERE discord_id = $3
                      AND guild_id = $4
                    """,
                    savings,
                    checking,
                    self.user.id,
                    self.guild.id,
                )

                await conn.execute(
                    """
                    UPDATE winning_lottery_tickets
                    SET paid = TRUE,
                        paid_date = NOW(),
                        status = 'claimed'
                    WHERE winning_ticket_id = $1
                    """,
                    winning_ticket_id,
                )

            savings_maxed = savings >= max_savings

            embed = discord.Embed(
                title=f"{MONEY} Prize Claimed! {MONEY}",
                color=discord.Color.green(),
            )

            embed.add_field(
                name="Total Winnings",
                value=f"**{fmt_money_cents(amount_won)}**",
                inline=False,
            )

            embed.add_field(
                name="Deposited into Savings",
                value=fmt_money_cents(deposit_to_savings),
                inline=True,
            )

            embed.add_field(
                name="Deposited into Checking",
                value=fmt_money_cents(deposit_to_checking),
                inline=True,
            )

            savings_text = fmt_money_cents(savings)
            if savings_maxed:
                savings_text += " (MAXED)"

            embed.add_field(
                name="Updated Savings Balance",
                value=savings_text,
                inline=False,
            )

            embed.add_field(
                name="Updated Checking Balance",
                value=fmt_money_cents(checking),
                inline=False,
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

            # Switch to claimed filter and refresh main message
            self.status = TicketStatus.CLAIMED
            self.page = 0
            await self.fetch_tickets()

            # Reset status selector
            for item in list(self.children):
                if isinstance(item, TicketStatusSelect):
                    self.remove_item(item)
            self.add_item(TicketStatusSelect(self.status))

            # Remove old claim selectors
            for item in list(self.children):
                if isinstance(item, TicketClaimSelect):
                    self.remove_item(item)

            page_tickets = self.get_page_tickets()
            if self.status == TicketStatus.CLAIMED and page_tickets:
                self.add_item(TicketClaimSelect(page_tickets))

            try:
                if interaction.message:
                    await interaction.message.edit(
                        embed=self.build_embed(),
                        view=self
                    )
            except Exception as e2:
                log_error("TicketView.handle_claim.message_edit", e2)

        except Exception as e:
            log_error("TicketView.handle_claim", e)
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⚠️ Error",
                        description="A database error occurred while claiming your prize.",
                        color=discord.Color.red(),
                    ),
                    ephemeral=True,
                )
            except:
                pass


class MyLotteryTickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="mylotterytickets",
        description="View your lottery tickets.",
    )
    async def mylotterytickets(self, interaction: discord.Interaction):
        try:
            if not interaction.guild:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Server Only",
                        description="This command can only be used in a server.",
                        color=discord.Color.red(),
                    ),
                    ephemeral=True,
                )

            view = TicketView(
                bot=self.bot,
                user=interaction.user,
                guild=interaction.guild,
                status=TicketStatus.ACTIVE,
            )

            await view.fetch_tickets()

            await interaction.response.send_message(
                embed=view.build_embed(),
                view=view,
                ephemeral=True
            )

        except Exception as e:
            log_error("MyLotteryTickets.mylotterytickets", e)
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⚠️ Error",
                        description="An internal error occurred while loading your tickets.",
                        color=discord.Color.red(),
                    ),
                    ephemeral=True,
                )
            except:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(MyLotteryTickets(bot))

