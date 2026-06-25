import discord
import random

# =========================
# LEVEL CALC
# =========================
async def get_level(conn, xp: int):
    row = await conn.fetchrow("""
        SELECT level
        FROM cd_levels
        WHERE xp_required <= $1
        ORDER BY xp_required DESC
        LIMIT 1
    """, xp)

    return row["level"] if row else 1


# =========================
# PRESTIGE CALC
# =========================
def get_prestige(level: int):
    # Every 50 levels = 1 prestige
    prestige = level // 50
    return prestige


# =========================
# XP PROGRESS BAR
# =========================
async def build_progress_bar(conn, xp: int, level: int):
    # Get current level XP requirement
    row = await conn.fetchrow("""
        SELECT xp_required
        FROM cd_levels
        WHERE level = $1
    """, level)

    current_level_xp = row["xp_required"] if row else 0

    # Get next level XP requirement
    row2 = await conn.fetchrow("""
        SELECT xp_required
        FROM cd_levels
        WHERE level = $1
    """, level + 1)

    next_level_xp = row2["xp_required"] if row2 else current_level_xp + 1000

    # Calculate progress
    span = next_level_xp - current_level_xp
    gained = xp - current_level_xp
    pct = max(0, min(1, gained / span))

    filled = int(pct * 20)
    empty = 20 - filled

    bar = "█" * filled + "░" * empty
    return bar, int(pct * 100)


# =========================
# RANDOM FLAVOR LINES
# =========================
FLAVOR_LINES = [
    "Your instincts are sharpening.",
    "You're becoming a problem for the competition.",
    "Your reputation is starting to echo.",
    "Your skills are leveling up faster than your enemies can react.",
    "You're moving like someone who knows what they're doing.",
    "Your momentum is getting dangerous.",
    "You're rising through the ranks with purpose.",
]


# =========================
# SOUND EFFECT ANIMATIONS
# =========================
SFX = [
    "✨ *shing!*",
    "⚡ *crackle!*",
    "🔥 *whoosh!*",
    "💥 *boom!*",
    "🌟 *flare!*",
]


# =========================
# LEVEL UP EMBED (FULLY UPGRADED)
# =========================
async def build_levelup_embed(conn, discord_id: int, old_level: int, new_level: int, new_xp: int):
    prestige = get_prestige(new_level)
    flavor = random.choice(FLAVOR_LINES)
    sfx = random.choice(SFX)

    # Build progress bar
    bar, pct = await build_progress_bar(conn, new_xp, new_level)

    embed = discord.Embed(
        title="🎉 LEVEL UP!",
        description=(
            f"{sfx}\n"
            f"<@{discord_id}> leveled up.\n\n"
            f"**Level {old_level} → {new_level}**"
        ),
        color=discord.Color.gold()
    )

    embed.add_field(
        name="🔥 Momentum",
        value=flavor,
        inline=False
    )

    embed.add_field(
        name="📊 XP Progress",
        value=f"`{bar}`\n**{pct}%** toward next level",
        inline=False
    )

    if prestige > 0:
        embed.add_field(
            name="🏆 Prestige",
            value=f"Prestige **{prestige}** — you're in rare territory.",
            inline=False
        )

    embed.set_footer(text="XP Engine • Progression System")

    return embed


# =========================
# ADD XP (CORE ENGINE)
# =========================
async def add_xp(conn, discord_id: int, guild_id: int, xp_gain: int, current_xp: int):
    new_xp = current_xp + xp_gain

    old_level = await get_level(conn, current_xp)
    new_level = await get_level(conn, new_xp)

    await conn.execute("""
        UPDATE users
        SET xp = $1,
            level = $2
        WHERE discord_id = $3 AND guild_id = $4
    """, new_xp, new_level, discord_id, guild_id)

    leveled_up = new_level > old_level

    levelup_embed = None
    if leveled_up:
        levelup_embed = await build_levelup_embed(
            conn,
            discord_id,
            old_level,
            new_level,
            new_xp
        )

    return {
        "new_xp": new_xp,
        "new_level": new_level,
        "old_level": old_level,
        "leveled_up": leveled_up,
        "levelup_embed": levelup_embed
    }
