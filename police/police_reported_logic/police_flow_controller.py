import asyncio
import discord
import logging
from db.connection import get_pool

logger = logging.getLogger("crime.police.flowcontroller")
logger.setLevel(logging.DEBUG)


class PoliceFlowController:
    def __init__(
        self,
        user_id: int,
        guild_id: int,
        channel: discord.TextChannel,
        crime_type: str,
        stolen_amount: int | None,
        company_name: str | None,
    ):
        # Core identity
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel = channel
        self.crime_type = crime_type
        self.stolen_amount = stolen_amount
        self.company_name = company_name

        # Crime outcome state
        self.outcome = None
        self.robbery_complete = asyncio.Event()

        # Hide engine state
        self.hide_spot_chosen = False
        self.chosen_spot = None

        # Snitch system state
        self.snitch_triggered = False

        # Stage progression flags
        self.stage1_complete = False
        self.stage2_complete = False

    async def get_user_items(self):
        """
        Returns a dict of item_id → quantity from user_items table.
        This is used by PoliceItemView and intimidation logic.
        """
        try:
            pool = get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT item_id, quantity
                    FROM user_items
                    WHERE discord_id = $1 AND guild_id = $2
                """, self.user_id, self.guild_id)

                return {row["item_id"]: row["quantity"] for row in rows}

        except Exception as e:
            logger.exception(f"[get_user_items] ERROR: {e}")
            return {}

    #
    # Logging helpers
    #
    async def log_solved_crime(self):
        try:
            logger.info(f"[SOLVED] Crime solved for user {self.user_id} in guild {self.guild_id}")
        except Exception as e:
            logger.exception(f"[log_solved_crime] ERROR: {e}")

    async def log_unsolved_crime(self):
        try:
            logger.info(f"[UNSOLVED] Crime unsolved for user {self.user_id} in guild {self.guild_id}")
        except Exception as e:
            logger.exception(f"[log_unsolved_crime] ERROR: {e}")

    #
    # Stop controller
    #
    def stop(self):
        try:
            self.robbery_complete.set()
        except Exception as e:
            logger.exception(f"[stop] ERROR: {e}")