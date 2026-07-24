import discord
import asyncio
import random
import logging

# ⭐ CORRECT PATH (matches your filesystem)
from police.police_reported_logic.police_flow_controller import PoliceFlowController
from police.police_reported_logic.universal_snitch_system import start_snitch_flow

# ⭐ Stage 3 import stays the same
from cogs.minigames.grandtheftauto.stage3_escape import start_stage3_directional_memory

logger = logging.getLogger("crime.gta.stage2")
logger.setLevel(logging.DEBUG)

WIRE_EMOJIS = {
    "red": "🔴",
    "blue": "🔵",
    "green": "🟢",
    "purple": "🟣",
    "yellow": "🟡",
}

WIRE_COLORS = list(WIRE_EMOJIS.keys())


async def start_gta_stage2(channel, bot, victim, user_id, car_id):
    try:
        controller = PoliceFlowController(
            user_id=user_id,
            guild_id=victim.guild.id,
            channel=channel,
            crime_type="grand_theft_auto",
            stolen_amount=None,
            company_name=None,
        )

        view = WiringPuzzleView(
            user_id=user_id,
            bot=bot,
            victim=victim,
            controller=controller,
            car_id=car_id,
        )

        embed = discord.Embed(
            title="🔧 GTA Stage 2 — Wiring Rotation Puzzle",
            description=(
                "Realign the wiring to match the correct diagram.\n\n"
                "**You have 5 moves and 1 minute.**\n"
                "Noise increases 20% per move.\n"
                "Noise ≥ 100% → witnesses alerted.\n\n"
                "Press **Begin Hotwiring** to start."
            ),
            color=discord.Color.orange(),
        )

        msg = await channel.send(embed=embed, view=view)
        view.status_message = msg

    except Exception as e:
        logger.exception(f"[start_gta_stage2] ERROR: {e}")
        await channel.send("❌ Error starting Stage 2.")


class WiringPuzzleView(discord.ui.View):
    def __init__(self, user_id, bot, victim, controller, car_id):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.bot = bot
        self.victim = victim
        self.controller = controller
        self.car_id = car_id

        self.status_message = None
        self.correct_order = random.sample(WIRE_COLORS, len(WIRE_COLORS))
        self.current_order = random.sample(WIRE_COLORS, len(WIRE_COLORS))

        self.moves_left = 5
        self.noise = 0
        self.time_left = 300
        self.timer_task = None

        self.selected_color = None
        self.selected_direction = None
        self.selected_spaces = None

        self.finished = False
        self.game_started = False

        begin_btn = BeginHotwireButton(self)
        begin_btn.row = 3
        self.add_item(begin_btn)

        for color in WIRE_COLORS:
            btn = ColorButton(color, self)
            btn.disabled = True
            btn.row = 0
            self.add_item(btn)

        for direction in ["left", "right"]:
            btn = DirectionButton(direction, self)
            btn.disabled = True
            btn.row = 1
            self.add_item(btn)

        for spaces in [1, 2, 3]:
            btn = SpaceButton(spaces, self)
            btn.disabled = True
            btn.row = 2
            self.add_item(btn)

    async def interaction_check(self, interaction):
        return interaction.user.id == self.user_id

    async def start_timer(self):
        while self.time_left > 0:
            if self.finished:
                return
            await asyncio.sleep(5)
            self.time_left -= 5
            if self.finished:
                return
            await self.update_embed()

        if not self.finished:
            await self.fail("⏱️ Time's up! The alarm triggered.")

    async def update_embed(self):
        if not self.status_message or self.finished:
            return

        correct_display = " ".join(WIRE_EMOJIS[c] for c in self.correct_order)
        current_display = " ".join(WIRE_EMOJIS[c] for c in self.current_order)

        selected_text = (
            f"**Selected:** "
            f"{WIRE_EMOJIS[self.selected_color] if self.selected_color else '—'} | "
            f"{self.selected_direction if self.selected_direction else '—'} | "
            f"{self.selected_spaces if self.selected_spaces else '—'}"
        )

        embed = discord.Embed(
            title="🔧 Wiring Rotation Puzzle",
            description=(
                f"**Correct Wiring Diagram:**\n{correct_display}\n\n"
                f"**Current Wiring Order:**\n{current_display}\n\n"
                f"{selected_text}\n\n"
                f"**Moves Left:** {self.moves_left}\n"
                f"**Noise:** {self.noise}%\n"
                f"**Time Remaining:** {self.time_left}s\n\n"
                "Select a **color**, **direction**, and **spaces**."
            ),
            color=discord.Color.blue(),
        )

        await self.status_message.edit(embed=embed, view=self)

    async def apply_move(self):
        if self.finished:
            return
        if not self.game_started:
            return
        if self.selected_color is None:
            return
        if self.selected_direction is None:
            return
        if self.selected_spaces is None:
            return

        color = self.selected_color
        direction = self.selected_direction
        spaces = self.selected_spaces

        idx = self.current_order.index(color)

        if direction == "left":
            new_idx = (idx - spaces) % len(self.current_order)
        else:
            new_idx = (idx + spaces) % len(self.current_order)

        self.current_order.pop(idx)
        self.current_order.insert(new_idx, color)

        self.selected_color = None
        self.selected_direction = None
        self.selected_spaces = None

        self.moves_left -= 1
        self.noise += 20

        if self.noise >= 100:
            await self.fail("🔊 Noise threshold reached! Witnesses alerted.")
            return

        if self.moves_left <= 0:
            await self.fail("❌ You ran out of moves!")
            return

        if self.current_order == self.correct_order:
            await self.success()
            return

        await self.update_embed()

    async def success(self):
        self.finished = True

        embed = discord.Embed(
            title="🚗 Engine Started!",
            description=(
                "You aligned the wiring perfectly.\n"
                "The engine roars to life.\n\n"
                "**Stage 3: Escape Route Memory Challenge begins now.**"
            ),
            color=discord.Color.green(),
        )

        await self.status_message.edit(embed=embed, view=None)

        if self.timer_task:
            self.timer_task.cancel()

        self.stop()

        # ⭐ Stage 3 call (unchanged)
        await start_stage3_directional_memory(
            channel=self.controller.channel,
            user=self.controller.channel.guild.get_member(self.user_id),
            guild_id=self.controller.guild_id,
            car_id=self.car_id,
            controller=self.controller,
        )

    async def fail(self, reason):
        self.finished = True

        embed = discord.Embed(
            title="🔊 Hotwire Failed!",
            description=(
                f"{reason}\n\n"
                "Witnesses are calling the police..."
            ),
            color=discord.Color.red(),
        )

        await self.status_message.edit(embed=embed, view=None)

        if self.timer_task:
            self.timer_task.cancel()

        self.stop()
        await start_snitch_flow(self.controller, self.controller.channel)


class BeginHotwireButton(discord.ui.Button):
    def __init__(self, parent_view):
        super().__init__(label="🔧 Begin Hotwiring", style=discord.ButtonStyle.green)
        self.parent_view = parent_view

    async def callback(self, interaction):
        if interaction.user.id != self.parent_view.user_id:
            return await interaction.response.send_message("This isn't your hotwire.", ephemeral=True)

        await interaction.response.defer()

        self.parent_view.game_started = True

        for child in self.parent_view.children:
            if isinstance(child, BeginHotwireButton):
                continue
            child.disabled = False

        self.parent_view.remove_item(self)

        await self.parent_view.status_message.edit(view=self.parent_view)

        self.parent_view.timer_task = asyncio.create_task(self.parent_view.start_timer())

        await self.parent_view.update_embed()


class ColorButton(discord.ui.Button):
    def __init__(self, color, parent_view):
        super().__init__(label=WIRE_EMOJIS[color], style=discord.ButtonStyle.secondary)
        self.color = color
        self.parent_view = parent_view

    async def callback(self, interaction):
        self.parent_view.selected_color = self.color
        await interaction.response.defer()
        await self.parent_view.apply_move()


class DirectionButton(discord.ui.Button):
    def __init__(self, direction, parent_view):
        label = "⬅️ Left" if direction == "left" else "➡️ Right"
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.direction = direction
        self.parent_view = parent_view

    async def callback(self, interaction):
        self.parent_view.selected_direction = self.direction
        await interaction.response.defer()
        await self.parent_view.apply_move()


class SpaceButton(discord.ui.Button):
    def __init__(self, spaces, parent_view):
        super().__init__(label=str(spaces), style=discord.ButtonStyle.success)
        self.spaces = spaces
        self.parent_view = parent_view

    async def callback(self, interaction):
        self.parent_view.selected_spaces = self.spaces
        await interaction.response.defer()
        await self.parent_view.apply_move()
