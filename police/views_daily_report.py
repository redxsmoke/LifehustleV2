import json
import random
import discord
from discord import ui, Embed
from db.connection import get_pool
from datetime import datetime
from zoneinfo import ZoneInfo


class DailyCrimeReportView(ui.View):
    def __init__(self, crimes, guild_id):
        super().__init__(timeout=None)
        self.crimes = crimes
        self.guild_id = guild_id
        self.index = 0

        if len(crimes) > 1:
            self.add_item(PrevButton())
            self.add_item(NextButton())

        self.add_item(ReportSuspectButton())

    # ------------------------------------------------------------
    # FETCH CLUES
    # ------------------------------------------------------------
    async def fetch_clues(self, crime_id):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT tip_data
                FROM police_crime_tips
                WHERE crime_id = $1
                  AND guild_id = $2
                  AND tip_type = 'auto_clue'
                ORDER BY timestamp ASC
            """, crime_id, self.guild_id)

        clues = []
        for r in rows:
            data = r["tip_data"]
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    continue
            if isinstance(data, dict) and "clue" in data:
                clues.append(data["clue"])
        return clues

    # ------------------------------------------------------------
    # BUILD EMBED PAGE
    # ------------------------------------------------------------
    async def build_page(self):
        crime = self.crimes[self.index]

        crime_id = crime["crime_id"]
        crime_type = crime["crime_type"]
        crime_date = crime["timestamp"]
        location = crime["location"]

        if crime_date.tzinfo is None:
            crime_date = crime_date.replace(tzinfo=ZoneInfo("UTC"))
        local_time = crime_date.astimezone(ZoneInfo("America/New_York"))
        formatted_time = local_time.strftime("%I:%M %p").lstrip("0")

        clues = await self.fetch_clues(crime_id)

        embed = Embed(
            title="🚨 Daily Crime Report",
            description=f"🗂️ **Case File #{crime_id}**\n\u200b",
            color=0xE74C3C
        )

        embed.add_field(
            name="📅 Time of Crime",
            value=f"{formatted_time} (Local Time)\n\u200b",
            inline=False
        )
        embed.add_field(
            name="📝 Crime Description",
            value=f"{crime_type}\n\u200b",
            inline=False
        )
        embed.add_field(
            name="📍 Location",
            value=f"{location}\n\u200b",
            inline=False
        )
        embed.add_field(
            name="🔎 Status",
            value="**Active Investigation**\n\u200b",
            inline=False
        )

        if clues:
            formatted_clues = "\n".join([f"• {c}" for c in clues])
        else:
            formatted_clues = "*No clues released yet.*"

        embed.add_field(
            name="🧩 Clues Released",
            value=f"{formatted_clues}\n\u200b",
            inline=False
        )

        embed.set_footer(text=f"Case {self.index + 1} of {len(self.crimes)}")

        return embed


# ------------------------------------------------------------
# REPORT SUSPECT FLOW
# ------------------------------------------------------------

class ReportSuspectButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Report Suspect",
            style=discord.ButtonStyle.danger,
            emoji="📨"
        )

    async def callback(self, interaction: discord.Interaction):
        view: DailyCrimeReportView = self.view
        crime = view.crimes[view.index]
        crime_id = crime["crime_id"]
        perp_id = crime.get("perpetrator_id")

        await interaction.response.send_modal(
            ReportSuspectModal(
                crime_id=crime_id,
                guild_id=view.guild_id,
                perp_id=perp_id,
                reporter_id=interaction.user.id
            )
        )


class ReportSuspectModal(ui.Modal, title="Report a Suspect"):
    suspect = ui.TextInput(
        label="Suspect (mention them)",
        placeholder="Type @ and select the suspect from the list",
        required=True,
        max_length=64
    )

    def __init__(self, crime_id: int, guild_id: int, perp_id: int, reporter_id: int):
        super().__init__()
        self.crime_id = crime_id
        self.guild_id = guild_id
        self.perp_id = perp_id
        self.reporter_id = reporter_id

    async def on_submit(self, interaction: discord.Interaction):
        raw = str(self.suspect).strip()

        # Expect something like <@123456789012345678>
        suspect_id = None
        try:
            cleaned = raw.replace("<", "").replace(">", "").replace("@", "").replace("!", "")
            suspect_id = int(cleaned)
        except Exception:
            await interaction.response.send_message(
                "❌ Please mention the suspect using @username so the police know who you mean.",
                ephemeral=True
            )
            return

        # Log the initial report
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO police_crime_tips (crime_id, guild_id, tip_type, tip_data)
                VALUES ($1, $2, 'user_report', $3::jsonb)
            """, self.crime_id, self.guild_id, json.dumps({
                "suspect_id": suspect_id,
                "suspect_mention": raw,
                "reporter": self.reporter_id
            }))

        # Polished warning text
        warning_text = (
            "🚨 **WARNING — FALSE REPORTS ARE A SERIOUS OFFENSE**\n\n"
            "The police take investigations very seriously.\n"
            "If you accuse an innocent person, you could face a hefty fine or even arrest.\n"
            "But if you're right, the police will reward you generously.\n\n"
            f"**Are you absolutely sure you want to report this suspect?**\n\n"
            f"Suspect: {raw}"
        )

        view = ConfirmReportView(
            crime_id=self.crime_id,
            guild_id=self.guild_id,
            perp_id=self.perp_id,
            suspect_id=suspect_id,
            reporter_id=self.reporter_id
        )

        await interaction.response.send_message(
            warning_text,
            view=view,
            ephemeral=True
        )


class ConfirmReportView(ui.View):
    def __init__(self, crime_id: int, guild_id: int, perp_id: int, suspect_id: int, reporter_id: int):
        super().__init__(timeout=60)
        self.crime_id = crime_id
        self.guild_id = guild_id
        self.perp_id = perp_id
        self.suspect_id = suspect_id
        self.reporter_id = reporter_id

        self.add_item(ConfirmReportButton())
        self.add_item(CancelReportButton())


class ConfirmReportButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Confirm Report",
            style=discord.ButtonStyle.danger
        )

    async def callback(self, interaction: discord.Interaction):
        view: ConfirmReportView = self.view

        pool = get_pool()
        async with pool.acquire() as conn:
            # Fetch reporter user record
            user_row = await conn.fetchrow("""
                SELECT checking_account_balance, xp
                FROM users
                WHERE discord_id = $1 AND guild_id = $2
            """, view.reporter_id, view.guild_id)

            if not user_row:
                await interaction.response.edit_message(
                    content="❌ You don't have a user record, so the police cannot process your report.",
                    view=None
                )
                return

            checking = user_row["checking_account_balance"] or 0
            current_xp = user_row["xp"] or 0

            # Base amounts in pennies ($1000 = 100000 pennies)
            base_money = 100000
            base_xp = 500

            if view.suspect_id == view.perp_id:
                # ------------------------------------------------------------
                # CORRECT REPORT → REWARD MONEY + XP
                # ------------------------------------------------------------
                money_multiplier = random.randint(1, 20)
                xp_multiplier = random.randint(1, 5)

                reward_money = base_money * money_multiplier
                reward_xp = base_xp * xp_multiplier

                new_balance = checking + reward_money
                new_xp = current_xp + reward_xp

                await conn.execute("""
                    UPDATE users
                    SET checking_account_balance = $1,
                        xp = $2
                    WHERE discord_id = $3 AND guild_id = $4
                """, new_balance, new_xp, view.reporter_id, view.guild_id)

                await interaction.response.edit_message(
                    content=(
                        f"✅ Your report was **correct**.\n\n"
                        f"💰 Money Reward: **${reward_money / 100:.2f}** "
                        f"(multiplier x{money_multiplier})\n"
                        f"⭐ XP Reward: **{reward_xp} XP** "
                        f"(multiplier x{xp_multiplier})"
                    ),
                    view=None
                )

            else:
                # ------------------------------------------------------------
                # WRONG REPORT → FINE OR JAIL
                # ------------------------------------------------------------
                fine_multiplier = random.randint(1, 10)
                fine = base_money * fine_multiplier
                new_balance = checking - fine

                if new_balance >= 0:
                    # They can pay the fine
                    await conn.execute("""
                        UPDATE users
                        SET checking_account_balance = $1
                        WHERE discord_id = $2 AND guild_id = $3
                    """, new_balance, view.reporter_id, view.guild_id)

                    await interaction.response.edit_message(
                        content=(
                            f"❌ Your report was **incorrect**.\n"
                            f"The police have fined you **${fine / 100:.2f}** "
                            f"(multiplier x{fine_multiplier})."
                        ),
                        view=None
                    )
                else:
                    # Cannot pay full fine → jail + bail
                    remaining = abs(new_balance)  # unpaid portion in pennies

                    await conn.execute("""
                        UPDATE users
                        SET checking_account_balance = 0,
                            cd_location_id = 8,
                            is_incarcerated = TRUE
                        WHERE discord_id = $1 AND guild_id = $2
                    """, view.reporter_id, view.guild_id)

                    await conn.execute("""
                        INSERT INTO user_bail (discord_id, guild_id, bail_total, bail_paid, is_active)
                        VALUES ($1, $2, $3, 0, TRUE)
                    """, view.reporter_id, view.guild_id, remaining)

                    await interaction.response.edit_message(
                        content=(
                            f"❌ Your report was **incorrect**, and you couldn't afford the fine.\n"
                            f"The police attempted to fine you **${fine / 100:.2f}** "
                            f"(multiplier x{fine_multiplier}), but you only had **${checking / 100:.2f}**.\n\n"
                            f"You have been sent to **jail**.\n"
                            f"Your remaining bail is **${remaining / 100:.2f}**."
                        ),
                        view=None
                    )


class CancelReportButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Cancel",
            style=discord.ButtonStyle.secondary
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="✅ Report cancelled. The police will ignore this suspect.",
            view=None
        )


# ------------------------------------------------------------
# NAVIGATION BUTTONS
# ------------------------------------------------------------

class PrevButton(ui.Button):
    def __init__(self):
        super().__init__(label="Previous", style=discord.ButtonStyle.secondary, emoji="⬅️")

    async def callback(self, interaction: discord.Interaction):
        view: DailyCrimeReportView = self.view
        view.index = (view.index - 1) % len(view.crimes)
        embed = await view.build_page()
        await interaction.response.edit_message(embed=embed, view=view)


class NextButton(ui.Button):
    def __init__(self):
        super().__init__(label="Next", style=discord.ButtonStyle.secondary, emoji="➡️")

    async def callback(self, interaction: discord.Interaction):
        view: DailyCrimeReportView = self.view
        view.index = (view.index + 1) % len(view.crimes)
        embed = await view.build_page()
        await interaction.response.edit_message(embed=embed, view=view)
