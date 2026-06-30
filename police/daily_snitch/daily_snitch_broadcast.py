import random
import asyncio
import discord
from discord import Embed
from db.connection import get_pool
from datetime import datetime
from zoneinfo import ZoneInfo

DAILY_SNITCH_NAME = "📰 The Daily Snitch"

# ------------------------------------------------------------
# FUNNY LINES (ALL FIXED — NO BROKEN QUOTES)
# ------------------------------------------------------------

FIRED_LINES = [
    "Management said they saw this coming since day one. It goes without saying, the suspect was fired.",
    "The employer stated the suspect was 'a walking HR violation.' We cut the suspect loose faster than HR deletes complaints during quarterly reviews.",
    "HR said they already had the termination paperwork half‑filled out. The suspect is now in the unemployment line.",
    "The boss said the suspect was 'one bad decision away from becoming a training example,' and added that they are now hiring.",
    "Coworkers reportedly celebrated, saying the suspect was 'the reason morale was low.' HR confirmed the suspect was fired.",
    "The employer said the suspect had 'the professionalism of a wet paper bag' and cheered that the suspect was FIRED.",
    "HR claimed they predicted this using a Magic 8 Ball. They also said the suspect asked the Magic 8 Ball if they're still employed — it replied 'No'.",
    "The company said they were shocked — shocked it took this long. They are now looking for a replacement after letting the suspect go.",
    "The employer said the suspect’s performance review was already titled 'Yikes.' Now it's titled 'Yikes and Took a Hike!' The employee was fired immediately.",
    "The boss said the suspect was 'a full-time disaster.' Now they're just a disaster — no longer full-time, part-time, or employed."
]

NOT_FIRED_LINES = [
    "The employer said they’re desperate and will hire anyone with a pulse.",
    "Management stated they don’t care what the suspect did — they need bodies.",
    "The company said background checks are optional now.",
    "HR said they stopped firing people in 2022 due to staffing shortages.",
    "The employer said the suspect is 'still more reliable than half the team.'",
    "The boss said they’d rehire the suspect even if they were on fire.",
    "The company said they’re so understaffed they’d hire a houseplant.",
    "Management said the suspect is 'problematic, but still cheaper than recruiting.'",
    "HR said they don’t have time to fire anyone anymore.",
    "The employer said they’re legally required to keep the suspect due to staffing laws."
]


# ------------------------------------------------------------
# MAIN BROADCAST FUNCTION
# ------------------------------------------------------------

async def send_daily_snitch_broadcast(
    interaction: discord.Interaction,
    crime_id: int,
    guild_id: int,
    perp_id: int,
    solver_id: int,
    is_anonymous: bool
):
    pool = get_pool()
    async with pool.acquire() as conn:

        # ------------------------------------------------------------
        # Fetch crime info
        # ------------------------------------------------------------
        crime_row = await conn.fetchrow("""
            SELECT crime_type, timestamp
            FROM police_crimes
            WHERE crime_id = $1 AND guild_id = $2
        """, crime_id, guild_id)

        if not crime_row:
            print("ERROR: Daily Snitch — crime row missing")
            return

        crime_type = crime_row["crime_type"]
        crime_ts = crime_row["timestamp"].date()

        # ------------------------------------------------------------
        # Fetch ALL occupations
        # ------------------------------------------------------------
        occ_rows = await conn.fetch("""
            SELECT uo.cd_occupation_id,
                   uo.employment_end_date,
                   co.company_name
            FROM user_occupations uo
            JOIN cd_occupations co ON co.cd_occupation_id = uo.cd_occupation_id
            WHERE uo.discord_id = $1 AND uo.guild_id = $2
        """, perp_id, guild_id)

        active_jobs = [row for row in occ_rows if row["employment_end_date"] is None]

        # ------------------------------------------------------------
        # Employment logic (bulletproof)
        # ------------------------------------------------------------
        if not active_jobs:
            employer_name = "No Employer"
            fired = False
            employer_line = "The suspect was not employed at the time."
        else:
            job = active_jobs[0]
            employer_name = job["company_name"]

            fired = random.random() < 0.5

            if fired:
                try:
                    await conn.execute("""
                        UPDATE user_occupations
                        SET employment_end_date = NOW()
                        WHERE discord_id = $1 AND guild_id = $2
                          AND employment_end_date IS NULL
                    """, perp_id, guild_id)
                except Exception as e:
                    print(f"ERROR: Daily Snitch — failed to update employment_end_date: {e}")

            employer_line = random.choice(FIRED_LINES if fired else NOT_FIRED_LINES)

        # ------------------------------------------------------------
        # Build embed
        # ------------------------------------------------------------
        guild = interaction.guild
        perp_member = guild.get_member(perp_id)
        solver_member = guild.get_member(solver_id)

        perp_mention = perp_member.mention if perp_member else f"<@{perp_id}>"

        if is_anonymous:
            solver_text = "The report was filed anonymously."
        else:
            solver_text = (
                f"Reported by {solver_member.mention}"
                if solver_member else
                f"Reported by <@{solver_id}>"
            )

        embed = Embed(
            title="🚨 BREAKING NEWS",
            description=(
                f"**{DAILY_SNITCH_NAME} — Official Crime Bulletin**\n\n"
                f"Authorities have confirmed an arrest in connection with the recent **{crime_type}** "
                f"that occurred on **{crime_ts}**.\n\n"
                f"**Suspect:** {perp_mention}\n"
                f"{solver_text}\n\n"
                f"Following the arrest, {DAILY_SNITCH_NAME} reached out to the suspect’s employer, "
                f"**{employer_name}**, for comment.\n\n"
                f"**Employer Response:** {employer_line}"
            ),
            color=0xE74C3C
        )

        embed.set_footer(text=f"{DAILY_SNITCH_NAME} • Trusted News Since 2026")

        # ------------------------------------------------------------
        # Send broadcast
        # ------------------------------------------------------------
        try:
            await interaction.channel.send(embed=embed)
        except Exception as e:
            print(f"ERROR: Daily Snitch — failed to send broadcast: {e}")
