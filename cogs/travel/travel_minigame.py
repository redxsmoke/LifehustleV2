import discord
import random
import asyncio

def log(msg):
    print(f"[MINIGAME] {msg}", flush=True)

class TravelMiniGameView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

        # lanes
        self.lanes = ["left", "middle", "right"]
        self.current_lane = random.choice(self.lanes)

        # game state
        self.step = 0
        self.failed = False
        self.passed = False
        self._message = None
        self._timeout_task = None

        # economy effects (for summary)
        self.extra_reward_cents = 0
        self.extra_penalty_cents = 0
        self.xp_reward = 0

        # controls
        self.left_button = discord.ui.Button(label="⬅️ Left", style=discord.ButtonStyle.primary)
        self.right_button = discord.ui.Button(label="➡️ Right", style=discord.ButtonStyle.primary)

        self.left_button.callback = self.on_left_click
        self.right_button.callback = self.on_right_click

        self.add_item(self.left_button)
        self.add_item(self.right_button)

        # obstacles
        self.predicaments = [0, 1, 2, 3]
        random.shuffle(self.predicaments)

        self.obstacle_lanes = []
        for idx in range(4):
            self.obstacle_lanes.append(self.generate_obstacles(idx))

        log(f"Initialized minigame. Starting lane={self.current_lane}, obstacles={self.obstacle_lanes}")

    def generate_obstacles(self, idx):
        if idx == 3:
            return random.choice([["left", "middle"], ["middle", "right"], ["left", "right"]])
        return [random.choice(self.lanes)]

    async def start_step(self, message: discord.Message):
        self._message = message

        log(f"Starting step {self.step}. Lane={self.current_lane}")

        # Completed all steps
        if self.step >= 4:
            log("All steps completed — marking as passed")
            self.passed = True

            # Rewards for summary
            self.extra_reward_cents = random.randint(50000, 150000)
            xp_multiplier = random.uniform(1.33, 5.44)
            self.xp_reward = int(100 * xp_multiplier)

            # Keep behavior: edit message, remove buttons, let summary handle outcome
            await self._message.edit(embed=self.get_embed(), view=None)
            self.stop()
            return

        # Update embed for current step
        await self._message.edit(embed=self.get_embed(), view=self)

        # Start new timeout task
        log(f"Creating timeout task for step {self.step}")
        self._timeout_task = asyncio.create_task(self._timeout())

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.user_id

    async def on_left_click(self, interaction: discord.Interaction):
        await self.move(interaction, "left")

    async def on_right_click(self, interaction: discord.Interaction):
        await self.move(interaction, "right")

    async def move(self, interaction, direction):
        idx = self.lanes.index(self.current_lane)

        if direction == "left" and idx > 0:
            self.current_lane = self.lanes[idx - 1]
        elif direction == "right" and idx < 2:
            self.current_lane = self.lanes[idx + 1]

        log(f"Player moved {direction}. New lane={self.current_lane}")

        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def _timeout(self):
        log(f"Timeout started for step {self.step}")
        await asyncio.sleep(3)
        log(f"Timeout fired for step {self.step}")

        if self.failed or self.passed:
            log("Timeout ignored — game already ended")
            return

        if self.step >= 4:
            log("Timeout ignored — step >= 4")
            return

        obstacles = self.obstacle_lanes[self.step]
        safe = self.current_lane not in obstacles

        log(f"Checking obstacles for step {self.step}: obstacles={obstacles}, lane={self.current_lane}, safe={safe}")

        if safe:
            log("Safe — progressing to next step")
            self.step += 1
            await self.start_step(self._message)
        else:
            log(f"CRASH at step {self.step}! Lane={self.current_lane}, obstacles={obstacles}")
            self.failed = True

            # Penalty for summary
            self.extra_penalty_cents = random.randint(50000, 150000)

            # Keep behavior: edit message, remove buttons, let summary handle outcome
            await self._message.edit(embed=self.get_embed(), view=None)
            self.stop()

    def get_embed(self):
        # No explicit "Success" or "Crash" text; just scene or neutral state
        if self.failed or self.passed:
            # Neutral end-state; summary will describe outcome
            title = "🕹️ Travel Outcome"
            color = discord.Color.blurple()
            desc = ""  # travel summary will fill in what happened
        else:
            title = "🕹️ Avoid the Obstacles"
            color = discord.Color.blurple()
            desc = self.render_scene()

        embed = discord.Embed(title=title, description=desc, color=color)

        if not (self.failed or self.passed):
            embed.set_footer(text=f"Step {self.step+1}/4")

        return embed

    def render_scene(self):
        road = "🛣️"
        car = "🚗"
        empty = "⬛"

        obstacles = self.obstacle_lanes[self.step]
        icons = ["🧒", "👵", "⚽", "🚧"]
        icon = icons[self.predicaments[self.step]]

        top = " ".join(icon if lane in obstacles else road for lane in self.lanes)
        bottom = " ".join(car if lane == self.current_lane else empty for lane in self.lanes)

        return f"{top}\n{bottom}"
