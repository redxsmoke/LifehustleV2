import random
import asyncio
import discord
from discord.ui import View, Button

# ============================================================
# ECONOMY SCALING (MATCHES MAKE-CHANGE)
# ============================================================
MIN_ECON_BASE = 10000     # $100
MAX_ECON_BASE = 50000     # $500
MIN_MULT = 1.4
MAX_MULT = 3.7


class SneakInMiniGameView(View):
    """
    4-step Sneak-In minigame:
    - Avoid janitor
    - Avoid coworkers
    - Avoid cameras
    - Avoid bosses

    No DB calls. No economy logic here.
    /workshift handles the actual money update.
    """

    def __init__(self, user_id: int, timer_seconds: int = 5):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.timer_seconds = timer_seconds

        # Game state
        self.lanes = ["left", "middle", "right"]
        self.current_lane = random.choice(self.lanes)
        self.step = 0
        self.failed = False
        self.passed = False
        self.result_message = ""
        self._timeout_task = None
        self._message = None

        # Buttons
        self.left_button = Button(label="⬅️ Left", style=discord.ButtonStyle.primary)
        self.right_button = Button(label="➡️ Right", style=discord.ButtonStyle.primary)

        self.left_button.callback = self.on_left_click
        self.right_button.callback = self.on_right_click

        self.add_item(self.left_button)
        self.add_item(self.right_button)

        # 4-step obstacle sequence
        self.predicament_data = [
            {"title": "Avoid the janitor's brooms!", "emoji": "🧹",
             "fail_actor": "the janitor", "reason": "spilling dirty water everywhere"},
            {"title": "Avoid your coworkers!", "emoji": "🧍‍♀️",
             "fail_actor": "a nosy coworker", "reason": "an awkward water cooler chat"},
            {"title": "Avoid the security cameras!", "emoji": "🎥",
             "fail_actor": "a security camera", "reason": "being spotted by security"},
            {"title": "Avoid your bosses!", "emoji": "🧑‍💼",
             "fail_actor": "your boss", "reason": "a surprise performance review"},
        ]

        # Pre-generate obstacle lanes for all 4 steps
        self.obstacle_lanes = self.generate_obstacles_for_all()

    # ---------------------------------------------------------
    # GAME LOGIC
    # ---------------------------------------------------------
    def generate_obstacles_for_all(self):
        result = []
        for _ in self.predicament_data:
            safe_lane = random.choice(self.lanes)
            obstacles = [lane for lane in self.lanes if lane != safe_lane]
            random.shuffle(obstacles)
            result.append(obstacles)
        return result

    async def start_step(self, message: discord.Message):
        """Start or continue the 4-step sequence."""
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass

        # Completed all 4 steps
        if self.step >= len(self.predicament_data):
            self.passed = True
            self.result_message = "You quietly slipped into your desk without being noticed. 🎉"
            await self._message.edit(embed=self.get_embed(), view=None)
            self.stop()
            return

        self._message = message
        await message.edit(embed=self.get_embed(), view=self)

        # Start timer for this step
        self._timeout_task = asyncio.create_task(self._timeout())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the user who started the game can interact."""
        return interaction.user.id == self.user_id

    async def on_left_click(self, interaction: discord.Interaction):
        await self.handle_move(interaction, "left")

    async def on_right_click(self, interaction: discord.Interaction):
        await self.handle_move(interaction, "right")

    async def handle_move(self, interaction: discord.Interaction, move: str):
        idx = self.lanes.index(self.current_lane)

        if move == "left" and idx > 0:
            self.current_lane = self.lanes[idx - 1]
        elif move == "right" and idx < 2:
            self.current_lane = self.lanes[idx + 1]

        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def _timeout(self):
        """After X seconds, check if the user is in a safe lane."""
        await asyncio.sleep(self.timer_seconds)

        if self.is_finished():
            return

        obstacles = self.obstacle_lanes[self.step]
        safe = self.current_lane not in obstacles

        if safe:
            # Advance to next step
            self.step += 1
            if self.step >= len(self.predicament_data):
                self.passed = True
                self.result_message = "You made it in undetected. Nice work! 🕶️"
                await self._message.edit(embed=self.get_embed(), view=None)
                self.stop()
            else:
                await self.start_step(self._message)
        else:
            # Failure
            self.failed = True
            pred = self.predicament_data[self.step]
            self.result_message = (
                f"You were caught by {pred['fail_actor']} in the "
                f"{', '.join(obstacles)} lane(s)! 💥\n"
                f"You’ve been flagged for {pred['reason']}."
            )
            await self._message.edit(embed=self.get_embed(), view=None)
            self.stop()

    # ---------------------------------------------------------
    # EMBEDS
    # ---------------------------------------------------------
    def get_embed(self):
        if self.failed:
            title = "❌ Caught Sneaking In!"
        elif self.passed:
            title = "✅ You Snuck In!"
        else:
            title = self.predicament_data[self.step]["title"]

        desc = (
            self.result_message
            if (self.failed or self.passed)
            else self.build_obstacle_scene(self.step)
        )

        page = f"{self.step + 1}/4" if not (self.failed or self.passed) else ""

        color = (
            discord.Color.green()
            if self.passed
            else discord.Color.red()
            if self.failed
            else discord.Color.dark_gray()
        )

        embed = discord.Embed(title=title, description=desc, color=color)
        if page:
            embed.set_footer(text=page)
        return embed

    def build_obstacle_scene(self, step):
        lanes = self.lanes
        user_lane = self.current_lane
        obstacles = self.obstacle_lanes[step]
        obstacle_emoji = self.predicament_data[step]["emoji"]
        safe_emoji = "🚪"

        top_row = " ".join(
            obstacle_emoji if lane in obstacles else safe_emoji
            for lane in lanes
        )
        bottom_row = " ".join(
            "🧍" if lane == user_lane else "⬛"
            for lane in lanes
        )

        return f"{top_row}\n{bottom_row}"

    def is_finished(self):
        return self.failed or self.passed or self.step >= len(self.predicament_data)


# ---------------------------------------------------------
# PUBLIC FUNCTION CALLED BY /workshift
# ---------------------------------------------------------
async def sneak_in_late_game(interaction, user_id: int):
    """
    Runs the Sneak-In minigame and returns a result dict:

    {
        "result": "win" or "fail",
        "bonus": int,
        "penalty": int,
        "message": str
    }
    """

    view = SneakInMiniGameView(user_id)
    embed = view.get_embed()

    await interaction.response.send_message(embed=embed, view=view)
    message = await interaction.original_response()

    await view.start_step(message)
    await view.wait()

    # ---------------------------------------------------------
    # ECONOMY SCALING (Make-Change style)
    # ---------------------------------------------------------
    base = random.randint(MIN_ECON_BASE, MAX_ECON_BASE)
    multiplier = random.uniform(MIN_MULT, MAX_MULT)
    econ_value = int(base * multiplier)

    if view.passed:
        return {
            "result": "win",
            "bonus": econ_value,
            "penalty": 0,
            "message": view.result_message,
        }

    if view.failed:
        return {
            "result": "fail",
            "bonus": 0,
            "penalty": econ_value,
            "message": view.result_message,
        }

    return {
        "result": "neutral",
        "bonus": 0,
        "penalty": 0,
        "message": "Something unexpected happened during the Sneak-In minigame.",
    }
