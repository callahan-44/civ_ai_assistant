"""
Static constants and data dictionaries for the Civ VI AI Advisor.
"""

from pathlib import Path

# Configuration paths
CONFIG_FILE = Path(__file__).parent.parent / "config.json"
DEBUG_LOG_FILE = Path(__file__).parent.parent / "debug.log"
DEFAULT_LOG_FOLDER = Path.home() / "Documents" / "My Games" / "Sid Meier's Civilization VI" / "Logs"
LOG_FILENAME = "Lua.log"

# Data files for civilization and leader information
DATA_DIR = Path(__file__).parent.parent / "data"
CIVS_SUMMARY_FILE = DATA_DIR / "civs_summary.txt"
LEADERS_FILE = DATA_DIR / "leaders.txt"

# Available models
ANTHROPIC_MODELS = [
    ("Claude 3.5 Sonnet", "claude-3-5-sonnet-20241022"),
    ("Claude Sonnet 4", "claude-sonnet-4-20250514"),
]

# Google models with Flash hierarchy
# Primary -> Secondary -> Failover
GOOGLE_MODELS = [
    ("Gemini 3 Flash (Primary)", "gemini-3-flash-preview"),
    ("Gemini 2.5 Flash (Secondary)", "gemini-2.5-flash"),
    ("Gemma 3 27B (Failover)", "gemma-3-27b-it"),
]

# Fallback chain for Google models (Primary -> Secondary -> Failover)
GOOGLE_FALLBACK_CHAIN = [
    "gemini-3-flash-preview",  # Primary: Latest, in preview
    "gemini-2.5-flash",        # Secondary: Stable, fast
    "gemma-3-27b-it",          # Failover: Open model (no system prompt!)
]

# Models that don't support system prompts
NO_SYSTEM_PROMPT_MODELS = {"gemma-2-9b-it", "gemma-2-27b-it", "gemma-3-27b-it", "gemma-7b-it"}

# OpenAI models
OPENAI_MODELS = [
    ("GPT-4o (Recommended)", "gpt-4o"),
    ("GPT-4o Mini", "gpt-4o-mini"),
    ("GPT-4 Turbo", "gpt-4-turbo"),
    ("GPT-3.5 Turbo", "gpt-3.5-turbo"),
]

# Ollama models (local)
OLLAMA_MODELS = [
    ("Llama 3 (Default)", "llama3"),
    ("Llama 3.1 8B", "llama3.1:8b"),
    ("Mistral", "mistral"),
    ("Gemma 2", "gemma2"),
    ("Phi-3", "phi3"),
]

# Default Ollama endpoint
DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"

# All available providers
PROVIDERS = [
    ("google", "Google (Gemini)"),
    ("anthropic", "Anthropic (Claude)"),
    ("openai", "OpenAI (GPT)"),
    ("ollama", "Ollama (Local)"),
    ("clipboard", "Clipboard (Manual)"),
]

# Rate limiting defaults
DEFAULT_TOKEN_LIMIT = 1000
DEFAULT_RATE_LIMIT_SECONDS = 60
DEFAULT_MIN_REQUEST_INTERVAL = 20

# Default system prompts (split into core and extended)
DEFAULT_SYSTEM_PROMPT_CORE = """You are an expert Advisor in Civilization VI. You help players win.

RULES:
1. Maximum 5 sentences. Be specific and actionable.
2. Focus on the player's stated victory goal.
3. Prioritize IMMEDIATE DECISIONS first (settlement locations, builders, tech, civic, production, unit moves, threats).
4. Always think about the best next place to settle, build districts, or fight. Do not suggest healing unless death is very likely in the next turn.

OUTPUT FORMAT:
- Start with the most urgent action
- Be specific: name the tech/civic/unit/building
- **NEVER use grid locations.** Reference tile descriptions and relative locations when giving movement advice"""

DEFAULT_SYSTEM_PROMPT_EXTENDED = """
Consider the civilization's unique strengths when advising.
Only base recommendations on provided game data.
If you must assume something not in the data, label it as [ASSUMPTION] and provide alternatives.
Always address war if it seems likely."""

# UI Colors matching Civ VI aesthetic
COLORS = {
    "bg": "#1B1F2B",
    "bg_secondary": "#252A3A",
    "text": "#E6C288",
    "text_secondary": "#B8956C",
    "accent": "#C9A227",
    "border": "#3D4559",
    "button": "#2D3345",
    "button_hover": "#3D4559",
    "error": "#C75050",
    "success": "#50C770",
}

# ASCII map symbols (2-char codes)
MAP_SYMBOLS = {
    "city": "Ct",
    "capital": "C*",
    "warrior": "Wr",
    "scout": "Sc",
    "settler": "St",
    "builder": "Bl",
    "archer": "Ar",
    "slinger": "Sl",
    "spearman": "Sp",
    "horseman": "Hr",
    "knight": "Kn",
    "swordsman": "Sw",
    "crossbowman": "Xb",
    "catapult": "Ca",
    "trebuchet": "Tb",
    "musketman": "Mu",
    "cavalry": "Cv",
    "infantry": "In",
    "artillery": "At",
    "tank": "Tk",
    "battleship": "Bs",
    "destroyer": "Ds",
    "submarine": "Sb",
    "carrier": "Cr",
    "bomber": "Bm",
    "fighter": "Ft",
    "missionary": "Mi",
    "apostle": "Ap",
    "inquisitor": "Iq",
    "trader": "Tr",
    "spy": "Sy",
    # Terrain/features
    "mountain": "^^",
    "hills": "/\\",
    "forest": "Fo",
    "jungle": "Jg",
    "marsh": "Ms",
    "desert": "..",
    "plains": "--",
    "grassland": "--",  # Same as plains (map shows both as flat terrain)
    "coast": "::",
    "ocean": "::",  # Same as coast (map shows both as water)
    "river": "rv",
    # Resources
    "resource": "Rs",
    "strategic": "Sr",
    "luxury": "Lx",
    # Districts (specific symbols for each type)
    "city_center": "Cc",
    "campus": "Cp",
    "commercial_hub": "CH",
    "industrial_zone": "IZ",
    "theater_square": "TS",
    "holy_site": "HS",
    "encampment": "En",
    "harbor": "Hb",
    "entertainment_complex": "EC",
    "water_park": "WP",
    "aqueduct": "Aq",
    "neighborhood": "Nb",
    "aerodrome": "Ae",
    "spaceport": "Sx",  # Not "Sp" (conflicts with Spearman)
    "government_plaza": "Gz",  # Not "GP" (conflicts with Great Prophet)
    "diplomatic_quarter": "DQ",
    "preserve": "Pv",
    "dam": "Da",
    "canal": "Cl",
    # Unique districts (map to base type for display)
    "hansa": "IZ",  # Germany
    "royal_navy_dockyard": "Hb",  # England
    "street_carnival": "EC",  # Brazil
    "copacabana": "WP",  # Brazil
    "acropolis": "TS",  # Greece
    "lavra": "HS",  # Russia
    "seowon": "Cp",  # Korea
    "cothon": "Hb",  # Phoenicia
    "suguba": "CH",  # Mali
    "thanh": "En",  # Vietnam
    "ikanda": "En",  # Zulu
    "bath": "Aq",  # Rome (but provides amenities)
    "mbanza": "Nb",  # Kongo
    "oppidum": "IZ",  # Gaul
    # Other
    "improvement": "Im",
    "wonder": "Wn",
    "barb_camp": "!B",
    "enemy": "!E",
    "empty": "  ",
    "fog": "??",
}

# Civilization Strategy Database (Civ-Pedia)
CIV_STRATEGIES = {
    "sumeria": {
        "identity": "Sumeria",
        "key_unit": "War Cart (Strong early rush, no spear penalty, no horses needed)",
        "key_improvement": "Ziggurat (Science & Culture, builds on floodplains)",
        "strategy": "Aggressive Early Game. Rush with War Carts before enemies get walls. Ziggurats near rivers for science boost."
    },
    "rome": {
        "identity": "Rome",
        "key_unit": "Legion (Can build forts and roads)",
        "key_building": "Baths (Amenities + Housing)",
        "strategy": "Expand rapidly. Free roads to capital. Legion rush mid-game. Strong classical era timing."
    },
    "greece": {
        "identity": "Greece",
        "key_unit": "Hoplite (Combat bonus when adjacent to other Hoplites)",
        "key_district": "Acropolis (Culture district, adjacency from hills)",
        "strategy": "Culture victory path. Wildcard policy slot is powerful. Hoplite defensive wall early."
    },
    "egypt": {
        "identity": "Egypt",
        "key_unit": "Maryannu Chariot Archer (Ranged cavalry)",
        "key_improvement": "Sphinx (Faith & Culture, desert tiles)",
        "strategy": "Wonder-focused. 15% faster wonder construction. Rivers and floodplains are key."
    },
    "china": {
        "identity": "China",
        "key_unit": "Crouching Tiger (Ranged, no resources needed)",
        "key_improvement": "Great Wall (Defense, culture, gold along borders)",
        "strategy": "Defensive build. Boost Eurekas aggressively. Great Wall segments for culture."
    },
    "scythia": {
        "identity": "Scythia",
        "key_unit": "Saka Horse Archer (Light cavalry ranged unit)",
        "key_improvement": "Kurgan (Faith, gold, bonus near pastures)",
        "strategy": "Cavalry spam. Get 2 units for 1. Heal on kills. Overwhelming force early-mid game."
    },
    "japan": {
        "identity": "Japan",
        "key_unit": "Samurai (No combat penalty when damaged)",
        "key_building": "Electronics Factory (Production to nearby cities)",
        "strategy": "District adjacency master. Pack districts tight. Coastal start preferred for fishing boats."
    },
    "aztec": {
        "identity": "Aztec",
        "key_unit": "Eagle Warrior (Captures defeated units as Builders)",
        "key_building": "Tlachtli (Amenities, faith, great general points)",
        "strategy": "Early aggression. Eagle Warriors capture workers. Luxury resources give combat bonus."
    },
    "america": {
        "identity": "America",
        "key_unit": "Rough Rider (Combat bonus on hills, culture from kills)",
        "key_building": "Film Studio (Tourism pressure)",
        "strategy": "Late game culture. Founding Fathers gives legacy bonuses. Strong diplomatic game."
    },
    "brazil": {
        "identity": "Brazil",
        "key_unit": "Minas Geraes (Powerful modern naval unit)",
        "key_district": "Street Carnival (Entertainment, great people points)",
        "strategy": "Rainforest preservation. Great people generation. Culture victory through carnivals."
    },
    "france": {
        "identity": "France",
        "key_unit": "Garde Imperiale (Combat bonus near capital)",
        "key_improvement": "Chateau (Culture, tourism, near rivers)",
        "strategy": "Wonder whore. Tourism from wonders. Mid-game espionage is strong."
    },
    "germany": {
        "identity": "Germany",
        "key_unit": "U-Boat (Cheap submarine, bonus vs naval units)",
        "key_district": "Hansa (Industrial zone, adjacency from commercial)",
        "strategy": "Production powerhouse. Hansa-Commercial Hub combos. Extra military policy slot."
    },
    "india": {
        "identity": "India",
        "key_unit": "Varu (War elephant, reduces adjacent enemy strength)",
        "key_improvement": "Stepwell (Food, housing, faith near farms)",
        "strategy": "Religious or peaceful. Spread religion for bonuses. Stepwells for tall cities."
    },
    "england": {
        "identity": "England",
        "key_unit": "Sea Dog (Captures enemy ships)",
        "key_district": "Royal Navy Dockyard (Great Admiral points, bonus movement)",
        "strategy": "Naval domination. Continental maps ideal. Trade route bonuses. Redcoats on foreign continents."
    },
    "russia": {
        "identity": "Russia",
        "key_unit": "Cossack (Cavalry that can move after attacking)",
        "key_district": "Lavra (Great people, territory expansion)",
        "strategy": "Faith and expansion. Extra territory from founding cities. Tundra is home. Dance of the Aurora strong."
    },
    "spain": {
        "identity": "Spain",
        "key_unit": "Conquistador (Combat bonus with missionary)",
        "key_improvement": "Mission (Faith, bonus on other continents)",
        "strategy": "Cross-continental religious. Bonuses for same religion on other continents. Naval + missionary combo."
    },
    "kongo": {
        "identity": "Kongo",
        "key_unit": "Ngao Mbeba (Swordsman that ignores terrain)",
        "key_building": "Mbanza (Neighborhood replacement, food/gold)",
        "strategy": "Great works collector. Cannot found religion but benefits from others. Relics and artifacts focus."
    },
    "norway": {
        "identity": "Norway",
        "key_unit": "Berserker (Combat bonus when attacking, can pillage cheaply)",
        "key_unit2": "Longship (Coastal raids, ocean early)",
        "strategy": "Coastal raider. Pillage economy. Early ocean access. Naval domination."
    },
    "arabia": {
        "identity": "Arabia",
        "key_unit": "Mamluk (Cavalry that heals every turn)",
        "key_building": "Madrasa (Science from campus)",
        "strategy": "Religious science. Last great prophet guaranteed. Spread religion for science bonus."
    },
    "persia": {
        "identity": "Persia",
        "key_unit": "Immortal (Melee with ranged attack)",
        "key_improvement": "Pairidaeza (Culture, gold, appeal)",
        "strategy": "Internal trade and surprise wars. Bonus during golden ages. Pairidaeza for culture victory."
    },
    "macedon": {
        "identity": "Macedon",
        "key_unit": "Hypaspist (Siege bonus, general points from kills)",
        "key_building": "Basilikoi Paides (Combat XP, science from barracks)",
        "strategy": "Conquest machine. Eurekas and Inspirations from conquest. Never stop attacking."
    },
    "australia": {
        "identity": "Australia",
        "key_unit": "Digger (Combat bonus outside territory, on coast)",
        "key_improvement": "Outback Station (Food, production, pastures)",
        "strategy": "Defensive liberation. Huge production when war declared on you. Coastal expansion. Pasture focus."
    },
    "nubia": {
        "identity": "Nubia",
        "key_unit": "Pitati Archer (Stronger, faster archer)",
        "key_improvement": "Nubian Pyramid (Yields based on adjacent districts)",
        "strategy": "Ranged dominance. Early archer rush devastating. Pyramids for all victory types."
    },
    "indonesia": {
        "identity": "Indonesia",
        "key_unit": "Jong (Frigate replacement, escort bonus)",
        "key_improvement": "Kampung (Housing, production, on coast)",
        "strategy": "Island hopping. Religious and naval. Coastal faith from Kampungs. Many small islands preferred."
    },
    "khmer": {
        "identity": "Khmer",
        "key_unit": "Domrey (Siege elephant, can move and shoot)",
        "key_building": "Prasat (Faith from missionaries)",
        "strategy": "Religious tall. Holy Sites near rivers for massive bonuses. Aqueducts for farms."
    },
    "cree": {
        "identity": "Cree",
        "key_unit": "Okihtcitaw (Scout replacement, free promotion)",
        "key_improvement": "Mekewap (Housing, gold, resources)",
        "strategy": "Trade and expansion. Free trader at Pottery. Alliance focus. Peaceful expansion."
    },
    "georgia": {
        "identity": "Georgia",
        "key_unit": "Khevsur (Swordsman with movement in hills)",
        "key_building": "Tsikhe (Renaissance walls, tourism)",
        "strategy": "Defensive faith. Bonuses during golden ages and protectorate wars. Walls give tourism."
    },
    "korea": {
        "identity": "Korea",
        "key_unit": "Hwacha (Ranged siege, cannot move and attack)",
        "key_district": "Seowon (Campus, must be alone, -1 per adjacent)",
        "strategy": "Science turtle. Seowon isolation. Governor science bonuses. Beeline key techs."
    },
    "mapuche": {
        "identity": "Mapuche",
        "key_unit": "Malon Raider (Light cavalry, pillage bonus)",
        "key_improvement": "Chemamull (Culture based on appeal)",
        "strategy": "Anti-golden age. Combat bonus vs civilizations in golden age. Chemamull for culture."
    },
    "mongolia": {
        "identity": "Mongolia",
        "key_unit": "Keshig (Ranged cavalry with escort)",
        "key_building": "Ordu (Cavalry movement bonus)",
        "strategy": "Cavalry domination. Diplomatic visibility = combat strength. Trading posts everywhere."
    },
    "netherlands": {
        "identity": "Netherlands",
        "key_unit": "De Zeven Provincien (Frigate with bonus vs defenseless)",
        "key_improvement": "Polder (Food, production, on coast/lakes)",
        "strategy": "Trade and coast. Rivers are key. Polders for coastal food. Great merchants focus."
    },
    "scotland": {
        "identity": "Scotland",
        "key_unit": "Highlander (Ranger with combat bonus)",
        "key_building": "Golf Course (Amenities, gold, tourism)",
        "strategy": "Happiness is power. Production and science bonuses when happy. Campus and industrial zones."
    },
    "zulu": {
        "identity": "Zulu",
        "key_unit": "Impi (Fast, cheap, flanking bonus)",
        "key_building": "Ikanda (Encampment, corps earlier)",
        "strategy": "Corps and army rush. Cheaper to form corps/armies. Impi swarm mid-game. Never stop training."
    },
    "canada": {
        "identity": "Canada",
        "key_unit": "Mountie (Creates national parks)",
        "key_improvement": "Ice Hockey Rink (Culture, tourism, tundra)",
        "strategy": "Diplomatic victory. Cannot be surprise warred. Emergency and competition bonuses."
    },
    "hungary": {
        "identity": "Hungary",
        "key_unit": "Huszar (Light cavalry, bonus from alliances)",
        "key_building": "Thermal Bath (Amenities, production, tourism)",
        "strategy": "Levy city-states. Upgraded levied units. Geothermal focus. Alliance warrior."
    },
    "inca": {
        "identity": "Inca",
        "key_unit": "Warak'aq (Skirmisher with extra attack)",
        "key_improvement": "Terrace Farm (Food on hills, adjacency)",
        "strategy": "Mountain master. Tunnels through mountains. Terrace farms stack food. Internal trade for food."
    },
    "mali": {
        "identity": "Mali",
        "key_unit": "Mandekalu Cavalry (Cavalry that protects traders)",
        "key_building": "Suguba (Market replacement, faith purchasing)",
        "strategy": "Gold economy. Reduced production, massive gold. Faith and gold purchasing. Desert mines."
    },
    "maori": {
        "identity": "Maori",
        "key_unit": "Toa (Haka reduces enemy strength)",
        "key_building": "Marae (Culture to all tiles in city)",
        "strategy": "Start at sea. No settling on first turn. Woods and rainforest preservation. Mana from features."
    },
    "ottoman": {
        "identity": "Ottoman",
        "key_unit": "Barbary Corsair (Naval raider, coastal raids)",
        "key_building": "Grand Bazaar (Extra amenities, strategic resources)",
        "strategy": "Siege and siege. Faster siege unit production. Conquered cities assimilate faster."
    },
    "phoenicia": {
        "identity": "Phoenicia",
        "key_unit": "Bireme (Galley replacement, trader protection)",
        "key_district": "Cothon (Harbor, fast naval production)",
        "strategy": "Coastal empire. Move capital to any city with Cothon. Mediterranean playstyle."
    },
    "sweden": {
        "identity": "Sweden",
        "key_unit": "Carolean (Combat bonus from unused movement)",
        "key_building": "Queen's Bibliotheque (Writing slots, great people)",
        "strategy": "Great people and diplomacy. Nobel Prize bonuses. Automatic themed museums."
    },
}

# Victory goals for selection
VICTORY_GOALS = [
    ("Domination", "Capture all original enemy capitals through military conquest."),
    ("Science", "Launch a Mars colony through technological advancement."),
    ("Culture", "Attract more tourists than any other civ has domestic tourists."),
    ("Religious", "Convert the majority of cities in all civilizations to your religion."),
    ("Diplomatic", "Earn diplomatic victory points through World Congress and emergencies."),
    ("Score", "Have the highest score after 500 turns (balanced approach)."),
]
