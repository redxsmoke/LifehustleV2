import json
import random
import unicodedata
import logging
import discord
from discord import ui, Embed
from db.connection import get_pool
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger("police.report_suspect")
logger.setLevel(logging.DEBUG)

# ------------------------------------------------------------
# UTILITY
# ------------------------------------------------------------
def normalize(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()

async def safe_respond(interaction: discord.Interaction, *, content=None, embed=None, view=None, ephemeral=True):
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(content=content, embed=embed, view=view, ephemeral=ephemeral)
        else:
            return await interaction.followup.send(content=content, embed=embed, view=view, ephemeral=ephemeral)
    except Exception:
        try:
            await interaction.edit_original_response(content=content or "", embed=embed, view=view)
        except Exception:
            pass

# ------------------------------------------------------------
# PAGINATION BUTTONS
# ------------------------------------------------------------
class PrevButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="◀️ Prev")

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.index = max(0, view.index - 1)
        embed = await view.build_page()
        await interaction.response.edit_message(embed=embed, view=view)

class NextButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="Next ▶️")

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.index = min(len(view.crimes) - 1, view.index + 1)
        embed = await view.build_page()
        await interaction.response.edit_message(embed=embed, view=view)

# ------------------------------------------------------------
# MAIN DAILY REPORT VIEW
# ------------------------------------------------------------
class DailyCrimeReportView(ui.View):
    def __init__(self, crimes, guild_id, stage_number):
        super().__init__(timeout=None)
        self.crimes = crimes or []
        self.guild_id = guild_id
        self.stage_number = stage_number
        self.index = 0

        if len(self.crimes) > 1:
            self.add_item(PrevButton())
            self.add_item(NextButton())

        self.add_item(ReportSuspectButton(self.stage_number))
        self.add_item(AnonymousReportButton(self.stage_number))

    async def fetch_clues(self, crime_id):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT tip_data
                FROM police_crime_tips
                WHERE crime_id = $1 AND guild_id = $2 AND tip_type = 'auto_clue'
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

    async def build_page(self):
        if not self.crimes:
            embed = Embed(title="🚨 Daily Crime Report", description="No active cases.", color=0xE74C3C)
            embed.set_footer(text="Case 0 of 0")
            return embed

        crime = self.crimes[self.index]
        crime_id = crime.get("crime_id")
        crime_type = crime.get("crime_type", "Unknown crime")
        crime_date = crime.get("timestamp", datetime.utcnow())
        location = crime.get("location", "Unknown location")

        if isinstance(crime_date, datetime) and crime_date.tzinfo is None:
            crime_date = crime_date.replace(tzinfo=ZoneInfo("UTC"))

        try:
            local_time = crime_date.astimezone(ZoneInfo("America/New_York"))
            formatted_time = local_time.strftime("%I:%M %p").lstrip("0")
        except Exception:
            formatted_time = "Unknown time"

        clues = await self.fetch_clues(crime_id)

        embed = Embed(
            title="🚨 Daily Crime Report",
            description=f"🗂️ **Case File #{crime_id}**\n\u200b",
            color=0xE74C3C
        )

        embed.add_field(name="📅 Time of Crime", value=f"{formatted_time}\n\u200b", inline=False)
        embed.add_field(name="📝 Crime Description", value=f"{crime_type}\n\u200b", inline=False)
        embed.add_field(name="📍 Location", value=f"{location}\n\u200b", inline=False)

        if clues:
            embed.add_field(name="🧩 Clues Released", value="\n".join(f"• {c}" for c in clues), inline=False)
        else:
            embed.add_field(name="🧩 Clues Released", value="*No clues released yet.*", inline=False)

        embed.set_footer(text=f"Case {self.index + 1} of {len(self.crimes)}")
        return embed
# ------------------------------------------------------------
# REPORT SUSPECT BUTTON
# ------------------------------------------------------------
class ReportSuspectButton(ui.Button):
    def __init__(self, stage_number):
        self.stage_number = stage_number
        super().__init__(label="Report Suspect", style=discord.ButtonStyle.danger, emoji="📨")

    async def callback(self, interaction: discord.Interaction):
        view: DailyCrimeReportView = self.view
        crime = view.crimes[view.index]

        await interaction.response.send_modal(
            ReportSuspectModal(
                crime_id=crime["crime_id"],
                guild_id=view.guild_id,
                perp_id=crime["perpetrator_id"],
                reporter_id=interaction.user.id,
                is_anonymous=False,
                stage_number=self.stage_number
            )
        )

# ------------------------------------------------------------
# ANONYMOUS REPORT BUTTON
# ------------------------------------------------------------
class AnonymousReportButton(ui.Button):
    def __init__(self, stage_number):
        self.stage_number = stage_number
        super().__init__(label="Anonymous Report", style=discord.ButtonStyle.primary, emoji="🕵️")

    async def callback(self, interaction: discord.Interaction):
        view: DailyCrimeReportView = self.view

        pool = get_pool()
        async with pool.acquire() as conn:
            item_row = await conn.fetchrow("""
                SELECT quantity
                FROM user_items
                WHERE discord_id = $1 AND guild_id = $2 AND item_id = 16
            """, interaction.user.id, view.guild_id)

        if not item_row or item_row.get("quantity", 0) <= 0:
            await safe_respond(interaction, content="❌ You do not own an **Anonymous Report** item.", ephemeral=True)
            return

        crime = view.crimes[view.index]

        await interaction.response.send_modal(
            ReportSuspectModal(
                crime_id=crime["crime_id"],
                guild_id=view.guild_id,
                perp_id=crime["perpetrator_id"],
                reporter_id=interaction.user.id,
                is_anonymous=True,
                stage_number=self.stage_number
            )
        )

# ------------------------------------------------------------
# REPORT SUSPECT MODAL
# ------------------------------------------------------------
class ReportSuspectModal(ui.Modal):
    def __init__(self, crime_id, guild_id, perp_id, reporter_id, is_anonymous=False, stage_number=0):
        super().__init__(title="Report a Suspect")

        self.crime_id = crime_id
        self.guild_id = guild_id
        self.perp_id = perp_id
        self.reporter_id = reporter_id
        self.is_anonymous = is_anonymous
        self.stage_number = stage_number

        self.suspect = ui.TextInput(
            label="Suspect nickname (not @mention)",
            placeholder="Type part of their nickname",
            required=True,
            max_length=64
        )

        self.add_item(self.suspect)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            raw = self.suspect.value or ""
            query = normalize(raw.strip())

            guild = interaction.guild
            if guild is None:
                await safe_respond(interaction, content="❌ Cannot search for suspects outside a server.", ephemeral=True)
                return

            matches = []
            for member in guild.members:
                nickname = member.display_name or ""
                username = member.name or ""

                n_norm = normalize(nickname)
                u_norm = normalize(username)

                if (
                    query == n_norm
                    or query in n_norm
                    or query == u_norm
                    or query in u_norm
                ):
                    matches.append(member)

            if len(matches) == 0:
                await safe_respond(interaction, content="❌ No suspects found. Try typing more of their nickname.", ephemeral=True)
                return

            if len(matches) == 1:
                await self.send_confirmation(interaction, matches[0])
                return

            if len(matches) > 25:
                await safe_respond(interaction, content="❌ Too many matches found. Please type more of the nickname.", ephemeral=True)
                return

            view = SuspectSelectView(
                matches=matches,
                crime_id=self.crime_id,
                guild_id=self.guild_id,
                perp_id=self.perp_id,
                reporter_id=self.reporter_id,
                is_anonymous=self.is_anonymous,
                stage_number=self.stage_number
            )

            await safe_respond(interaction, content="Multiple suspects found. Please select the correct one:", view=view, ephemeral=True)

        except Exception as e:
            logger.exception(f"[ReportSuspectModal] on_submit error: {e}")
            await safe_respond(interaction, content="❌ Something went wrong while processing your report.", ephemeral=True)

    async def send_confirmation(self, interaction: discord.Interaction, suspect: discord.Member):
        try:
            if suspect.id == self.reporter_id:
                embed = Embed(
                    title="❌ You can’t report yourself",
                    description=(
                        "🚓 **The cops stared at you like you just licked a light socket.**\n\n"
                        "You cannot report yourself."
                    ),
                    color=0xE74C3C
                )
                await safe_respond(interaction, embed=embed, ephemeral=True)
                return

            warning_text = (
                "🚨 **WARNING — FALSE REPORTS ARE A SERIOUS OFFENSE**\n\n"
                "If you accuse an innocent person, you could face a hefty fine or even arrest.\n"
                "But if you're right, the police will reward you generously.\n\n"
                f"**Are you sure you want to report this suspect?**\n\n"
                f"Suspect: **{suspect.display_name} ({suspect.name})**"
            )

            view = ConfirmReportView(
                crime_id=self.crime_id,
                guild_id=self.guild_id,
                perp_id=self.perp_id,
                suspect_id=suspect.id,
                reporter_id=self.reporter_id,
                is_anonymous=self.is_anonymous,
                stage_number=self.stage_number
            )

            await safe_respond(interaction, content=warning_text, view=view, ephemeral=True)

        except Exception as e:
            logger.exception(f"[ReportSuspectModal] send_confirmation error: {e}")
            await safe_respond(interaction, content="❌ Something went wrong while preparing the confirmation.", ephemeral=True)
# ------------------------------------------------------------
# MULTI-MATCH DROPDOWN
# ------------------------------------------------------------
class SuspectSelect(discord.ui.Select):
    def __init__(self, matches, crime_id, guild_id, perp_id, reporter_id, is_anonymous, stage_number):
        options = [
            discord.SelectOption(label=f"{m.display_name} ({m.name})", value=str(m.id))
            for m in matches
        ]

        super().__init__(
            placeholder="Select the suspect",
            min_values=1,
            max_values=1,
            options=options
        )

        self.crime_id = crime_id
        self.guild_id = guild_id
        self.perp_id = perp_id
        self.reporter_id = reporter_id
        self.is_anonymous = is_anonymous
        self.stage_number = stage_number

    async def callback(self, interaction: discord.Interaction):
        suspect_id = int(self.values[0])
        suspect = interaction.guild.get_member(suspect_id)

        if suspect is None:
            await safe_respond(interaction, content="❌ That suspect is no longer in the server.", ephemeral=True)
            return

        if suspect_id == self.reporter_id:
            embed = Embed(
                title="❌ You can’t report yourself",
                description="🚓 **The cops stared at you like you just licked a light socket.**",
                color=0xE74C3C
            )
            await safe_respond(interaction, embed=embed, ephemeral=True)
            return

        modal = ReportSuspectModal(
            crime_id=self.crime_id,
            guild_id=self.guild_id,
            perp_id=self.perp_id,
            reporter_id=self.reporter_id,
            is_anonymous=self.is_anonymous,
            stage_number=self.stage_number
        )

        await modal.send_confirmation(interaction, suspect)


class SuspectSelectView(ui.View):
    def __init__(self, matches, crime_id, guild_id, perp_id, reporter_id, is_anonymous, stage_number):
        super().__init__(timeout=60)
        self.add_item(SuspectSelect(matches, crime_id, guild_id, perp_id, reporter_id, is_anonymous, stage_number))

# ------------------------------------------------------------
# CONFIRMATION VIEW
# ------------------------------------------------------------
class ConfirmReportView(ui.View):
    def __init__(self, crime_id, guild_id, perp_id, suspect_id, reporter_id, is_anonymous, stage_number):
        super().__init__(timeout=60)
        self.crime_id = crime_id
        self.guild_id = guild_id
        self.perp_id = perp_id
        self.suspect_id = suspect_id
        self.reporter_id = reporter_id
        self.is_anonymous = is_anonymous
        self.stage_number = stage_number

        self.add_item(ConfirmReportButton())
        self.add_item(CancelReportButton())

# ------------------------------------------------------------
# CANCEL REPORT BUTTON
# ------------------------------------------------------------
class CancelReportButton(ui.Button):
    def __init__(self):
        super().__init__(label="Cancel", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await safe_respond(interaction, content="❌ Report cancelled.", ephemeral=True)


# ------------------------------------------------------------
# CONFIRM REPORT BUTTON
# ------------------------------------------------------------
class ConfirmReportButton(ui.Button):
    def __init__(self):
        super().__init__(label="Confirm Report", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        view: ConfirmReportView = self.view

        await interaction.response.defer(ephemeral=True)

        try:
            pool = get_pool()
            async with pool.acquire() as conn:

                # ------------------------------------------------------------
                # CALL THE FUNCTION AND GET ALL RETURN VALUES
                # ------------------------------------------------------------
                row = await conn.fetchrow("""
                    SELECT *
                    FROM police_process_report($1,$2,$3,$4,$5,$6,$7)
                """,
                    view.crime_id,
                    view.guild_id,
                    view.reporter_id,
                    view.suspect_id,
                    view.perp_id,
                    view.is_anonymous,
                    view.stage_number
                )

        except Exception as e:
            # ------------------------------------------------------------
            # SHOW REAL DATABASE ERROR MESSAGE IN AN EMBED
            # ------------------------------------------------------------
            err_msg = str(e).split("\n")[0]

            embed = Embed(
                title="🚨 The police are starting to get annoyed with your snitching",
                description=(
                    "**The police said the boy who cried wolf snitches less than you. "
                    "Even Paul Revere thinks you need to chill.**\n\n"
                    f"**Error:** {err_msg}"
                ),
                color=0xE74C3C
            )

            embed.set_footer(text="Try doing something with your life and reporting again during the next broadcast stage.")
            await safe_respond(interaction, embed=embed, ephemeral=True)
            return

        # ------------------------------------------------------------
        # EXTRACT RETURN VALUES
        # ------------------------------------------------------------
        was_correct = row["was_correct"]
        reward_money = row["reward_money"]
        reward_xp = row["reward_xp"]
        fine = row["fine"]
        remaining = row["remaining"]
        checking_before = row["checking"]

        # ------------------------------------------------------------
        # CORRECT REPORT
        # ------------------------------------------------------------
        if was_correct:
            embed = Embed(
                title="🎉 Correct Report!",
                description=(
                    f"Your report was **correct**.\n\n"
                    f"💰 Money Reward: **${reward_money / 100:.2f}**\n"
                    f"⭐ XP Reward: **{reward_xp} XP**"
                ),
                color=0x2ECC71
            )
            await safe_respond(interaction, embed=embed, ephemeral=True)
            return

        # ------------------------------------------------------------
        # WRONG REPORT — JAIL
        # ------------------------------------------------------------
        if remaining is not None:
            embed = Embed(
                title="🚨 Arrested for False Reporting",
                description=(
                    f"Your report was **incorrect**, and you couldn't afford the fine.\n\n"
                    f"The police attempted to fine you **${fine / 100:.2f}**, "
                    f"but you only had **${checking_before / 100:.2f}**.\n\n"
                    f"You have been sent to **jail**.\n"
                    f"Your remaining bail is **${remaining / 100:.2f}**."
                ),
                color=0xE74C3C
            )
            await safe_respond(interaction, embed=embed, ephemeral=True)
            return

        # ------------------------------------------------------------
        # WRONG REPORT — FINE (FUNNY VERSION)
        # ------------------------------------------------------------
        embed = Embed(
            title="❌ Incorrect Report",
            description=(
                "You accused the wrong suspect.\n\n"
                f"The police have fined you **${fine / 100:.2f}**.\n\n"
                "They also said your detective skills are so catastrophically bad "
                "that they’re considering issuing a restraining order to keep you "
                "**at least 50 feet away from any future clues.**"
            ),
            color=0xE74C3C
        )

        await safe_respond(interaction, embed=embed, ephemeral=True)

# ------------------------------------------------------------
# (OPTIONAL) EXTRA SAFETY / FALLBACKS
# ------------------------------------------------------------
# These are intentionally minimal and unchanged from your original file.
# No logic is altered here — only preserved exactly as before.

async def fetch_user_balance(discord_id: int, guild_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT checking_account_balance
            FROM users
            WHERE discord_id = $1 AND guild_id = $2
        """, discord_id, guild_id)
        return row["checking_account_balance"] if row else 0


async def fetch_user_incarceration(discord_id: int, guild_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT is_incarcerated
            FROM users
            WHERE discord_id = $1 AND guild_id = $2
        """, discord_id, guild_id)
        return bool(row["is_incarcerated"]) if row else False


async def fetch_crime_status(crime_id: int, guild_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT status, solver_id
            FROM police_crimes
            WHERE crime_id = $1 AND guild_id = $2
        """, crime_id, guild_id)
        return row if row else None


# ------------------------------------------------------------
# END OF FILE (PARTIAL)
# ------------------------------------------------------------
# The final part (PART 6/6) will include:
# - Any remaining utility functions
# - The final closing of the module
# - Ensuring no dangling code or missing imports
# - Ensuring the file is syntactically complete
# ------------------------------------------------------------
# FINAL SAFETY: ENSURE MODULE EXPORTS ARE CLEAN
# ------------------------------------------------------------

__all__ = [
    "DailyCrimeReportView",
    "ReportSuspectButton",
    "AnonymousReportButton",
    "ReportSuspectModal",
    "SuspectSelect",
    "SuspectSelectView",
    "ConfirmReportView",
    "ConfirmReportButton",
    "CancelReportButton",
    "safe_respond",
    "normalize"
]

# End of views_daily_report.py



