import discord
import logging
from db.connection import get_pool
from datetime import datetime, timedelta

# ⭐ LOGGER FOR GTA ERRORS
logger = logging.getLogger("crime.gtaerrors")
logger.setLevel(logging.ERROR)

# GTA cooldown (currently 0 hours)
COOLDOWN_HOURS = 0
GTA_COOLDOWN = timedelta(hours=COOLDOWN_HOURS)


def normalize(text: str) -> str:
    import unicodedata
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


class GTASelectVictimModal(discord.ui.Modal, title="Select a Car Theft Victim"):
    victim_name = discord.ui.TextInput(
        label="Victim nickname (not @mention)",
        placeholder="Type part of their nickname",
        required=True,
        max_length=64
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        try:
            raw = self.victim_name.value or ""
            query = normalize(raw.strip())

            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message(
                    "❌ Cannot search for victims outside a server.",
                    ephemeral=True
                )
                return

            pool = get_pool()
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
                    async with pool.acquire() as conn:
                        row = await conn.fetchrow("""
                            SELECT last_stolen_at
                            FROM user_vehicles
                            WHERE discord_id = $1
                              AND guild_id = $2
                              AND is_active = TRUE
                            LIMIT 1
                        """, member.id, guild.id)

                    if row:
                        last_stolen = row["last_stolen_at"]
                        if last_stolen:
                            if datetime.utcnow() - last_stolen < GTA_COOLDOWN:
                                continue

                        matches.append(member)

            if len(matches) == 0:
                embed = discord.Embed(
                    title="🚫 No Active Vehicle",
                    description=(
                        "This user does not currently have an active vehicle. "
                        "Please try another user or try this user again later."
                    ),
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            if len(matches) == 1:
                victim = matches[0]

                if victim.id == interaction.user.id:
                    await interaction.response.send_message(
                        "🧠 You are dumber than SpongeBob and Patrick on free balloon day.\n\n"
                        "🚗 It's not a crime to steal **your own car**.",
                        ephemeral=True
                    )
                    return

                cog = self.bot.get_cog("CrimeCommands")
                if not cog:
                    await interaction.response.send_message(
                        "⚠️ Crime system unavailable.",
                        ephemeral=True
                    )
                    return

                await cog.handle_grand_theft_auto(interaction, victim)
                return

            if len(matches) > 25:
                await interaction.response.send_message(
                    "❌ Too many matches found. Please type more of the nickname.",
                    ephemeral=True
                )
                return

            view = GTAVictimSelectView(matches, self.bot)
            await interaction.response.send_message(
                "Multiple matches found. Select the correct victim:",
                view=view,
                ephemeral=True
            )

        except Exception as e:
            logger.exception("Error in GTASelectVictimModal.on_submit: %s", e)
            try:
                await interaction.response.send_message(
                    "❌ Something went wrong while selecting a victim.",
                    ephemeral=True
                )
            except Exception:
                pass


class GTAVictimSelect(discord.ui.Select):
    def __init__(self, matches, bot):
        options = [
            discord.SelectOption(label=f"{m.display_name} ({m.name})", value=str(m.id))
            for m in matches
        ]

        super().__init__(
            placeholder="Select the victim",
            min_values=1,
            max_values=1,
            options=options
        )

        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        try:
            victim_id = int(self.values[0])
            victim = interaction.guild.get_member(victim_id)

            if victim is None:
                await interaction.response.send_message(
                    "❌ That user is no longer in the server.",
                    ephemeral=True
                )
                return

            pool = get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT last_stolen_at
                    FROM user_vehicles
                    WHERE discord_id = $1
                      AND guild_id = $2
                      AND is_active = TRUE
                    LIMIT 1
                """, victim.id, interaction.guild.id)

            if not row:
                embed = discord.Embed(
                    title="🚫 No Active Vehicle",
                    description=(
                        "This user does not currently have an active vehicle. "
                        "Please try another user or try this user again later."
                    ),
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            last_stolen = row["last_stolen_at"]
            if last_stolen:
                if datetime.utcnow() - last_stolen < GTA_COOLDOWN:
                    embed = discord.Embed(
                        title="⏳ Vehicle Theft Cooldown",
                        description=(
                            "This user recently had a vehicle stolen.\n"
                            "Please try again later."
                        ),
                        color=discord.Color.orange()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

            if victim.id == interaction.user.id:
                await interaction.response.send_message(
                    "🧠 You are dumber than SpongeBob and Patrick on free balloon day.\n\n"
                    "🚗 It's not a crime to steal **your own car**.",
                    ephemeral=True
                )
                return

            cog = self.bot.get_cog("CrimeCommands")
            if not cog:
                await interaction.response.send_message(
                    "⚠️ Crime system unavailable.",
                    ephemeral=True
                )
                return

            await cog.handle_grand_theft_auto(interaction, victim)

        except Exception as e:
            logger.exception("Error in GTAVictimSelect.callback: %s", e)
            try:
                await interaction.response.send_message(
                    "❌ Something went wrong while selecting a victim.",
                    ephemeral=True
                )
            except Exception:
                pass


class GTAVictimSelectView(discord.ui.View):
    def __init__(self, matches, bot):
        super().__init__(timeout=60)
        self.add_item(GTAVictimSelect(matches, bot))


class CrimeSelectionView(discord.ui.View):
    def __init__(self, user: discord.User, bot):
        super().__init__(timeout=60)
        self.user = user
        self.bot = bot
        self.add_item(CrimeDropdown(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id


class CrimeDropdown(discord.ui.Select):
    def __init__(self, parent_view):
        options = [
            discord.SelectOption(label="Theft", description="Steal from someone or somewhere"),
        ]
        super().__init__(placeholder="Select a crime...", min_values=1, max_values=1, options=options)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        crime_choice = self.values[0]

        if crime_choice == "Theft":
            await interaction.response.edit_message(
                content="Where do you want to steal from?",
                view=TheftLocationView(self.parent_view.user, self.parent_view.bot),
                embed=None
            )
        else:
            await interaction.response.send_message("Crime not implemented yet.", ephemeral=True)


class TheftLocationView(discord.ui.View):
    def __init__(self, user: discord.User, bot):
        super().__init__(timeout=60)
        self.user = user
        self.bot = bot
        self.add_item(TheftLocationDropdown(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id


class TheftLocationDropdown(discord.ui.Select):
    def __init__(self, parent_view):
        options = [
            discord.SelectOption(label="Rob your job", description="Steal from your workplace"),
            discord.SelectOption(label="Grand Theft Auto", description="Steal someone's car"),
        ]
        super().__init__(placeholder="Select location...", min_values=1, max_values=1, options=options)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        location = self.values[0]

        if location == "Rob your job":
            pool = get_pool()
            user_id = interaction.user.id
            guild_id = interaction.guild.id

            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT cd_location_id
                    FROM users
                    WHERE discord_id = $1 AND guild_id = $2
                    """,
                    user_id,
                    guild_id
                )

            if not row or row["cd_location_id"] != 2:
                embed = discord.Embed(
                    title="📍 Wrong Location",
                    description="❌ You need to travel to **Work** before you can rob your job.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            async with pool.acquire() as conn:
                employed = await conn.fetchval("""
                    SELECT 1
                    FROM user_occupations
                    WHERE discord_id = $1
                      AND guild_id = $2
                      AND employment_end_date IS NULL
                """, user_id, guild_id)

            if not employed:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="🚫 Not Employed",
                        description="You can't rob your job if you don't even have one.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

            cog = self.parent_view.bot.get_cog("CrimeCommands")
            if cog:
                try:
                    await cog.handle_rob_job(interaction)
                except Exception as e:
                    print(f"❌ Error in handle_rob_job: {e}")
                    try:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(
                                embed=discord.Embed(
                                    title="❌ Robbery Failed",
                                    description="Something went wrong during the robbery attempt.",
                                    color=discord.Color.red()
                                ),
                                ephemeral=True
                            )
                        else:
                            await interaction.followup.send(
                                embed=discord.Embed(
                                    title="❌ Robbery Failed",
                                    description="Something went wrong during the robbery attempt.",
                                    color=discord.Color.red()
                                ),
                                ephemeral=True
                            )
                    except Exception as inner_e:
                        print(f"❌ Failed to send error message: {inner_e}")
            else:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⚠️ Crime System Unavailable",
                        description="Crime system is not available right now. Please try again later.",
                        color=discord.Color.orange()
                    ),
                    ephemeral=True
                )

        elif location == "Grand Theft Auto":
            try:
                await interaction.response.send_modal(GTASelectVictimModal(self.parent_view.bot))
            except Exception as e:
                logger.exception("Error showing GTASelectVictimModal: %s", e)
                try:
                    await interaction.response.send_message(
                        "❌ Something went wrong while starting Grand Theft Auto.",
                        ephemeral=True
                    )
                except Exception:
                    pass
