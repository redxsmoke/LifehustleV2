import discord
import asyncio
import random
import logging
from db.connection import get_pool
from police.police_reported_logic.universal_snitch_system import start_snitch_flow

logger = logging.getLogger("crime.gta.stage3")
logger.setLevel(logging.DEBUG)


class Stage3EscapeView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int, car_id: int, controller, channel: discord.TextChannel):
        super().__init__(timeout=30)
        self.user_id = user_id              # thief
        self.guild_id = guild_id
        self.car_id = car_id
        self.controller = controller        # contains victim info
        self.channel = channel

        self.sequence = []
        self.index = 0
        self.message: discord.Message | None = None

        self.up = EscapeButton("⬆️", "UP", self)
        self.down = EscapeButton("⬇️", "DOWN", self)
        self.left = EscapeButton("⬅️", "LEFT", self)
        self.right = EscapeButton("➡️", "RIGHT", self)

        self.add_item(self.up)
        self.add_item(self.down)
        self.add_item(self.left)
        self.add_item(self.right)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def start_sequence(self, message: discord.Message):
        self.message = message

        # Generate 5-step pattern
        self.sequence = random.choices(["UP", "DOWN", "LEFT", "RIGHT"], k=5)

        # Show pattern for 5 seconds
        show_embed = discord.Embed(
            title="🏃 Stage 3 — Escape!",
            description=(
                "Memorize this escape pattern:\n\n"
                f"**{' '.join(self.sequence)}**\n\n"
                "You have **5 seconds**."
            ),
            color=discord.Color.blue()
        )
        await message.edit(embed=show_embed, view=None)

        await asyncio.sleep(5)

        # Hide pattern — user must recall from memory
        hide_embed = discord.Embed(
            title="🔒 Enter the Escape Pattern",
            description=(
                "The pattern is now hidden.\n"
                "Repeat the **5 directions** from memory."
            ),
            color=discord.Color.orange()
        )
        await message.edit(embed=hide_embed, view=self)

    async def handle_correct(self):
        self.index += 1

        if self.index >= len(self.sequence):
            xp_awarded = await self.mark_car_stolen()
            embed = discord.Embed(
                title="🏁 Escape Successful!",
                description=f"You escaped with the vehicle!\n\n**XP Earned:** `{xp_awarded:,}`",
                color=discord.Color.green()
            )
            if self.message:
                await self.message.edit(embed=embed, view=None)
            self.stop()

    async def handle_incorrect(self):
        embed = discord.Embed(
            title="🚨 Escape Failed!",
            description="You messed up the sequence. Police are alerted!",
            color=discord.Color.red()
        )
        if self.message:
            await self.message.edit(embed=embed, view=None)
        self.stop()

        await start_snitch_flow(self.controller, self.channel)

    async def mark_car_stolen(self):
        pool = get_pool()
        async with pool.acquire() as conn:

            # Update vehicle ownership + stolen metadata
            await conn.execute(
                """
                UPDATE user_vehicles
                SET is_stolen = TRUE,
                    last_stolen_at = NOW(),
                    stolen_from_discord_id = discord_id,
                    discord_id = $1
                WHERE user_vehicle_id = $2
                  AND guild_id = $3
                """,
                self.user_id,
                self.car_id,
                self.guild_id
            )

            # Insert stolen record into stolen_vehicles table
            await conn.execute(
                """
                INSERT INTO stolen_vehicles (
                    discord_id,
                    guild_id,
                    user_vehicle_id,
                    reported_to_police,
                    reported_date,
                    case_status
                )
                VALUES (
                    $1, $2, $3,
                    FALSE,
                    NULL,
                    'open'
                )
                """,
                self.user_id,      # thief
                self.guild_id,
                self.car_id
            )

            # ⭐ Award XP to thief
            base_xp = random.randint(1000, 2500)
            multiplier = round(random.uniform(1.5, 4.9), 2)
            xp_awarded = int(base_xp * multiplier)

            await conn.execute(
                """
                UPDATE users
                SET xp = xp + $1
                WHERE discord_id = $2
                  AND guild_id = $3
                """,
                xp_awarded,
                self.user_id,
                self.guild_id
            )

            return xp_awarded


class EscapeButton(discord.ui.Button):
    def __init__(self, emoji: str, direction: str, parent_view: Stage3EscapeView):
        super().__init__(label=emoji, style=discord.ButtonStyle.primary)
        self.direction = direction
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        try:
            expected = self.parent_view.sequence[self.parent_view.index]

            if self.direction == expected:
                await self.parent_view.handle_correct()
            else:
                await self.parent_view.handle_incorrect()

            await interaction.response.defer()
        except Exception as e:
            logger.exception(f"[EscapeButton.callback] ERROR: {e}")


async def start_stage3_directional_memory(
    channel: discord.TextChannel,
    user: discord.Member,
    guild_id: int,
    car_id: int,
    controller
):
    try:
        view = Stage3EscapeView(
            user_id=user.id,
            guild_id=guild_id,
            car_id=car_id,
            controller=controller,
            channel=channel
        )

        embed = discord.Embed(
            title="🏃 Stage 3 — Escape!",
            description=(
                "Get ready to follow the escape sequence.\n"
                "Watch closely—then repeat the directions."
            ),
            color=discord.Color.blue()
        )

        msg = await channel.send(embed=embed, view=view)
        await view.start_sequence(msg)

    except Exception as e:
        logger.exception(f"[start_stage3_directional_memory] ERROR: {e}")
