import discord
from discord.ext import commands
from discord import app_commands
from db.connection import get_pool
from datetime import datetime
import random

from cogs.weather_service import get_world_weather


# =========================
# TEMP GENERATION
# =========================
def generate_temp(month: int, hour: int, weather: str):
    base = {
        12: (25, 45), 1: (20, 40), 2: (25, 45),
        3: (40, 60), 4: (50, 70), 5: (60, 75),
        6: (70, 90), 7: (75, 95), 8: (75, 95),
        9: (65, 80), 10: (50, 70), 11: (40, 60)
    }

    low, high = base[month]
    temp = random.randint(low, high)

    if 6 <= hour < 18:
        temp += random.randint(0, 5)
    else:
        temp -= random.randint(0, 7)

    if weather == "rain":
        temp -= random.randint(1, 4)
    elif weather == "snow":
        temp -= random.randint(5, 12)
    elif weather == "sunny":
        temp += random.randint(1, 4)

    return temp


# =========================
# SEASONAL WEATHER CONTROL
# =========================
def get_season(month: int):
    if month in [12, 1, 2]:
        return "winter"
    if month in [3, 4, 5]:
        return "spring"
    if month in [6, 7, 8]:
        return "summer"
    return "fall"


def filter_weather_by_season(season: str):
    if season == "winter":
        return ["cloudy", "rain", "snow"]
    if season == "spring":
        return ["cloudy", "rain", "sunny"]
    if season == "summer":
        return ["sunny", "cloudy", "rain"]
    if season == "fall":
        return ["cloudy", "rain", "windy", "sunny"]


# =========================
# LEVEL SYSTEM
# =========================
async def get_level_info(conn, xp: int):
    current = await conn.fetchrow("""
        SELECT level, xp_required
        FROM cd_levels
        WHERE xp_required <= $1
        ORDER BY xp_required DESC
        LIMIT 1
    """, xp)

    next_lvl = await conn.fetchrow("""
        SELECT level, xp_required
        FROM cd_levels
        WHERE xp_required > $1
        ORDER BY xp_required ASC
        LIMIT 1
    """, xp)

    if not current:
        current = {"level": 0, "xp_required": 0}

    if not next_lvl:
        next_lvl = current

    progress = xp - current["xp_required"]
    needed = next_lvl["xp_required"] - current["xp_required"]

    return {
        "level": current["level"],
        "progress": progress,
        "needed": needed,
        "next_level": next_lvl["level"]
    }


# =========================
# COG
# =========================
class LifeCheck(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="lifecheck", description="View your life dashboard")
    async def lifecheck(self, interaction: discord.Interaction):

        pool = get_pool()

        async with pool.acquire() as conn:

            user = await conn.fetchrow("""
                SELECT checking_account_balance,
                       savings_account_balance,
                       cd_location_id,
                       xp
                FROM users
                WHERE discord_id = $1 AND guild_id = $2
            """, interaction.user.id, interaction.guild.id)

            if not user:
                return await interaction.response.send_message(
                    "No profile found.",
                    ephemeral=True
                )

            location = await conn.fetchrow("""
                SELECT description
                FROM cd_location
                WHERE cd_location_id = $1
            """, user["cd_location_id"])

            vehicle = await conn.fetchrow("""
                SELECT cv.vehicle_type
                FROM user_vehicles uv
                JOIN cd_vehicles cv ON cv.cd_vehicle_id = uv.cd_vehicle_id
                WHERE uv.discord_id = $1
                  AND uv.guild_id = $2
                  AND uv.is_active = true
                LIMIT 1
            """, interaction.user.id, interaction.guild.id)

            level_info = await get_level_info(conn, user["xp"])

        # =========================
        # WORLD STATE
        # =========================
        now = datetime.now()
        hour = now.hour

        time_icon = "🌞" if 6 <= hour < 18 else "🌙"

        season = get_season(now.month)
        allowed_weather = filter_weather_by_season(season)

        weather_type, weather_icon = await get_world_weather()

        if weather_type not in allowed_weather:
            weather_type = random.choice(allowed_weather)

        temp = generate_temp(now.month, hour, weather_type)

        # =========================
        # VALUES
        # =========================
        checking = f"${user['checking_account_balance']/100:,.2f}"
        savings = f"${user['savings_account_balance']/100:,.2f}"

        location_name = location["description"] if location else "Unknown"
        vehicle_name = vehicle["vehicle_type"] if vehicle else "None"

        # =========================
        # LEVEL BLOCK
        # =========================
        level_text = (
            f"```yml\n"
            f"LEVEL {level_info['level']}  →  {level_info['next_level']}\n"
            f"XP: {level_info['progress']:,} / {level_info['needed']:,}\n"
            f"```"
        )

        # =========================
        # EMBED
        # =========================
        embed = discord.Embed(
            title="🧭 LIFE DASHBOARD",
            description="A living simulation of your world state, updating in real time",
            color=discord.Color.blurple(),
            timestamp=now
        )

        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url
        )

        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        # =========================
        # TIME
        # =========================
        embed.add_field(
            name="⏰ TIME",
            value=f"```{now.strftime('%m/%d/%Y %I:%M %p')} {time_icon}```",
            inline=False
        )

        # =========================
        # WORLD STATE
        # =========================
        embed.add_field(
            name="🌍 WORLD STATE",
            value=(
                f"```"
                f"Season: {season.upper()}\n"
                f"Weather: {weather_type.upper()}\n"
                f"Temp: {temp}°F {weather_icon}"
                f"```"
            ),
            inline=False
        )

        # =========================
        # FINANCES (UPDATED)
        # =========================
        embed.add_field(
            name="💰 FINANCES",
            value=(
                f"**Checking Account:**\n```{checking}```\n"
                f"**Savings Account:**\n```{savings}```"
            ),
            inline=True
        )

        embed.add_field(
            name="🚗 TRANSPORT",
            value=f"```{vehicle_name}```",
            inline=True
        )

        embed.add_field(
            name="📍 LOCATION",
            value=f"```{location_name}```",
            inline=True
        )

        # =========================
        # LEVEL
        # =========================
        embed.add_field(
            name="📈 PROGRESSION",
            value=level_text,
            inline=False
        )

        # =========================
        # FOOTER
        # =========================
        embed.set_footer(text="Life Hustle • A living world that never pauses")

        await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================
# SETUP
# =========================
async def setup(bot):
    await bot.add_cog(LifeCheck(bot))