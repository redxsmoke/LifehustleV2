import datetime
import traceback
import random
import discord
import asyncio
from discord import app_commands

from db.connection import get_pool
from cogs.xp_engine import add_xp
from cogs.minigames.make_change import generate_make_change_game, format_money
from cogs.minigames.sneak_in import sneak_in_late_game
from cogs.minigames.snake_breakroom import play as play_snake_breakroom

occupation_group = app_commands.Group(
    name="occupation",
    description="Occupation system commands"
)

SHIFT_MESSAGES = [
    "You worked hard… or at least looked like it.",
    "Corporate is satisfied. That’s all that matters.",
    "Another shift survived without incident.",
    "You stared into the void… the void approved your work.",
    "Productivity achieved (definition unclear).",
    "Your manager is still unaware of your existence.",
    "You earned your paycheck with questionable effort.",
    "One step closer to retirement you’ll never afford.",
    "Work completed. Motivation not found.",
]

WIN_MESSAGES = [
    "💸 Somehow you didn’t embarrass yourself this time. Impressive.",
    "🧠 You might actually understand basic math. Scary.",
    "💰 Correct. Don’t get used to it, genius.",
    "😎 Wow… you did the bare minimum correctly.",
    "📈 Against all odds, you functioned like a competent adult.",
]

LOSE_MESSAGES = [
    "💀 That was painful to watch. Truly inspiring incompetence.",
    "🤡 I’ve seen toddlers handle money better than you.",
    "📉 Financial literacy: uninstalling itself from your brain.",
    "🧻 You fumbled a 4-option multiple choice. Incredible failure.",
    "🚨 Please do not touch cash registers in real life.",
]


def get_random_message(success: bool):
    return random.choice(WIN_MESSAGES if success else LOSE_MESSAGES)


# ============================================================
# JOB SELECTION UI
# ============================================================

class JobButton(discord.ui.Button):
    def __init__(self, job):
        super().__init__(
            label=f"{job['description']} (Lvl {job['level_required']})",
            style=discord.ButtonStyle.primary
        )
        self.job = job

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_occupations (
                    discord_id, guild_id, cd_occupation_id, employment_start_date
                )
                VALUES ($1, $2, $3, NOW())
            """,
            interaction.user.id,
            interaction.guild.id,
            self.job["cd_occupation_id"])

        await interaction.response.send_message(
            embed=discord.Embed(
                title="💼 Job Assigned",
                description=f"You are now employed as **{self.job['description']}**!",
                color=discord.Color.green()
            ),
            ephemeral=True
        )

        self.view.stop()


class JobSelectView(discord.ui.View):
    def __init__(self, jobs):
        super().__init__(timeout=60)
        self.jobs = jobs
        self.page = 0
        self.page_size = 10
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()

        start = self.page * self.page_size
        end = start + self.page_size

        for job in self.jobs[start:end]:
            self.add_item(JobButton(job))

        if self.page > 0:
            prev_btn = discord.ui.Button(label="⬅ Previous", style=discord.ButtonStyle.secondary)
            async def prev_callback(interaction):
                self.page -= 1
                self.update_buttons()
                await interaction.response.edit_message(view=self)
            prev_btn.callback = prev_callback
            self.add_item(prev_btn)

        if end < len(self.jobs):
            next_btn = discord.ui.Button(label="Next ➡", style=discord.ButtonStyle.secondary)
            async def next_callback(interaction):
                self.page += 1
                self.update_buttons()
                await interaction.response.edit_message(view=self)
            next_btn.callback = next_callback
            self.add_item(next_btn)


# ============================================================
# /occupation apply
# ============================================================
@occupation_group.command(name="apply", description="Browse and apply for available jobs")
async def apply(interaction: discord.Interaction):
    try:
        pool = get_pool()

        async with pool.acquire() as conn:

            # =====================================================
            # RULE: User may only have ONE active job
            # =====================================================
            existing_job = await conn.fetchrow("""
                SELECT cd_occupation_id
                FROM user_occupations
                WHERE discord_id = $1
                  AND guild_id = $2
                  AND employment_end_date IS NULL
            """, interaction.user.id, interaction.guild.id)

            if existing_job:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="🚫 Already Employed",
                        description=(
                            "You already have a job.\n\n"
                            "If you're trying to escape your current workplace:\n"
                            "• Use **/occupation resignjob** to quit\n"
                            "• Then use **/occupation apply** to find a new questionable career path"
                        ),
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

            # Continue normal apply logic
            user = await conn.fetchrow("""
                SELECT xp, level
                FROM users
                WHERE discord_id = $1 AND guild_id = $2
            """, interaction.user.id, interaction.guild.id)

            if not user:
                return await interaction.response.send_message(
                    "❌ No user profile found.",
                    ephemeral=True
                )

            jobs = await conn.fetch("""
                SELECT 
                    cd_occupation_id,
                    description,
                    level_required,
                    xp_required,
                    wage_per_shift,
                    xp_per_shift,
                    required_shifts_per_day
                FROM cd_occupations
                ORDER BY level_required ASC, xp_required ASC
            """)

        eligible_jobs = [
            job for job in jobs
            if user["level"] >= job["level_required"]
        ]

        if not eligible_jobs:
            return await interaction.response.send_message(
                "❌ No jobs available for your current level.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="💼 Available Occupations",
            description=(
                f"Showing **{len(eligible_jobs)}** eligible jobs.\n"
                "Select one to apply.\n"
                "10 jobs per page."
            ),
            color=discord.Color.blue()
        )

        view = JobSelectView(eligible_jobs)

        await interaction.response.send_message(embed=embed, view=view)

    except Exception:
        print(traceback.format_exc())


# ============================================================
# /occupation workshift
# ============================================================
@occupation_group.command(name="workshift", description="Work a shift")
async def workshift(interaction: discord.Interaction):

    try:
        pool = get_pool()

        async with pool.acquire() as conn:

            job = await conn.fetchrow("""
                SELECT 
                    uo.user_occupation_id,
                    uo.last_shift_worked,
                    uo.shifts_worked_today,
                    c.description,
                    c.wage_per_shift,
                    c.xp_per_shift,
                    c.required_shifts_per_day
                FROM user_occupations uo
                JOIN cd_occupations c
                  ON c.cd_occupation_id = uo.cd_occupation_id
                WHERE uo.discord_id = $1
                  AND uo.guild_id = $2
                  AND uo.employment_end_date IS NULL
            """, interaction.user.id, interaction.guild.id)

            if not job:
                return await interaction.response.send_message(
                    "❌ You don’t have a job.",
                    ephemeral=True
                )

            user = await conn.fetchrow("""
                SELECT xp
                FROM users
                WHERE discord_id = $1 AND guild_id = $2
            """, interaction.user.id, interaction.guild.id)

            if not user:
                return await interaction.response.send_message(
                    "❌ User not found.",
                    ephemeral=True
                )

            base_pay = job["wage_per_shift"]

        # =========================
        # MINIGAME SELECTION
        # =========================
        minigames = ["make_change", "sneak_in", "snake_breakroom"]
        chosen = random.choice(minigames)

        success = False
        reward = 0
        penalty = 0
        summary_text = ""

        # -------------------------
        # MAKE CHANGE GAME
        # -------------------------
        if chosen == "make_change":

            game = generate_make_change_game()
            correct = game["change_cents"]

            class ChangeGameView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=5)
                    self.result = None

                    for opt in game["options"]:
                        button = discord.ui.Button(
                            label=f"${opt / 100:,.2f}",
                            style=discord.ButtonStyle.primary
                        )

                        async def callback(interaction: discord.Interaction, value=opt):
                            self.result = (value == correct)

                            for child in self.children:
                                child.disabled = True

                            await interaction.response.edit_message(view=self)
                            self.stop()

                        button.callback = callback
                        self.add_item(button)

            view = ChangeGameView()

            embed = discord.Embed(
                title="💵 Make Change",
                description=(
                    f"Bill: {format_money(game['bill_cents'])}\n"
                    f"Payment: {format_money(game['payment_cents'])}\n\n"
                    "You have **5 seconds**."
                ),
                color=discord.Color.gold()
            )

            await interaction.response.send_message(embed=embed, view=view)
            await view.wait()

            success = view.result is True

            if success:
                reward = game["reward_cents"]
                summary_text = get_random_message(True)
            else:
                penalty = max(
                    game["penalty_cents"],
                    int(base_pay * 0.75)
                )
                correct_amount = format_money(game["change_cents"])
                summary_text = (
                    f"{get_random_message(False)}\n\n"
                    f"The correct amount was **{correct_amount}**."
                )

        # -------------------------
        # SNEAK-IN GAME
        # -------------------------
        elif chosen == "sneak_in":
            result = await sneak_in_late_game(interaction, interaction.user.id)

            success = (result["result"] == "win")
            reward = result["bonus"]
            penalty = result["penalty"]
            summary_text = result["message"]

        # -------------------------
        # SNAKE BREAKROOM GAME
        # -------------------------
        else:
            embed, view = await play_snake_breakroom(
                pool,
                interaction.guild.id,
                interaction.user.id,
                job["user_occupation_id"],
                base_pay
            )

            await interaction.response.send_message(embed=embed, view=view)
            await view.wait()

            success = (view.outcome_type == "positive")
            penalty = -view.bonus_amount if view.outcome_type == "negative" else 0
            reward = view.bonus_amount if view.outcome_type == "positive" else 0
            summary_text = view.outcome_summary

        # =========================
        # APPLY ECONOMY + XP
        # =========================
        pool = get_pool()
        async with pool.acquire() as conn:

            if success:
                await conn.execute("""
                    UPDATE users
                    SET checking_account_balance = checking_account_balance + $1
                    WHERE discord_id = $2 AND guild_id = $3
                """,
                reward,
                interaction.user.id,
                interaction.guild.id)

                xp_gain = job["xp_per_shift"]

            else:
                await conn.execute("""
                    UPDATE users
                    SET checking_account_balance = checking_account_balance - $1
                    WHERE discord_id = $2 AND guild_id = $3
                """,
                penalty,
                interaction.user.id,
                interaction.guild.id)

                xp_gain = 0

            result = await add_xp(
                conn,
                interaction.user.id,
                interaction.guild.id,
                xp_gain,
                user["xp"]
            )

            await conn.execute("""
                UPDATE user_occupations
                SET last_shift_worked = NOW(),
                    total_shifts_worked = total_shifts_worked + 1,
                    shifts_worked_today = shifts_worked_today + 1
                WHERE user_occupation_id = $1
            """, job["user_occupation_id"])

        # =========================
        # FINAL EMBED
        # =========================
        final_color = discord.Color.green() if success else discord.Color.red()

        final_effect = reward if success else -penalty
        final_paycheck = base_pay + final_effect

        embed = discord.Embed(
            title="🟢 Shift Summary" if success else "🔴 Shift Summary",
            description=summary_text,
            color=final_color,
            timestamp=datetime.datetime.utcnow()
        )

        embed.add_field(
            name="💰 Base Wage",
            value=format_money(base_pay),
            inline=False
        )

        embed.add_field(
            name="⭐ XP Earned",
            value=f"+{job['xp_per_shift']:,}" if success else "0",
            inline=False
        )

        embed.add_field(
            name="🎮 Minigame Effect",
            value=f"{'+' if final_effect >= 0 else '-'}{format_money(abs(final_effect))}",
            inline=False
        )

        embed.add_field(
            name="💵 Final Paycheck",
            value=format_money(final_paycheck),
            inline=False
        )

        if result["leveled_up"]:
            embed.add_field(
                name="📈 Level Up!",
                value=f"{result['old_level']} → {result['new_level']}",
                inline=False
            )

        await interaction.followup.send(embed=embed)

        # =========================
        # SEPARATE LEVEL UP EMBED
        # =========================
        if result["leveled_up"]:
            await interaction.followup.send(embed=result["levelup_embed"])

    except Exception:
        print(traceback.format_exc())


# ============================================================
# /occupation resignjob
# ============================================================
@occupation_group.command(name="resignjob", description="Quit job")
async def resignjob(interaction: discord.Interaction):

    try:
        pool = get_pool()

        async with pool.acquire() as conn:

            job = await conn.fetchrow("""
                SELECT user_occupation_id
                FROM user_occupations
                WHERE discord_id = $1
                  AND guild_id = $2
                  AND employment_end_date IS NULL
            """, interaction.user.id, interaction.guild.id)

            if not job:
                return await interaction.response.send_message(
                    "❌ You don’t have a job to resign from.",
                    ephemeral=True
                )

            # =====================================================
            # NEW: Delete the job record entirely
            # =====================================================
            await conn.execute("""
                DELETE FROM user_occupations
                WHERE user_occupation_id = $1
            """, job["user_occupation_id"])

        await interaction.response.send_message(
            embed=discord.Embed(
                title="💼 Resignation Processed",
                description="You walked out the door and never looked back.",
                color=discord.Color.orange()
            ),
            ephemeral=True
        )

    except Exception:
        print(traceback.format_exc())


async def setup(bot):
    bot.tree.add_command(occupation_group)
