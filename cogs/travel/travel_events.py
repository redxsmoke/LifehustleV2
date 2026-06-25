import random
from datetime import datetime

def L(msg):
    print(f"[TRAVEL LOG] {msg}", flush=True)

# =========================
# TIME OF DAY
# =========================
def get_time_band(hour: int):
    if 6 <= hour < 11:
        return "morning"
    elif 11 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 22:
        return "evening"
    else:
        return "late_night"

# =========================
# WEIGHTS
# =========================
TIME_WEIGHTS = {
    "morning": (45, 40, 15),
    "afternoon": (40, 40, 20),
    "evening": (30, 40, 30),
    "late_night": (20, 35, 45)
}

# =========================
# OUTCOMES
# =========================
OUTCOMES = {
    "car": {
        "morning": {
            "positive": [
                {"message": "You blew past a cop at 90mph — he waved like a dumbass.", "amount": 500},
                {"message": "Your exhaust backfired so loud it scared a jogger into dropping their smoothie.", "amount": 400},
                {"message": "You drifted into Starbucks drive‑thru like a wannabe Fast & Furious extra.", "amount": 600},
                {"message": "You revved so hard a Karen screamed — bonus points.", "amount": 700},
                {"message": "You scared a squirrel into abandoning its nut stash. Comedy gold.", "amount": 300},
            ],
            "neutral": [
                {"message": "You drove like a boring NPC. Congrats, you’re fucking invisible.", "amount": 0},
                {"message": "You made it from A to B without incident. Riveting shit.", "amount": 0},
                {"message": "Your GPS yawned. That’s how dull you were.", "amount": 0},
                {"message": "You drove so average you could be a DMV training video.", "amount": 0},
                {"message": "Nothing happened. Literally nothing. Fucking thrilling.", "amount": 0},
            ],
            "negative": [
                {"message": "Your tire exploded and some asshole filmed it for TikTok.", "amount": -400},
                {"message": "You hit every red light like the city was trolling your dumb ass.", "amount": -500},
                {"message": "Your muffler fell off and now you sound like a fart cannon.", "amount": -300},
                {"message": "You hit a pothole so deep it felt like pain in physical form.", "amount": -600},
                {"message": "Your hood flew open mid‑drive. Everyone laughed their asses off.", "amount": -700},
            ],
        },
        "afternoon": {
            "positive": [
                {"message": "You found a shortcut through a sketchy alley. Worth it.", "amount": 500},
                {"message": "You scared a jogger into dropping their protein shake. Comedy bonus.", "amount": 300},
                {"message": "You drifted into Taco Bell like a legend.", "amount": 600},
                {"message": "You honked at a Karen and she cried. Joy unlocked.", "amount": 700},
                {"message": "You revved so loud you set off three car alarms. Chaos bonus.", "amount": 500},
            ],
            "neutral": [
                {"message": "Your car ride was so uneventful it could be used as a sedative.", "amount": 0},
                {"message": "You drove like a boring fuck. Even your GPS fell asleep.", "amount": 0},
                {"message": "You blended into traffic like wallpaper.", "amount": 0},
                {"message": "You drove like a dad on cruise control.", "amount": 0},
                {"message": "Nothing happened. Literally nothing. Fucking thrilling.", "amount": 0},
            ],
            "negative": [
                {"message": "You stalled in front of a biker gang. They laughed until you cried.", "amount": -400},
                {"message": "Your brakes squealed like a pig being slaughtered.", "amount": -300},
                {"message": "You spilled coffee all over yourself mid‑drive. Dignity destroyed.", "amount": -200},
                {"message": "Your car smelled like burning ass. Everyone noticed.", "amount": -600},
                {"message": "You got rear‑ended by a grandma. Humiliation bonus.", "amount": -500},
            ],
        },
        "evening": {
            "positive": [
                {"message": "You scared a drunk guy into dropping his drink. Comedy win.", "amount": 400},
                {"message": "You drifted into Walmart parking lot like a dumbass hero.", "amount": 500},
                {"message": "You revved so loud you scared a raccoon into fleeing.", "amount": 300},
                {"message": "You blew past a cop — he was too busy on his phone.", "amount": 700},
                {"message": "You parked like a dick and somehow didn’t get keyed.", "amount": 400},
            ],
            "neutral": [
                {"message": "You drove like a boring NPC. Congrats, you’re fucking invisible.", "amount": 0},
                {"message": "You made it from A to B without incident. Riveting shit.", "amount": 0},
                {"message": "Your GPS yawned. That’s how dull you were.", "amount": 0},
                {"message": "You drove so average you could be a DMV training video.", "amount": 0},
                {"message": "Nothing happened. Literally nothing. Fucking thrilling.", "amount": 0},
            ],
            "negative": [
                {"message": "You clipped a curb so hard it sounded like murder.", "amount": -300},
                {"message": "Your headlights died mid‑drive. Everyone honked at your dumb ass.", "amount": -400},
                {"message": "You stalled at a green light and got cursed out.", "amount": -500},
                {"message": "You hit a pothole and your soul left your body.", "amount": -600},
                {"message": "Your car smelled like burning clutch. Everyone noticed.", "amount": -700},
            ],
        },
        "late_night": {
            "positive": [
                {"message": "Empty roads let you fly through the route like a lunatic.", "amount": 600},
                {"message": "You scared a raccoon into dropping its trash treasure.", "amount": 300},
                {"message": "You drifted into a 7‑Eleven parking lot like a dumbass hero.", "amount": 500},
                {"message": "You revved so loud you woke up half the neighborhood.", "amount": 700},
                {"message": "You blew past a cop — he was asleep in his cruiser.", "amount": 800},
            ],
            "neutral": [
                {"message": "You drove like a boring NPC. Congrats, you’re fucking invisible.", "amount": 0},
                {"message": "You made it from A to B without incident. Riveting shit.", "amount": 0},
                {"message": "Your GPS yawned. That’s how dull you were.", "amount": 0},
                {"message": "You drove so average you could be a DMV training video.", "amount": 0},
                {"message": "Nothing happened. Literally nothing. Fucking thrilling.", "amount": 0},
            ],
            "negative": [
                {"message": "You stalled in front of a biker gang. They laughed until you cried.", "amount": -400},
                {"message": "Your brakes squealed like a pig being slaughtered.", "amount": -300},
                {"message": "You spilled coffee all over yourself mid‑drive. Dignity destroyed.", "amount": -200},
                {"message": "Your car smelled like burning ass. Everyone noticed.", "amount": -600},
                {"message": "Your hood flew open mid‑drive. Everyone laughed their asses off.", "amount": -700},
            ],
        },
    },
    "bus": {
        "morning": {
            "positive": [
                {"message": "The bus driver floored it like he was late for parole.", "amount": 500},
                {"message": "You scored the only seat that didn’t smell like piss.", "amount": 400},
                {"message": "The bus skipped three stops just for you. VIP treatment.", "amount": 600},
                {"message": "You found a seat with working AC. Jackpot.", "amount": 700},
                {"message": "The bus driver blasted metal and you vibed hard.", "amount": 300},
            ],
            "neutral": [
                {"message": "You stared out the window pretending you were in a sad indie film.", "amount": 0},
                {"message": "You zoned out so hard you unlocked Bus Meditation Level 3.", "amount": 0},
                {"message": "You sat quietly, ignored by everyone. NPC vibes.", "amount": 0},
                {"message": "You rode the bus like a background character.", "amount": 0},
                {"message": "Nothing happened. Just bus shit.", "amount": 0},
            ],
            "negative": [
                {"message": "The bus smelled like wet socks and regret.", "amount": -400},
                {"message": "Some kid screamed for 20 minutes straight.", "amount": -500},
                {"message": "The bus was delayed and you aged 10 years waiting.", "amount": -300},
                {"message": "Someone sneezed directly into your soul.", "amount": -600},
                {"message": "The bus broke down and everyone cursed.", "amount": -700},
            ],
        },
        "afternoon": {
            "positive": [
                {"message": "You found a seat and relaxed like royalty.", "amount": 500},
                {"message": "The bus driver actually braked smoothly for once.", "amount": 400},
                {"message": "You got a window seat and judged everyone outside.", "amount": 300},
                {"message": "You hopped on just as the doors were closing. Clutch move.", "amount": 600},
                {"message": "The bus was weirdly quiet. Peace bonus.", "amount": 700},
            ],
            "neutral": [
                {"message": "You stared at your phone the whole ride like a zombie.", "amount": 0},
                {"message": "You listened to music and ignored humanity.", "amount": 0},
                {"message": "You watched the same street you always see. Thrilling.", "amount": 0},
                {"message": "You sat there, existing, doing absolutely nothing.", "amount": 0},
                {"message": "You rode the bus like a professional commuter NPC.", "amount": 0},
            ],
            "negative": [
                {"message": "The bus was packed and someone’s elbow lived in your ribs.", "amount": -400},
                {"message": "You got stuck next to someone chewing loudly.", "amount": -300},
                {"message": "The bus stopped at every possible light and sign.", "amount": -500},
                {"message": "Someone’s bag took up more space than you.", "amount": -200},
                {"message": "The bus driver slammed the brakes every five seconds.", "amount": -600},
            ],
        },
        "evening": {
            "positive": [
                {"message": "You found a seat that didn’t smell like despair.", "amount": 400},
                {"message": "The bus was quiet enough to feel illegal.", "amount": 500},
                {"message": "You got off right in front of your destination. Perfect.", "amount": 600},
                {"message": "The driver skipped a useless stop and you cheered inside.", "amount": 300},
                {"message": "You shared a nod with another tired gremlin. Solidarity bonus.", "amount": 700},
            ],
            "neutral": [
                {"message": "You stared at the floor and questioned your life choices.", "amount": 0},
                {"message": "You watched reflections in the window like a weirdo.", "amount": 0},
                {"message": "You rode in silence, like a background extra.", "amount": 0},
                {"message": "You zoned out and almost missed your stop.", "amount": 0},
                {"message": "You did nothing. The bus did nothing. Everyone did nothing.", "amount": 0},
            ],
            "negative": [
                {"message": "Someone played videos on full volume with no headphones.", "amount": -400},
                {"message": "You got stuck near a guy who smelled like old gym socks.", "amount": -500},
                {"message": "The bus took the longest possible route for no reason.", "amount": -300},
                {"message": "You missed your stop because the driver spaced out.", "amount": -600},
                {"message": "The bus lights flickered like a horror movie.", "amount": -700},
            ],
        },
        "late_night": {
            "positive": [
                {"message": "The bus was nearly empty. You claimed a whole row.", "amount": 500},
                {"message": "A drunk guy started singing and it was actually decent.", "amount": 400},
                {"message": "You got the perfect late‑night window seat.", "amount": 300},
                {"message": "The driver ignored a weird guy and kept things chill.", "amount": 600},
                {"message": "You rode in peace like a tired goblin king.", "amount": 700},
            ],
            "neutral": [
                {"message": "You stared out into the dark like a moody main character.", "amount": 0},
                {"message": "You rode in silence, half asleep, half dead.", "amount": 0},
                {"message": "You watched streetlights blur past and felt nothing.", "amount": 0},
                {"message": "You sat there, existing, while the bus hummed along.", "amount": 0},
                {"message": "You zoned out so hard you forgot what stop you needed.", "amount": 0},
            ],
            "negative": [
                {"message": "A drunk guy tried to tell you his entire life story.", "amount": -400},
                {"message": "Someone kept staring at you like you owed them money.", "amount": -500},
                {"message": "The bus took a detour through sketchy nowhere.", "amount": -300},
                {"message": "You got stuck next to someone snoring like a chainsaw.", "amount": -600},
                {"message": "The bus broke down in the middle of nowhere.", "amount": -700},
            ],
        },
    },
    "taxi": {
        "morning": {
            "positive": [
                {"message": "Your driver tested out their nitrous mod and you flew down the interstate.", "amount": 500},
                {"message": "The driver actually knew a shortcut and used it. Miracle.", "amount": 400},
                {"message": "You got a cab with working AC and no weird smells.", "amount": 600},
                {"message": "The driver offered you gum instead of attitude.", "amount": 300},
                {"message": "You made every light like the city owed you a favor.", "amount": 700},
            ],
            "neutral": [
                {"message": "A normal taxi ride, full of cigarette smell and regret.", "amount": 0},
                {"message": "You sat in silence while the driver judged your haircut.", "amount": 0},
                {"message": "You stared at the meter and questioned your life choices.", "amount": 0},
                {"message": "You rode quietly, like a hostage to capitalism.", "amount": 0},
                {"message": "You watched the same boring streets roll by.", "amount": 0},
            ],
            "negative": [
                {"message": "Your driver drifted corners like a maniac. You clung to life.", "amount": -400},
                {"message": "The driver missed your turn three times.", "amount": -500},
                {"message": "You got stuck in a rant about politics you didn’t ask for.", "amount": -300},
                {"message": "The cab smelled like old fries and bad decisions.", "amount": -600},
                {"message": "The driver slammed the brakes like it was a sport.", "amount": -700},
            ],
        },
        "afternoon": {
            "positive": [
                {"message": "Your driver drove on the railroad tracks to dodge traffic.", "amount": 500},
                {"message": "The driver cut through an alley like a pro.", "amount": 400},
                {"message": "You got dropped off right at the door like royalty.", "amount": 600},
                {"message": "The driver actually followed the GPS correctly.", "amount": 300},
                {"message": "You made it across town faster than you deserved.", "amount": 700},
            ],
            "neutral": [
                {"message": "Nothing special happened. You’re not special, nor was the ride.", "amount": 0},
                {"message": "You scrolled your phone and ignored reality.", "amount": 0},
                {"message": "You watched traffic crawl and accepted your fate.", "amount": 0},
                {"message": "You sat there, mildly annoyed but functional.", "amount": 0},
                {"message": "You rode in silence like a background extra.", "amount": 0},
            ],
            "negative": [
                {"message": "Your driver stopped for 30 minutes to clip his toenails.", "amount": -400},
                {"message": "The driver took the longest possible route.", "amount": -500},
                {"message": "You got stuck in a cab that smelled like wet dog.", "amount": -300},
                {"message": "The driver argued with someone on speakerphone the whole ride.", "amount": -600},
                {"message": "The meter climbed faster than the car moved.", "amount": -700},
            ],
        },
        "evening": {
            "positive": [
                {"message": "The driver ran from the police which got you there faster.", "amount": 500},
                {"message": "Your driver threaded through traffic like a chaos god.", "amount": 400},
                {"message": "You got a cab with decent music for once.", "amount": 300},
                {"message": "The driver dropped you right at the entrance like a VIP.", "amount": 600},
                {"message": "You made it across town before your food got cold.", "amount": 700},
            ],
            "neutral": [
                {"message": "Your driver let four other people cab share with you.", "amount": 0},
                {"message": "You sat in the back, silently judging everyone.", "amount": 0},
                {"message": "You watched city lights and felt mildly dead inside.", "amount": 0},
                {"message": "You rode in silence, like a tired NPC.", "amount": 0},
                {"message": "You stared at the meter and pretended not to care.", "amount": 0},
            ],
            "negative": [
                {"message": "Your driver stopped for dinner and added it to your fare.", "amount": -400},
                {"message": "The driver missed your exit and blamed you.", "amount": -500},
                {"message": "You got stuck in a cab that smelled like old sweat.", "amount": -300},
                {"message": "The driver argued with another driver mid‑ride.", "amount": -600},
                {"message": "You got dropped off a block away for no reason.", "amount": -700},
            ],
        },
        "late_night": {
            "positive": [
                {"message": "Your driver found a new shortcut. Who cares if it was legal?", "amount": 500},
                {"message": "The cab was weirdly clean for once.", "amount": 400},
                {"message": "You got home faster than your anxiety expected.", "amount": 600},
                {"message": "The driver actually kept the music chill.", "amount": 300},
                {"message": "You rode through empty streets like a night goblin king.", "amount": 700},
            ],
            "neutral": [
                {"message": "Your driver kept staring at your crotch area and winking.", "amount": 0},
                {"message": "You stared out the window like a moody main character.", "amount": 0},
                {"message": "You rode in silence, half asleep, half annoyed.", "amount": 0},
                {"message": "You watched neon signs blur past and felt nothing.", "amount": 0},
                {"message": "You sat there, existing, while the cab hummed along.", "amount": 0},
            ],
            "negative": [
                {"message": "Your driver was arrested mid‑ride and you got stranded.", "amount": -400},
                {"message": "The cab took a detour through sketchy nowhere.", "amount": -500},
                {"message": "You got stuck listening to the driver’s life story.", "amount": -300},
                {"message": "The meter kept climbing while you sat in traffic.", "amount": -600},
                {"message": "The cab broke down and you had to walk.", "amount": -700},
            ],
        },
    },
}


# =========================
# MAIN GENERATOR (with optional forced outcome)
# =========================
def generate_travel_event(travel_type: str, hour: int, forced_outcome_type: str | None = None):
    L(f"generate_travel_event START: travel_type={travel_type}, hour={hour}, forced={forced_outcome_type}")

    travel_type = travel_type.lower().strip()
    time_band = get_time_band(hour)
    L(f"time_band={time_band}")

    if travel_type not in OUTCOMES:
        L(f"Unknown travel_type={travel_type}, defaulting to car")
        travel_type = "car"

    if time_band not in OUTCOMES[travel_type]:
        L(f"Unknown time_band={time_band}, defaulting to afternoon")
        time_band = "afternoon"

    if forced_outcome_type in ("positive", "neutral", "negative"):
        outcome_type = forced_outcome_type
        L(f"Forced outcome_type={outcome_type}")
    else:
        p, n, neg = TIME_WEIGHTS[time_band]
        roll = random.randint(1, 100)
        L(f"Roll={roll}, weights={p}/{n}/{neg}")

        if roll <= p:
            outcome_type = "positive"
        elif roll <= p + n:
            outcome_type = "neutral"
        else:
            outcome_type = "negative"

        L(f"Selected outcome_type={outcome_type}")

    bucket = OUTCOMES[travel_type][time_band].get(outcome_type, [{"message": "Nothing happened.", "amount": 0}])
    message = random.choice(bucket)
    L(f"Selected event={message}")

    base_amount_cents = message.get("amount", 0) * 100
    multiplier = random.randint(2,7)
    L(f"Applying multiplier={multiplier}")
    event_delta = base_amount_cents * multiplier
    L(f"Final event_delta={event_delta}")

    return {
        "outcome_type": outcome_type,
        "message": message["message"],
        "amount": message["amount"]
    }
