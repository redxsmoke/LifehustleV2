import asyncio
import discord

from db.connection import get_pool  

from .hide_locations import HIDE_SPOTS
from .hide_engine import start_hide_sequence, process_police_search
from .intimidation_engine import process_snitch

# Arrest consequence handler
from police.police_reported_logic.police_rewards import apply_police_consequences


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

    "gta": {
        "use_padlock": False,
        "use_bail": False,
        "use_criminal_record": False,
        "use_employment_firing": False,
        "use_money_seizure": False,
        "use_smoke_bomb": True,
        "use_corrupt_cop": True,
        "hide_spots": "gta",
    },
}


class PoliceFlowController:
    def __init__(
        self,
        user_id: int,
        guild_id: int,
        channel: discord.TextChannel,
        crime_type: str,
        stolen_amount: int | None = None,
        company_name: str | None = None,
        car_id: int | None = None,
        stolen_value: int | None = None,
    ):
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

    def uses_padlock(self):
        return bool(self.get_config().get("use_padlock"))

    def uses_bail(self):
        return bool(self.get_config().get("use_bail"))

    def uses_criminal_record(self):
        return bool(self.get_config().get("use_criminal_record"))

    def uses_employment_firing(self):
        return bool(self.get_config().get("use_employment_firing"))

    def uses_money_seizure(self):
        return bool(self.get_config().get("use_money_seizure"))

    def uses_smoke_bomb(self):
        return bool(self.get_config().get("use_smoke_bomb"))

    def uses_corrupt_cop(self):
        return bool(self.get_config().get("use_corrupt_cop"))

    def get_hide_spots(self):
        key = self.get_config().get("hide_spots")
        if not key:
            return []
        return HIDE_SPOTS.get(key, [])

    async def start_hide(self, interaction):
        await start_hide_sequence(self, interaction)

    async def trigger_police_search(self, interaction, chosen_spot):
        # Run police search
        caught = await process_police_search(self, interaction, chosen_spot)

        # DEBUG: show whether caught or not
        await self.channel.send(f"DEBUG: trigger_police_search → caught={caught} user={self.user_id}")

        if caught:
            try:
                await apply_police_consequences(self)
                await self.channel.send(f"DEBUG: apply_police_consequences SUCCESS user={self.user_id}")
            except Exception as e:
                await self.channel.send(f"DEBUG: apply_police_consequences ERROR user={self.user_id} → {e}")

    async def handle_hide_timeout(self):
        caught = await process_police_search(self, None, None)

        await self.channel.send(f"DEBUG: handle_hide_timeout → caught={caught} user={self.user_id}")

        if caught:
            try:
                await apply_police_consequences(self)
                await self.channel.send(f"DEBUG: timeout apply_police_consequences SUCCESS user={self.user_id}")
            except Exception as e:
                await self.channel.send(f"DEBUG: timeout apply_police_consequences ERROR user={self.user_id} → {e}")

    async def handle_snitch(self, interaction, snitcher_id):
        try:
            blocked = await process_snitch(self, interaction, snitcher_id)
            await self.channel.send(f"DEBUG: handle_snitch → blocked={blocked} snitcher={snitcher_id} user={self.user_id}")
            return blocked
        except Exception as e:
            await self.channel.send(f"DEBUG: handle_snitch ERROR user={self.user_id} → {e}")

    async def get_user_items(self):
        try:
            pool = get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT item_id, quantity
                    FROM user_items
                    WHERE discord_id = $1 AND guild_id = $2
                    """,
                    self.user_id,
                    self.guild_id,
                )

            return {row["item_id"]: row["quantity"] for row in rows}

        except Exception as e:
            return {}
