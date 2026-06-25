import discord
import random
from datetime import datetime

from db.connection import get_pool
from db.users import upsert_user
from cogs.travel.travel_events import generate_travel_event
from cogs.travel.travel_minigame import TravelMiniGameView


def travel_error(msg: str):
    print(f"[TRAVEL ERROR] {msg}", flush=True)


def L(msg):
    print(f"[TRAVEL LOG] {msg}", flush=True)


BREAKDOWN_REASONS = [
    "Your radiator overheated.",
    "Your engine seized up.",
    "Your transmission failed.",
    "Your alternator died.",
    "Your timing belt snapped.",
    "Your fuel pump stopped working.",
    "Your axle broke.",
    "Your suspension collapsed.",
    "Your spark plugs failed.",
    "Your battery exploded.",
]


# =========================
# BREAKDOWN / TRANSPORT / LOCATION VIEWS
# =========================

class RepairVehicleButton(discord.ui.Button):
    def __init__(self, vehicle_data, is_flat_tire):
        super().__init__(label="Repair Vehicle", style=discord.ButtonStyle.green)
        self.vehicle_data = vehicle_data
        self.is_flat_tire = is_flat_tire

    async def callback(self, interaction: discord.Interaction):
        L("RepairVehicleButton.callback START")
        pool = get_pool()
        cost = self.vehicle_data["breakdown_cost"]
        L(f"Repair cost = {cost}")

        async with pool.acquire() as conn:
            L("Updating vehicle repair in DB")
            await conn.execute("""
                UPDATE user_vehicles
                SET vehicle_status_id = 1,
                    breakdown_reason = NULL,
                    breakdown_cost = 0,
                    updated_timestamp = NOW()
                WHERE user_vehicle_id = $1
            """, self.vehicle_data["user_vehicle_id"])

            L("Updating user balance for repair")
            await conn.execute("""
                UPDATE users
                SET checking_account_balance = checking_account_balance - $1
                WHERE discord_id = $2 AND guild_id = $3
            """, cost, interaction.user.id, interaction.guild.id)

        embed = discord.Embed(
            title="🔧 Vehicle Repaired",
            description=f"Your vehicle has been repaired for **${cost/100:,.2f}**.",
            color=discord.Color.green()
        )

        L("Editing original response with repair embed")
        await interaction.edit_original_response(embed=embed, view=None)
        L("RepairVehicleButton.callback END")


class SellBrokenVehicleButton(discord.ui.Button):
    def __init__(self, vehicle_data):
        super().__init__(label="Sell Vehicle", style=discord.ButtonStyle.red)
        self.vehicle_data = vehicle_data

    async def callback(self, interaction: discord.Interaction):
        L("SellBrokenVehicleButton.callback START")
        pool = get_pool()
        sale_price = max(10000, int(self.vehicle_data["purchase_price"] * 0.25))
        L(f"Sale price = {sale_price}")

        async with pool.acquire() as conn:
            L("Deleting vehicle from DB")
            await conn.execute("""
                DELETE FROM user_vehicles
                WHERE user_vehicle_id = $1
            """, self.vehicle_data["user_vehicle_id"])

            L("Updating user balance for sale")
            await conn.execute("""
                UPDATE users
                SET checking_account_balance = checking_account_balance + $1
                WHERE discord_id = $2 AND guild_id = $3
            """, sale_price, interaction.user.id, interaction.guild.id)

        embed = discord.Embed(
            title="🚗 Vehicle Sold",
            description=f"You sold your broken vehicle for **${sale_price/100:,.2f}**.",
            color=discord.Color.orange()
        )

        L("Editing original response with sale embed")
        await interaction.edit_original_response(embed=embed, view=None)
        L("SellBrokenVehicleButton.callback END")


class BreakdownView(discord.ui.View):
    def __init__(self, vehicle_data, is_flat_tire):
        super().__init__(timeout=None)
        L("BreakdownView created")
        self.add_item(RepairVehicleButton(vehicle_data, is_flat_tire))
        self.add_item(SellBrokenVehicleButton(vehicle_data))


class TransportSelectButton(discord.ui.Button):
    def __init__(self, transport_data):
        self.transport_data = transport_data
        cost = transport_data.get("fare", transport_data.get("fuel_cost", 0))
        super().__init__(
            label=f"{transport_data.get('label', 'Unknown')} - ${cost/100:,.2f}",
            emoji=transport_data.get("emoji", "🚗"),
            style=discord.ButtonStyle.success
        )

    async def callback(self, interaction: discord.Interaction):
        L("TransportSelectButton.callback START")
        L(f"Transport selected: {self.transport_data}")

        pool = get_pool()

        async with pool.acquire() as conn:
            L("Fetching locations from DB")
            locations = await conn.fetch("""
                SELECT cd_location_id, description
                FROM cd_location
                ORDER BY description
            """)

        view = LocationView(locations, self.transport_data)

        embed = discord.Embed(
            title="🌍 Choose Destination",
            description=f"You selected **{self.transport_data.get('label', 'Unknown')}**",
            color=discord.Color.blurple()
        )

        L("Editing original message to show destinations")
        await interaction.response.edit_message(embed=embed, view=view)
        L("TransportSelectButton.callback END")


class LocationButton(discord.ui.Button):
    def __init__(self, label, emoji, location_id, transport_data):
        super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.primary)
        self.location_id = location_id
        self.transport_data = transport_data

    async def callback(self, interaction: discord.Interaction):
        L("LocationButton.callback START")
        L(f"Destination selected: {self.location_id}")

        await interaction.response.defer()
        L("Interaction deferred")

        msg = await interaction.followup.send("Traveling...", ephemeral=False)
        L("Created followup message for travel")

        pool = get_pool()
        guild_id = interaction.guild.id if interaction.guild else 0
        L(f"Guild ID = {guild_id}")

        async with pool.acquire() as conn:
            L("Upserting user")
            await upsert_user(conn, interaction.user.id, guild_id, interaction.user.name)

            L("Fetching user balance")
            user = await conn.fetchrow("""
                SELECT checking_account_balance
                FROM users
                WHERE discord_id = $1
                  AND guild_id = $2
            """, interaction.user.id, guild_id)

        if not user:
            L("User not found in DB")
            await msg.edit(content="User not found.", embed=None, view=None)
            return

        previous_balance = user["checking_account_balance"] or 0
        L(f"Previous balance = {previous_balance}")

        travel_class_id = self.transport_data.get("travel_class_id", 1)
        TRAVEL_TYPE_MAP = {1: "car", 2: "taxi", 3: "bus"}
        travel_type = TRAVEL_TYPE_MAP.get(travel_class_id, "car")
        L(f"Travel type = {travel_type}")

        fare = self.transport_data.get("fare", self.transport_data.get("fuel_cost", 0))
        L(f"Fare = {fare}")

        vehicle = None
        breakdown_triggered = False

        # =========================
        # VEHICLE LOGIC (car only)
        # =========================
        if travel_type == "car" and "vehicle_id" in self.transport_data:
            L("Car travel detected, checking vehicle status")

            async with pool.acquire() as conn:
                vehicle = await conn.fetchrow("""
                    SELECT uv.user_vehicle_id,
                           uv.commute_count,
                           uv.vehicle_condition_id,
                           uv.vehicle_status_id,
                           uv.purchase_price,
                           uv.color,
                           uv.license_plate,
                           uv.breakdown_reason,
                           uv.breakdown_cost,
                           cv.vehicle_type
                    FROM user_vehicles uv
                    JOIN cd_vehicles cv ON cv.cd_vehicle_id = uv.cd_vehicle_id
                    WHERE uv.user_vehicle_id = $1
                      AND uv.discord_id = $2
                      AND uv.guild_id = $3
                """,
                self.transport_data["vehicle_id"],
                interaction.user.id,
                guild_id)

            L(f"Vehicle fetched: {vehicle}")

            if not vehicle:
                L("Vehicle not found")
                await msg.edit(content="Vehicle not found.", embed=None, view=None)
                return

            if vehicle["vehicle_status_id"] in (8, 9):
                L("Vehicle already broken")
                is_flat = vehicle["vehicle_status_id"] == 9
                reason = vehicle["breakdown_reason"]
                cost = vehicle["breakdown_cost"]

                embed = discord.Embed(
                    title="🚫 Flat Tire" if is_flat else "💥 Vehicle Breakdown",
                    description=f"{reason}\n\nRepair cost: **${cost/100:,.2f}**",
                    color=discord.Color.red()
                )

                view = BreakdownView(vehicle, is_flat)

                L("Sending breakdown UI")
                await msg.edit(embed=embed, view=view)
                return

            L("Vehicle OK, updating commute count")

            old_commute = vehicle["commute_count"] or 0
            new_commute = old_commute + 1
            L(f"Commute updated: {old_commute} → {new_commute}")

            if new_commute <= 100:
                condition_id = 7
            elif new_commute <= 250:
                condition_id = 8
            elif new_commute <= 400:
                condition_id = 9
            elif new_commute <= 500:
                condition_id = 10
            else:
                condition_id = 11

            L(f"New condition_id = {condition_id}")

            status_id = vehicle["vehicle_status_id"]
            breakdown_reason = None
            breakdown_cost = 0

            if random.random() < 0.03:
                L("Flat tire triggered")
                status_id = 9
                breakdown_reason = "Your tire gave up on life."
                breakdown_cost = 10000
                breakdown_triggered = True
            else:
                if new_commute >= 600:
                    chance = 1.0
                elif new_commute > 500:
                    chance = 0.75
                elif new_commute > 401:
                    chance = 0.25
                else:
                    chance = 0.0

                L(f"Breakdown chance = {chance}")

                if chance > 0 and random.random() < chance:
                    L("Engine breakdown triggered")
                    status_id = 8
                    breakdown_reason = random.choice(BREAKDOWN_REASONS)
                    breakdown_cost = random.randint(100, 1000) * 100
                    breakdown_triggered = True

            async with pool.acquire() as conn:
                L("Saving vehicle updates")
                await conn.execute("""
                    UPDATE user_vehicles
                    SET commute_count = $1,
                        vehicle_condition_id = $2,
                        vehicle_status_id = $3,
                        breakdown_reason = $4,
                        breakdown_cost = $5,
                        updated_timestamp = NOW()
                    WHERE user_vehicle_id = $6
                """,
                new_commute,
                condition_id,
                status_id,
                breakdown_reason,
                breakdown_cost,
                vehicle["user_vehicle_id"])

            if breakdown_triggered:
                L("Showing breakdown UI after update")

                embed = discord.Embed(
                    title="🚫 Flat Tire" if status_id == 9 else "💥 Vehicle Breakdown",
                    description=f"{breakdown_reason}\n\nRepair cost: **${breakdown_cost/100:,.2f}**",
                    color=discord.Color.red()
                )

                view = BreakdownView(vehicle, status_id == 9)

                await msg.edit(embed=embed, view=view)
                return

        # =========================
        # MINIGAME (car only)
        # =========================
        forced_outcome_type = None
        extra_reward_cents = 0
        extra_penalty_cents = 0
        extra_xp = 0

        if travel_type == "car":
            L("Starting minigame")

            view = TravelMiniGameView(interaction.user.id)
            embed = view.get_embed()

            game_msg = await interaction.followup.send(embed=embed, view=view, ephemeral=False)
            L("Minigame message sent")

            await view.start_step(game_msg)
            await view.wait()
            L("Minigame finished")

            if view.passed:
                L("Minigame passed")
                forced_outcome_type = "positive"
                extra_reward_cents = view.extra_reward_cents
                extra_xp = view.xp_reward
            else:
                L("Minigame failed")
                forced_outcome_type = "negative"
                extra_penalty_cents = view.extra_penalty_cents

        # =========================
        # ECONOMY + TRAVEL EVENT
        # =========================
        L("Processing travel event")

        try:
            new_balance = previous_balance - fare
            L(f"Balance after fare: {new_balance}")

            L("Calling generate_travel_event()")
            event = generate_travel_event(travel_type, datetime.now().hour, forced_outcome_type)
            L(f"Event returned: {event}")

            event_type = event["outcome_type"]
            L(f"Event type = {event_type}")

            event_message = event["message"]
            L(f"Event message = {event_message}")

            base_amount_cents = event.get("amount", 0) * 100
            L(f"Base amount cents = {base_amount_cents}")

            multiplier = random.randint(1, 5)
            L(f"Multiplier = {multiplier}")

            event_delta = base_amount_cents * multiplier
            L(f"Event delta before type adjustment = {event_delta}")

            if event_type == "positive":
                event_delta = abs(event_delta)
                color = discord.Color.green()
                L("Event is positive")
            elif event_type == "negative":
                event_delta = -abs(event_delta)
                color = discord.Color.red()
                L("Event is negative")
            else:
                event_delta = 0
                color = discord.Color.gold()
                L("Event is neutral")

            L(f"Event delta after type adjustment = {event_delta}")

            new_balance += event_delta
            L(f"Balance after event delta = {new_balance}")

            new_balance += extra_reward_cents
            L(f"Balance after minigame reward = {new_balance}")

            new_balance -= extra_penalty_cents
            L(f"Balance after minigame penalty = {new_balance}")

            L("Updating user balance + XP in DB")
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE users
                    SET checking_account_balance = $1,
                        xp = xp + $5,
                        cd_location_id = $2
                    WHERE discord_id = $3
                      AND guild_id = $4
                """,
                new_balance,
                self.location_id,
                interaction.user.id,
                guild_id,
                extra_xp)

            L("DB update complete")

        except Exception as e:
            L(f"ERROR DURING TRAVEL EVENT: {e}")
            await msg.edit(content=f"Travel failed due to error: {e}", embed=None, view=None)
            return

        def money(v):
            return f"${v/100:+,.2f}"

        embed = discord.Embed(
            title="🚗 Travel Summary",
            color=color
        )
        embed.add_field(name="Travel Outcome", value=event_message, inline=False)
        embed.add_field(name="Transportation Cost", value=f"-${fare/100:,.2f}", inline=False)
        embed.add_field(name="Travel Outcome Bonus", value=money(event_delta), inline=False)

        if extra_reward_cents:
            embed.add_field(name="Minigame Bonus", value=money(extra_reward_cents), inline=False)
        if extra_penalty_cents:
            embed.add_field(name="Minigame Penalty", value=money(-extra_penalty_cents), inline=False)
        if extra_xp:
            embed.add_field(name="Minigame XP Reward", value=f"+{extra_xp:,} XP", inline=False)

        final_change = event_delta - fare + extra_reward_cents - extra_penalty_cents
        embed.add_field(name="Account Balance Change", value=money(final_change), inline=False)
        embed.add_field(name="Previous Account Balance", value=f"${previous_balance/100:,.2f}", inline=False)
        embed.add_field(name="New Account Balance", value=f"${new_balance/100:,.2f}", inline=False)

        L("Editing travel summary message")
        await msg.edit(content=None, embed=embed, view=None)
        L("LocationButton.callback END")


class LocationView(discord.ui.View):
    def __init__(self, locations, transport_data):
        super().__init__(timeout=60)
        L("LocationView created")

        emoji_map = {
            "Home": "🏠",
            "Work": "🏢",
            "Car Dealer": "🚗",
            "Market": "🏪",
            "Park": "🌳",
            "Bank": "🏦",
            "Jail": "👮"
        }

        for loc in locations:
            L(f"Adding location button: {loc['description']}")
            self.add_item(LocationButton(
                label=loc["description"],
                emoji=emoji_map.get(loc["description"], "📍"),
                location_id=loc["cd_location_id"],
                transport_data=transport_data
            ))


class TravelView(discord.ui.View):
    def __init__(self, vehicles):
        super().__init__(timeout=60)
        L("TravelView created")

        self.add_item(TransportSelectButton({
            "label": "Bus",
            "emoji": "🚌",
            "fare": 5000,
            "travel_class_id": 3
        }))

        self.add_item(TransportSelectButton({
            "label": "Taxi",
            "emoji": "🚕",
            "fare": 10000,
            "travel_class_id": 2
        }))

        for v in vehicles:
            L(f"Adding vehicle transport button: {v['vehicle_type']}")
            self.add_item(TransportSelectButton({
                "label": v["vehicle_type"],
                "emoji": "🚗",
                "fuel_cost": v["fuel_cost"],
                "travel_class_id": v["travel_class_id"],
                "vehicle_id": v["user_vehicle_id"],
            }))
