import asyncio
import discord
import logging

from db.connection import get_pool  
from .hide_locations import HIDE_SPOTS
from .hide_engine import start_hide_sequence, process_police_search
from .intimidation_engine import process_snitch
from police.police_reported_logic.police_rewards import apply_police_consequences

logger = logging.getLogger("crime.policeflow")
logger.setLevel(logging.ERROR)


CRIME_CONFIG = {
    "vault": {
        "use_padlock": True,
        "use_bail": True,
        "use_criminal_record": True,
        "use_employment_firing": True,
        "use_money_seizure": True,
        "use_smoke_bomb": True,
        "use_corrupt_cop": True,
        "hide_spots": "vault",
    },

    "grand_theft_auto": {
        "use_padlock": False,
        "use_bail": False,
        "use_criminal_record": False,
        "use_employment_firing": False,
        "use_money_seizure": False,
        "use_smoke_bomb": True,
        "use_corrupt_cop": True,
        "hide_spots": "grand_theft_auto",
    },
}


class PoliceFlowController:
    def __init__(self, user_id, guild_id, channel, crime_type,
                 stolen_amount=None, company_name=None, car_id=None, stolen_value=None):

        self.user_id = user_id
        self.guild_id = guild_id
        self.channel = channel
        self.crime_type = crime_type

        self.stolen_amount = stolen_amount
        self.company_name = company_name
        self.car_id = car_id
        self.stolen_value = stolen_value

        self.hide_spot_chosen = False
        self.chosen_spot = None
        self.smoke_bomb_used = False
        self.corrupt_cop_used = False

        self.snitched = False
        self.snitcher_id = None

        self.outcome = None
        self.robbery_complete = asyncio.Event()

    def get_config(self):
        return CRIME_CONFIG.get(self.crime_type, {})

    def get_hide_spots(self):
        key = self.get_config().get("hide_spots")
        if not key:
            return []
        return HIDE_SPOTS.get(key, [])

    async def start_hide(self, interaction):
        await start_hide_sequence(self, interaction)

    # ============================================================
    # CRIME LOGGING
    # ============================================================
    async def log_unsolved_crime(self):
        try:
            pool = get_pool()
            async with pool.acquire() as conn:

                next_id = await conn.fetchval("SELECT COALESCE(MAX(crime_id), 0) + 1 FROM police_crimes")

                company_name = await conn.fetchval("""
                    SELECT cd_o.company_name
                    FROM user_occupations uo
                    JOIN cd_occupations cd_o ON cd_o.cd_occupation_id = uo.cd_occupation_id
                    WHERE uo.discord_id = $1 AND uo.guild_id = $2 AND uo.employment_end_date IS NULL
                """, self.user_id, self.guild_id)

                await conn.execute("""
                    INSERT INTO police_crimes
                    (crime_id, guild_id, perpetrator_id, crime_type, crime_description,
                     timestamp, status, location)
                    VALUES ($1,$2,$3,$4,$5,NOW(),$6,$7)
                """,
                next_id, self.guild_id, self.user_id,
                "Robbery", "Theft of business funds", "Unsolved", company_name)

        except Exception as e:
            await self.channel.send(f"ERROR: log_unsolved_crime → {e}")

    async def log_solved_crime(self):
        try:
            pool = get_pool()
            async with pool.acquire() as conn:

                next_id = await conn.fetchval("SELECT COALESCE(MAX(crime_id), 0) + 1 FROM police_crimes")

                company_name = await conn.fetchval("""
                    SELECT cd_o.company_name
                    FROM user_occupations uo
                    JOIN cd_occupations cd_o ON cd_o.cd_occupation_id = uo.cd_occupation_id
                    WHERE uo.discord_id = $1 AND uo.guild_id = $2 AND uo.employment_end_date IS NULL
                """, self.user_id, self.guild_id)

                await conn.execute("""
                    INSERT INTO police_crimes
                    (crime_id, guild_id, perpetrator_id, crime_type, crime_description,
                     timestamp, status, location)
                    VALUES ($1,$2,$3,$4,$5,NOW(),$6,$7)
                """,
                next_id, self.guild_id, self.user_id,
                "Robbery", "Theft of business funds", "Solved", company_name)

        except Exception as e:
            await self.channel.send(f"ERROR: log_solved_crime → {e}")

    # ============================================================
    # POLICE SEARCH HANDLING
    # ============================================================
    async def trigger_police_search(self, interaction, chosen_spot):
        try:
            caught = await process_police_search(self, interaction, chosen_spot)

            if caught:
                await apply_police_consequences(self)
                await self.log_solved_crime()
            else:
                await self.log_unsolved_crime()

        except Exception as e:
            await self.channel.send(f"ERROR: trigger_police_search → {e}")

    async def handle_hide_timeout(self):
        if not self.hide_spot_chosen:
            try:
                await apply_police_consequences(self)
                await self.log_solved_crime()
            except Exception as e:
                await self.channel.send(f"ERROR: handle_hide_timeout auto → {e}")
            return

        try:
            caught = await process_police_search(self, None, None)

            if caught:
                await apply_police_consequences(self)
                await self.log_solved_crime()
            else:
                await self.log_unsolved_crime()

        except Exception as e:
            await self.channel.send(f"ERROR: handle_hide_timeout → {e}")

    async def handle_snitch(self, interaction, snitcher_id):
        try:
            logger.error(f"[POLICE] Starting police flow for user={self.user_id}, guild={self.guild_id}, type={self.crime_type}")

            # ⭐ LOG CRIME LOADING
            logger.error(f"[POLICE] Loading crime for user={self.user_id}, guild={self.guild_id}, type={self.crime_type}")

            # ⭐ GTA CRIME IS NEVER LOADED — THIS WILL SHOW UP
            # (We will fix this once we see the logs)
            crime = None

            if not crime:
                logger.error(f"[POLICE] NO CRIME FOUND for user={self.user_id}, guild={self.guild_id}, type={self.crime_type}")
            else:
                logger.error(f"[POLICE] CRIME LOADED: {crime}")

            # Run snitch logic
            result = await process_snitch(self, interaction, snitcher_id)

            logger.error(f"[POLICE] Finished police flow for user={self.user_id}")

            return result

        except Exception as e:
            logger.exception(f"[POLICE] ERROR in handle_snitch → {e}")
            await self.channel.send(f"ERROR: handle_snitch → {e}")

    async def get_user_items(self):
        try:
            pool = get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT item_id, quantity
                    FROM user_items
                    WHERE discord_id = $1 AND guild_id = $2
                """, self.user_id, self.guild_id)

            return {row["item_id"]: row["quantity"] for row in rows}

        except Exception:
            return {}

    def stop(self):
        try:
            if not self.robbery_complete.is_set():
                self.robbery_complete.set()
        except:
            pass
