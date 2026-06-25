import discord
from db.connection import get_pool


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
        ]
        super().__init__(placeholder="Select location...", min_values=1, max_values=1, options=options)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        location = self.values[0]

        if location == "Rob your job":
            pool = get_pool()
            user_id = interaction.user.id
            guild_id = interaction.guild.id

            # ============================
            # CHECK LOCATION (must be at Work)
            # ============================
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

            # ============================
            # ⭐ EMPLOYMENT CHECK (must have active job)
            # ============================
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

            # ============================
            # RUN ROBBERY
            # ============================
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


class ConfirmRobberyView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.value = None
        self.user_interaction = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not your robbery.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.green)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.user_interaction = interaction

        embed = discord.Embed(
            title="✅ Robbery Confirmed!",
            description="You're moving forward with the heist. Let's crack the vault...",
            color=0x43B581
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.user_interaction = interaction

        embed = discord.Embed(
            title="❌ Robbery Cancelled",
            description="You've backed out. Maybe next time...",
            color=0xF04747
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)
        self.stop()
