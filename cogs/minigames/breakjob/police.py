import asyncio
import random
import discord
from db.connection import get_pool
from .rewards import apply_protect_assets, set_bail_for_user
from utils.crime_system import log_crime, get_user_company


async def police_arrive(channel: discord.TextChannel):
    await channel.send(
        embed=discord.Embed(
            title="🚨 Police Arrival",
            description="The police have arrived on scene...",
            color=0xF04747,
        )
    )


async def police_search_sequence(view, interaction, chosen_spot: str):
    """
    Normal police search sequence.
    Smoke Bomb logic is handled BEFORE calling this function.
    """

    await police_arrive(view.channel)
   #searched = [(None, chosen_spot)]
    searched = random.sample(view.hide_spots, 3)
    caught = False

    for emoji, spot in searched:
        await asyncio.sleep(5)
        await view.channel.send(
            embed=discord.Embed(
                title="🔍 Police Search",
                description=f"The police search **{spot}**...",
                color=0xFAA61A,
            )
        )

        if spot == chosen_spot:
            caught = True
            break

    await asyncio.sleep(3)
    return caught


async def handle_police_outcome(view, interaction, chosen_spot: str):
    """
    Handles the final outcome after police search.
    Smoke Bomb and Corrupt Cop are handled in VaultGameView.
    """

    pool = get_pool()

    async with pool.acquire() as conn:

        # ------------------------------------------------------------
        # SMOKE BOMB GUARANTEED ESCAPE
        # ------------------------------------------------------------
        if view.smoke_bomb_used:
            view.outcome = "success"
            view.robbery_complete.set()

            await view.channel.send(
                embed=discord.Embed(
                    title="💨 You Escaped!",
                    description="The police didn’t bring their gas masks and left. You escaped.",
                    color=0x2ECC71
                )
            )
            return False

        # ------------------------------------------------------------
        # NORMAL SEARCH
        # ------------------------------------------------------------
        if chosen_spot is None:
            caught = True
        else:
            caught = await police_search_sequence(view, interaction, chosen_spot)

        guild_id = view.guild_id

        # ------------------------------------------------------------
        # CAUGHT
        # ------------------------------------------------------------
        if caught:
            view.outcome = "failure"
            view.robbery_complete.set()

            balance = await conn.fetchval("""
                SELECT checking_account_balance
                FROM users
                WHERE discord_id = $1 AND guild_id = $2
            """, view.user_id, guild_id) or 0

            money_loss = balance

            # Pad Lock protection only
            final_loss, used_padlock = await apply_protect_assets(
                conn, view.user_id, guild_id, money_loss
            )

            if chosen_spot is None:
                spot_text = "the area"
            else:
                spot_text = chosen_spot

            if used_padlock:
                desc = (
                    f"The police searched **{spot_text}** and found you.\n"
                    "**Your Pad Lock protected your checking account.** 🔐"
                )
            else:
                desc = (
                    f"The police searched **{spot_text}** and found you.\n"
                    "You've been arrested and your checking account was seized."
                )

            await view.channel.send(
                embed=discord.Embed(
                    title="🚨 Caught!",
                    description=desc,
                    color=0xF04747
                )
            )

            # ------------------------------------------------------------
            # LOG CRIME: CAUGHT IN HIDING SPOT
            # ------------------------------------------------------------
            company_name, occupation_name = await get_user_company(view.guild_id, view.user_id)

            await log_crime(
                guild_id=view.guild_id,
                perpetrator_id=view.user_id,
                crime_type="vault robbery",
                crime_description=f"Arrested while hiding at {company_name}",
                clue_description=None,
                evidence_list=[],
                status="solved",
                location=company_name
            )

            # Apply loss (if any)
            await conn.execute("""
                UPDATE users
                SET checking_account_balance = checking_account_balance - $1,
                    cd_location_id = 8,
                    is_incarcerated = TRUE
                WHERE discord_id = $2 AND guild_id = $3
            """, final_loss, view.user_id, guild_id)

            await conn.execute("""
                UPDATE user_occupations
                SET employment_end_date = NOW()
                WHERE discord_id = $1
                  AND guild_id = $2
                  AND employment_end_date IS NULL
            """, view.user_id, guild_id)

            await conn.execute("""
                INSERT INTO user_criminal_record (discord_id, guild_id, cd_crime_id, date_of_offense)
                VALUES ($1, $2, 1, NOW())
            """, view.user_id, guild_id)

            await conn.execute("""
                INSERT INTO user_criminal_record (discord_id, guild_id, cd_crime_id, date_of_offense)
                VALUES ($1, $2, 4, NOW())
            """, view.user_id, guild_id)

            await set_bail_for_user(view.user_id, guild_id)
            return True

        # ------------------------------------------------------------
        # ESCAPED (NORMAL)
        # ------------------------------------------------------------
        else:
            view.outcome = "success"
            view.robbery_complete.set()

            await view.channel.send(
                embed=discord.Embed(
                    title="🏃 You Escaped!",
                    description="The police searched the area but didn’t find you.",
                    color=0x2ECC71
                )
            )

            return False
