import discord
import asyncio
import random
from db.connection import get_pool

from .hide_locations import HIDE_SPOTS
from .police_rewards import apply_padlock_protection, set_bail_for_user


class HideButton(discord.ui.Button):
    def __init__(self, emoji, spot, controller):
        super().__init__(label=spot, emoji=emoji, style=discord.ButtonStyle.blurple)
        self.spot = spot
        self.controller = controller

    async def callback(self, interaction):
        if interaction.user.id != self.controller.user_id:
            return await interaction.response.send_message("This isn't your robbery.", ephemeral=True)

        self.controller.hide_spot_chosen = True
        self.controller.chosen_spot = self.spot

        # ⭐ UPDATED: Embedded hide message
        await interaction.response.send_message(
            embed=discord.Embed(
                title=f"🫣 You hid {self.spot}",
                description="The police are on their way...",
                color=0x3498DB
            ),
            ephemeral=True
        )

        # ⭐ FIX: Disable hide buttons immediately so user cannot click twice
        try:
            await interaction.message.edit(view=None)
        except Exception:
            pass

        await process_police_search(self.controller, interaction, self.spot)


class HideOnlyView(discord.ui.View):
    def __init__(self, controller):
        super().__init__(timeout=30)
        self.controller = controller

        spots_to_show = random.sample(HIDE_SPOTS[controller.crime_type], 4)

        for emoji, spot in spots_to_show:
            self.add_item(HideButton(emoji, spot, controller))


async def start_hide_sequence(controller, interaction):
    controller.hide_spot_chosen = False
    controller.chosen_spot = None

    hide_message = await controller.channel.send(
        embed=discord.Embed(
            title="🫣 Available Hiding Locations",
            description="Choose a hiding spot before the police arrive!",
            color=0x3498DB
        ),
        view=HideOnlyView(controller)
    )

    asyncio.create_task(hide_timeout(controller, hide_message))


    asyncio.create_task(hide_timeout(controller, hide_message))


async def hide_timeout(controller, hide_message):
    await asyncio.sleep(10)

    if controller.hide_spot_chosen or controller.robbery_complete.is_set():
        return

    try:
        await controller.channel.send(
            embed=discord.Embed(
                title="🚨 Police have arrived!",
                description="The officers rush in and begin searching the area.",
                color=0xF04747,
            )
        )
    except Exception:
        pass

    try:
        await hide_message.edit(view=None)
    except Exception:
        pass

    await asyncio.sleep(3)

    if controller.hide_spot_chosen or controller.robbery_complete.is_set():
        return

    controller.outcome = "failure"
    controller.chosen_spot = None

    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            balance = await conn.fetchval(
                "SELECT checking_account_balance FROM users WHERE discord_id = $1 AND guild_id = $2",
                controller.user_id, controller.guild_id
            ) or 0

            money_loss = balance

            final_loss, used_padlock = await apply_padlock_protection(
                conn, controller.user_id, controller.guild_id, money_loss
            )

            if used_padlock and money_loss > 0:
                desc = (
                    "You stood there looking like an idiot! The police arrested you.\n\n"
                    "**Your Pad Lock protected your checking account from being seized.** 🔐"
                )
            else:
                desc = (
                    "You stood there looking like an idiot! The police arrested you and "
                    "seized your checking_account funds for investigation."
                )

            await controller.channel.send(
                embed=discord.Embed(title="🚨 Arrested!", description=desc, color=0xF04747)
            )

            await conn.execute(
                "UPDATE users SET checking_account_balance = checking_account_balance - $1, cd_location_id = 8, is_incarcerated = TRUE WHERE discord_id = $2 AND guild_id = $3",
                final_loss, controller.user_id, controller.guild_id
            )

            await conn.execute(
                "UPDATE user_occupations SET employment_end_date = NOW() WHERE discord_id = $1 AND guild_id = $2 AND employment_end_date IS NULL",
                controller.user_id, controller.guild_id
            )

            await conn.execute(
                "INSERT INTO user_criminal_record (discord_id, guild_id, cd_crime_id, date_of_offense) VALUES ($1, $2, 1, NOW())",
                controller.user_id, controller.guild_id
            )

            await conn.execute(
                "INSERT INTO user_criminal_record (discord_id, guild_id, cd_crime_id, date_of_offense) VALUES ($1, $2, 4, NOW())",
                controller.user_id, controller.guild_id
            )

        await set_bail_for_user(controller.user_id, controller.guild_id)

        try:
            await controller.log_solved_crime()
        except Exception:
            pass

    except Exception:
        pass

    controller.robbery_complete.set()
    controller.stop()


async def process_police_search(controller, interaction, chosen_spot):
    if controller.robbery_complete.is_set():
        return False

    searched = random.sample(HIDE_SPOTS[controller.crime_type], 3)
    caught = False

    await asyncio.sleep(5)
    await controller.channel.send(
        embed=discord.Embed(
            title="🚨 Police Arrival",
            description="The police have arrived on scene...",
            color=0xF04747,
        )
    )

    for emoji, spot in searched:
        await asyncio.sleep(5)
        await controller.channel.send(
            embed=discord.Embed(
                title="🔍 Police Search",
                description=f"The police search **{spot}**...",
                color=0xFAA61A,
            )
        )
        if spot == chosen_spot:
            caught = True
            break

    await asyncio.sleep(5)

    pool = get_pool()

    if caught:
        controller.outcome = "failure"
        controller.robbery_complete.set()

        try:
            async with pool.acquire() as conn:
                balance = await conn.fetchval(
                    "SELECT checking_account_balance FROM users WHERE discord_id = $1 AND guild_id = $2",
                    controller.user_id, controller.guild_id
                ) or 0

                money_loss = balance

                final_loss, used_padlock = await apply_padlock_protection(
                    conn, controller.user_id, controller.guild_id, money_loss
                )

                if used_padlock and money_loss > 0:
                    desc = (
                        f"The police searched **{chosen_spot}** and found you.\n"
                        "**Your Pad Lock protected your checking account.** 🔐"
                    )
                else:
                    desc = (
                        f"The police searched **{chosen_spot}** and found you.\n"
                        "You've been arrested and your checking account was seized."
                    )

                await controller.channel.send(
                    embed=discord.Embed(title="🚨 Caught!", description=desc, color=0xF04747)
                )

                await conn.execute(
                    "UPDATE users SET checking_account_balance = checking_account_balance - $1, cd_location_id = 8, is_incarcerated = TRUE WHERE discord_id = $2 AND guild_id = $3",
                    final_loss, controller.user_id, controller.guild_id
                )

                await conn.execute(
                    "UPDATE user_occupations SET employment_end_date = NOW() WHERE discord_id = $1 AND guild_id = $2 AND employment_end_date IS NULL",
                    controller.user_id, controller.guild_id
                )

                await conn.execute(
                    "INSERT INTO user_criminal_record (discord_id, guild_id, cd_crime_id, date_of_offense) VALUES ($1, $2, 1, NOW())",
                    controller.user_id, controller.guild_id
                )

                await conn.execute(
                    "INSERT INTO user_criminal_record (discord_id, guild_id, cd_crime_id, date_of_offense) VALUES ($1, $2, 4, NOW())",
                    controller.user_id, controller.guild_id
                )

            await set_bail_for_user(controller.user_id, controller.guild_id)

            try:
                await controller.log_solved_crime()
            except Exception:
                pass

        except Exception:
            pass

    else:
        controller.outcome = "success"

        try:
            await controller.channel.send(
                embed=discord.Embed(
                    title="🏃 You Escaped!",
                    description="The police searched the area but didn’t find you.",
                    color=0x2ECC71
                )
            )
        except Exception:
            pass

        try:
            await controller.log_unsolved_crime()
        except Exception:
            pass

    controller.stop()
    return caught
