"""
Game state enrichment and processing for the Civ VI AI Advisor.
Includes the Fog Trimmer algorithm for token optimization.
"""

import re
import copy
from typing import Optional

from .constants import MAP_SYMBOLS, CIV_STRATEGIES, CIVS_SUMMARY_FILE, LEADERS_FILE
from .map_processor import AsciiMapGenerator


# ============================================================================
# DATA FILE LOADERS
# ============================================================================

def _load_data_file(filepath) -> dict:
    """
    Load a data file with format:
    === SECTION_NAME ===
    Content line 1
    Content line 2

    === ANOTHER_SECTION ===
    ...

    Returns dict mapping section names (lowercase, spaces to underscores) to content strings.
    """
    data = {}
    if not filepath.exists():
        return data

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Split by section headers
        import re
        sections = re.split(r'^===\s*(.+?)\s*===$', content, flags=re.MULTILINE)

        # sections[0] is before first header (usually empty)
        # sections[1] is first header name, sections[2] is first content, etc.
        for i in range(1, len(sections), 2):
            if i + 1 < len(sections):
                header = sections[i].strip()
                body = sections[i + 1].strip()
                # Normalize key: "AMERICA" -> "america", "T_ROOSEVELT" -> "t_roosevelt"
                key = header.lower().replace(" ", "_")
                data[key] = body
    except Exception as e:
        print(f"Error loading data file {filepath}: {e}")

    return data


def _clean_leader_id(leader_str: str) -> str:
    """
    Clean leader ID from Lua format.
    "LEADER_HAMMURABI" -> "hammurabi"
    "LEADER_T_ROOSEVELT_ROUGHRIDER" -> "t_roosevelt_roughrider"
    """
    if not leader_str:
        return ""
    result = leader_str.upper()
    if result.startswith("LEADER_"):
        result = result[7:]  # Remove "LEADER_" prefix
    return result.lower()


def _clean_civ_id(civ_str: str) -> str:
    """
    Clean civilization name for lookup.
    "Sumeria" -> "sumeria"
    "America" -> "america"
    """
    if not civ_str:
        return ""
    return civ_str.lower().replace(" ", "_")


# Cache for loaded data files
_civs_data_cache = None
_leaders_data_cache = None


def get_civs_data() -> dict:
    """Load and cache civs_summary.txt data."""
    global _civs_data_cache
    if _civs_data_cache is None:
        _civs_data_cache = _load_data_file(CIVS_SUMMARY_FILE)
    return _civs_data_cache


def get_leaders_data() -> dict:
    """Load and cache leaders.txt data."""
    global _leaders_data_cache
    if _leaders_data_cache is None:
        _leaders_data_cache = _load_data_file(LEADERS_FILE)
    return _leaders_data_cache


def format_number(num) -> str:
    """
    Smart number formatting to save tokens.
    - If > 50: round to integer
    - If <= 50: round to 1 decimal, strip .0
    """
    if num is None:
        return "0"
    try:
        num = float(num)
    except (ValueError, TypeError):
        return str(num)

    if abs(num) > 50:
        return str(int(round(num)))
    else:
        rounded = round(num, 1)
        if rounded == int(rounded):
            return str(int(rounded))
        else:
            return str(rounded)


# Era index to name mapping (Civ VI era indices)
ERA_NAMES = {
    0: "Ancient",
    1: "Classical",
    2: "Medieval",
    3: "Renaissance",
    4: "Industrial",
    5: "Modern",
    6: "Atomic",
    7: "Information",
    8: "Future",
}


def get_era_name(era_value) -> str:
    """Convert era index to readable name."""
    if era_value is None:
        return "?"
    if isinstance(era_value, int):
        return ERA_NAMES.get(era_value, f"Era {era_value}")
    if isinstance(era_value, str):
        # Already a string, clean it
        return clean_game_string(era_value) or era_value
    return str(era_value)


# Prefixes to strip from verbose Civ VI strings
_VERBOSE_PREFIXES = (
    "BUILDING_",
    "UNIT_",
    "TECH_",
    "CIVIC_",
    "DISTRICT_",
    "IMPROVEMENT_",
    "RESOURCE_",
    "FEATURE_",
    "TERRAIN_",
    "PROMOTION_",
    "POLICY_",
    "GOVERNMENT_",
    "BELIEF_",
    "RELIGION_",
    "GREAT_PERSON_",
    "PROJECT_",
    "WONDER_",
    "ERA_",
    "CIVILIZATION_",
    "LEADER_",
)


def clean_game_string(s: str) -> str:
    """
    Clean verbose Civ VI game strings.
    Examples:
        BUILDING_MONUMENT -> Monument
        UNIT_WARRIOR -> Warrior
        TECH_MINING -> Mining
        CIVIC_CODE_OF_LAWS -> Code Of Laws
    """
    if not s or not isinstance(s, str):
        return s if s else ""

    # Skip if already clean (no underscore or lowercase)
    if "_" not in s or s[0].islower():
        return s

    result = s
    for prefix in _VERBOSE_PREFIXES:
        if result.upper().startswith(prefix):
            result = result[len(prefix):]
            break

    # Replace underscores with spaces and convert to title case
    result = result.replace("_", " ").title()

    return result


def clean_game_string_in_text(text: str) -> str:
    """
    Clean verbose Civ VI prefixes found anywhere in a text string.
    Handles strings like "UNIT_WARRIOR 18,18 100hp 2/2m" -> "Warrior 18,18 100hp 2/2m"
    """
    if not text or not isinstance(text, str):
        return text if text else ""

    result = text
    for prefix in _VERBOSE_PREFIXES:
        # Case-insensitive replacement of prefix at word boundaries
        pattern = re.compile(r'\b' + prefix, re.IGNORECASE)
        result = pattern.sub('', result)

    # Clean up any remaining ALL_CAPS_WORDS with underscores
    def replace_caps_underscored(match):
        word = match.group(0)
        return word.replace("_", " ").title()

    result = re.sub(r'\b[A-Z][A-Z_]+[A-Z]\b', replace_caps_underscored, result)

    return result


def clean_game_list(items: list) -> list:
    """Clean a list of game strings."""
    return [clean_game_string_in_text(item) for item in items]


class GameStateEnricher:
    """Enriches raw game state JSON with LLM-optimized context."""

    def __init__(self):
        self.previous_state: Optional[dict] = None
        self.previous_turn: int = -1
        self.is_first_turn: bool = True
        self.map_generator = AsciiMapGenerator()

    def enrich(self, game_state: dict, victory_goal: str = "") -> dict:
        """
        Enrich raw game state with:
        - Decision priorities
        - ASCII mini-map (with Fog Trimmer)
        - Civ strategy context
        - Delta tracking (only changed data)
        - Formatted numbers
        """
        current_turn = game_state.get("turn", 0)
        is_new_turn = current_turn != self.previous_turn

        # Compute what changed
        delta_info = self._compute_full_delta(game_state)

        enriched = {
            "raw": game_state,
            "decisions": self._extract_decisions(game_state),
            "mini_map": self.map_generator.generate_mini_map(game_state),
            "civ_context": self._get_civ_context(game_state) if self.is_first_turn else "",
            "changes_summary": delta_info["summary"],
            "delta": delta_info,
            "victory_goal": victory_goal,
            "is_first_turn": self.is_first_turn,
        }

        # Cache for next turn delta
        if is_new_turn:
            self.previous_state = copy.deepcopy(game_state)
            self.previous_turn = current_turn
            self.is_first_turn = False

        return enriched

    def _extract_decisions(self, gs: dict) -> dict:
        """Extract immediate decisions needed."""
        decisions = {
            "needs_tech": gs.get("needsTech", False),
            "needs_civic": gs.get("needsCivic", False),
            "needs_production": gs.get("needsProd", False),
            "cities_idle": [],
            "units_with_moves": [],
            "threats_nearby": [],
            "has_settler": False,
            "settler_location": None,
        }

        # Find cities needing production
        for city in gs.get("cities", []):
            if city.get("bld") in ["None", "", None]:
                decisions["cities_idle"].append(city.get("n", "?"))

        # Find units with movement remaining and detect settlers
        for unit_str in gs.get("units", []):
            unit_str_clean = clean_game_string_in_text(unit_str)
            unit_str_lower = unit_str_clean.lower()

            # Detect settler units
            if "settler" in unit_str_lower:
                decisions["has_settler"] = True
                # Extract settler location
                loc_match = re.search(r"(\d+),(\d+)", unit_str)
                if loc_match:
                    decisions["settler_location"] = (int(loc_match.group(1)), int(loc_match.group(2)))

            # Parse "Warrior 18,18 100hp 2/2m"
            match = re.search(r"(\d+)/(\d+)m$", unit_str)
            if match:
                moves_left = int(match.group(1))
                if moves_left > 0:
                    decisions["units_with_moves"].append(unit_str_clean)

        # Extract threats
        decisions["threats_nearby"] = clean_game_list(gs.get("threats", []))

        return decisions

    def _generate_tile_details(self, gs: dict) -> str:
        """
        Generate detailed tile information with relative coordinates.

        Filters to include only "interesting" tiles:
        - Tiles with Resources
        - Tiles with Features (Forest, Marsh, Jungle, etc.)
        - Tiles with Improvements (marked with 'i' flag)
        - Tiles with total yield > 4
        - Tiles adjacent to reference point (within distance 2)
        """
        tiles = gs.get("tiles", [])

        if not tiles:
            return ""

        # Get reference point (capital, settler, or first unit)
        ref_x, ref_y = self.map_generator.get_reference_point(gs)

        if ref_x is None:
            return ""

        # Determine reference type for header
        cities = gs.get("cities", [])
        if cities:
            ref_label = "Capital"
        else:
            ref_label = "Settler"

        def to_rel(abs_x, abs_y):
            return (abs_x - ref_x, abs_y - ref_y)

        def manhattan_distance(x1, y1, x2, y2):
            return abs(x1 - x2) + abs(y1 - y2)

        # Features that are "interesting"
        interesting_features = {"forest", "marsh", "jungle", "rainforest", "floodplains", "oasis", "reef"}

        filtered_tiles = []

        for tile_str in tiles:
            # Parse format: "x,y: Terrain Feature Resource (yields) i"
            # Example: "18,20: Plains Forest Spices (3f,3p,3g) i"
            match = re.match(r"(\d+),(\d+):\s*(.+)", tile_str)
            if not match:
                continue

            abs_x = int(match.group(1))
            abs_y = int(match.group(2))
            content = match.group(3)

            rel_x, rel_y = to_rel(abs_x, abs_y)

            # Parse the content to determine if it's interesting
            content_lower = content.lower()

            # Check for improvement/district in brackets [Farm], [Campus], etc.
            improvement_match = re.search(r"\[([^\]]+)\]", content)
            improvement_name = improvement_match.group(1) if improvement_match else None
            has_improvement = improvement_name is not None

            # Parse yields from parentheses
            yield_match = re.search(r"\(([^)]+)\)", content)
            total_yield = 0
            yield_str = ""
            if yield_match:
                yield_str = yield_match.group(1)
                # Parse yields like "3f,2p,1g"
                for part in yield_str.split(","):
                    part = part.strip()
                    if part and part[:-1].isdigit():
                        total_yield += int(part[:-1])

            # Check if adjacent to reference point (capital or settler)
            is_adjacent = manhattan_distance(abs_x, abs_y, ref_x, ref_y) <= 2

            # Check for interesting features
            has_interesting_feature = any(feat in content_lower for feat in interesting_features)

            # Check for resources (anything that isn't terrain/feature/yield)
            # Resources are typically single words like "Spices", "Iron", "Horses"
            resource_indicators = ["iron", "horse", "coal", "oil", "uranium", "aluminum", "niter",
                                   "spice", "silk", "dye", "ivory", "fur", "cotton", "sugar",
                                   "wine", "incense", "marble", "copper", "diamond", "jade",
                                   "silver", "gold", "pearl", "whale", "crab", "fish", "deer",
                                   "cattle", "sheep", "stone", "rice", "wheat", "maize", "banana",
                                   "citrus", "coffee", "tobacco", "tea", "mercury", "salt", "amber",
                                   "gypsum", "honey", "truffles", "olives", "turtle", "cocoa"]
            has_resource = any(res in content_lower for res in resource_indicators)

            # Apply filtering rules
            should_include = (
                has_resource or
                has_interesting_feature or
                has_improvement or
                total_yield > 4 or
                is_adjacent
            )

            if should_include:
                # Format the description - remove yield parentheses and brackets, reformat
                desc_parts = re.sub(r"\s*\([^)]+\)\s*", " ", content)  # Remove yields
                desc_parts = re.sub(r"\s*\[[^\]]+\]\s*", " ", desc_parts)  # Remove improvement brackets
                desc_parts = desc_parts.strip()

                # Build yield abbreviation (F=food, P=prod, G=gold, S=sci, C=cul, H=faith)
                if yield_str:
                    # Convert to uppercase format: "3F 2P 1G"
                    yield_formatted = yield_str.upper().replace(",", " ")
                    tile_output = f"[{rel_x:+d},{rel_y:+d}]: {desc_parts} ({yield_formatted})"
                else:
                    tile_output = f"[{rel_x:+d},{rel_y:+d}]: {desc_parts}"

                # Add improvement/district name if present
                if improvement_name:
                    tile_output += f" [{improvement_name}]"

                filtered_tiles.append((abs(rel_x) + abs(rel_y), tile_output))  # Sort by distance

        if not filtered_tiles:
            return ""

        # Sort by distance from reference point
        filtered_tiles.sort(key=lambda x: x[0])

        lines = ["=== VISIBLE TILE DETAILS ==="]
        lines.append(f"({len(filtered_tiles)} notable tiles, coordinates relative to {ref_label} at 0,0)")
        for _, tile_line in filtered_tiles:
            lines.append(f"  {tile_line}")

        return "\n".join(lines)

    def _get_civ_context(self, gs: dict) -> str:
        """
        Get civilization and leader context from external data files.

        Returns two sections:
        1. Civilization Context (from civs_summary.txt) - Unique units, infrastructure, general bias
        2. Leader Context (from leaders.txt) - Leader-specific abilities and strategies
        """
        civ_name = gs.get("civ", "")
        leader_raw = gs.get("leader", "")

        sections = []

        # === CIVILIZATION CONTEXT ===
        civ_key = _clean_civ_id(civ_name)
        civs_data = get_civs_data()

        # Try exact match first, then fuzzy match
        civ_content = civs_data.get(civ_key)
        if not civ_content:
            # Fuzzy match: check if civ_key is contained in any key or vice versa
            for key in civs_data:
                if civ_key in key or key in civ_key:
                    civ_content = civs_data[key]
                    break

        if civ_content:
            sections.append(f"=== CIVILIZATION: {civ_name.upper()} ===\n{civ_content}")
        else:
            # Fallback to hardcoded CIV_STRATEGIES if external file not found
            civ_name_lower = civ_name.lower().replace(" ", "")
            civ_info = None
            for key in CIV_STRATEGIES:
                if key in civ_name_lower or civ_name_lower in key:
                    civ_info = CIV_STRATEGIES[key]
                    break
            if civ_info:
                lines = [f"=== CIVILIZATION: {civ_info['identity'].upper()} ==="]
                if "key_unit" in civ_info:
                    lines.append(f"Unique Unit: {civ_info['key_unit']}")
                if "key_improvement" in civ_info:
                    lines.append(f"Unique Improvement: {civ_info['key_improvement']}")
                if "key_building" in civ_info:
                    lines.append(f"Unique Building: {civ_info['key_building']}")
                if "key_district" in civ_info:
                    lines.append(f"Unique District: {civ_info['key_district']}")
                lines.append(f"Strategy: {civ_info['strategy']}")
                sections.append("\n".join(lines))

        # === LEADER CONTEXT ===
        leader_key = _clean_leader_id(leader_raw)
        leaders_data = get_leaders_data()

        # Try exact match first, then fuzzy match
        leader_content = leaders_data.get(leader_key)
        if not leader_content:
            # Fuzzy match
            for key in leaders_data:
                if leader_key in key or key in leader_key:
                    leader_content = leaders_data[key]
                    break

        if leader_content:
            # Clean up leader name for display
            leader_display = leader_raw.replace("LEADER_", "").replace("_", " ").title()
            sections.append(f"=== LEADER: {leader_display} ===\n{leader_content}")

        return "\n\n".join(sections)

    def _compute_full_delta(self, gs: dict) -> dict:
        """Compute comprehensive delta - what changed and what to transmit."""
        delta = {
            "summary": "",
            "is_first": self.previous_state is None,
            "yields_changed": False,
            "tech_changed": False,
            "civic_changed": False,
            "cities_changed": False,
            "units_changed": False,
            "threats_changed": False,
            "diplo_changed": False,
            "cs_changed": False,
            "trade_changed": False,
            "new_cities": [],
            "lost_cities": [],
            "new_units": [],
            "lost_units": [],
            "diplo_changes": [],
        }

        if self.previous_state is None:
            delta["summary"] = "First turn of session - sending full state."
            return delta

        prev = self.previous_state
        changes = []

        prev_turn = prev.get("turn", 0)
        curr_turn = gs.get("turn", 0)
        if curr_turn == prev_turn:
            delta["summary"] = "Same turn - no changes."
            return delta

        changes.append(f"Turn {prev_turn} -> {curr_turn}")

        # Yields
        prev_gpt = prev.get("gpt", 0)
        curr_gpt = gs.get("gpt", 0)
        prev_sci = prev.get("sci", 0)
        curr_sci = gs.get("sci", 0)
        prev_cul = prev.get("cul", 0)
        curr_cul = gs.get("cul", 0)
        prev_faith = prev.get("faith", 0)
        curr_faith = gs.get("faith", 0)

        if curr_gpt != prev_gpt or curr_sci != prev_sci or curr_cul != prev_cul or curr_faith != prev_faith:
            delta["yields_changed"] = True

        prev_gold = prev.get("gold", 0)
        curr_gold = gs.get("gold", 0)
        if curr_gold != prev_gold:
            gold_delta = curr_gold - prev_gold
            sign = "+" if gold_delta > 0 else ""
            changes.append(f"Gold {sign}{format_number(gold_delta)} ({format_number(curr_gold)})")

        # Tech
        prev_tech = prev.get("tech", "")
        curr_tech = gs.get("tech", "")
        if prev_tech != curr_tech:
            delta["tech_changed"] = True
            if prev_tech and prev_tech != curr_tech:
                changes.append(f"Tech '{clean_game_string(prev_tech)}' completed")
            if curr_tech:
                changes.append(f"Now researching: {clean_game_string(curr_tech)}")

        # Civic
        prev_civic = prev.get("civic", "")
        curr_civic = gs.get("civic", "")
        if prev_civic != curr_civic:
            delta["civic_changed"] = True
            if prev_civic and prev_civic != curr_civic:
                changes.append(f"Civic '{clean_game_string(prev_civic)}' completed")
            if curr_civic:
                changes.append(f"Now developing: {clean_game_string(curr_civic)}")

        # Cities
        prev_city_names = {c.get("n") for c in prev.get("cities", [])}
        curr_city_names = {c.get("n") for c in gs.get("cities", [])}
        new_cities = curr_city_names - prev_city_names
        lost_cities = prev_city_names - curr_city_names

        if new_cities or lost_cities:
            delta["cities_changed"] = True
            delta["new_cities"] = list(new_cities)
            delta["lost_cities"] = list(lost_cities)
            if new_cities:
                changes.append(f"New city: {', '.join(new_cities)}")
            if lost_cities:
                changes.append(f"Lost city: {', '.join(lost_cities)}")

        if not delta["cities_changed"]:
            prev_city_prod = {c.get("n"): c.get("bld") for c in prev.get("cities", [])}
            curr_city_prod = {c.get("n"): c.get("bld") for c in gs.get("cities", [])}
            if prev_city_prod != curr_city_prod:
                delta["cities_changed"] = True

        # Units
        prev_units = set(prev.get("units", []))
        curr_units = set(gs.get("units", []))

        if len(curr_units) != len(prev_units):
            delta["units_changed"] = True
            if len(curr_units) > len(prev_units):
                changes.append(f"+{len(curr_units) - len(prev_units)} new unit(s)")
            else:
                changes.append(f"-{len(prev_units) - len(curr_units)} unit(s) lost")

        # Threats
        prev_threats = prev.get("threats", [])
        curr_threats = gs.get("threats", [])
        if set(prev_threats) != set(curr_threats):
            delta["threats_changed"] = True
            if len(curr_threats) > len(prev_threats):
                changes.append(f"New threat(s)!")
            elif len(curr_threats) < len(prev_threats):
                changes.append(f"Threats reduced")

        # Diplomacy (now rich dicts, compare by civ+status)
        def diplo_key(entry):
            if isinstance(entry, dict):
                return f"{entry.get('civ', '')}:{entry.get('status', '')}"
            return str(entry)

        prev_diplo_keys = {diplo_key(d) for d in prev.get("diplo", [])}
        curr_diplo_keys = {diplo_key(d) for d in gs.get("diplo", [])}
        if prev_diplo_keys != curr_diplo_keys:
            delta["diplo_changed"] = True
            new_diplo = curr_diplo_keys - prev_diplo_keys
            if new_diplo:
                delta["diplo_changes"] = list(new_diplo)
                changes.append(f"Diplo change: {', '.join(new_diplo)}")

        # City States
        prev_cs = set(prev.get("cs", []))
        curr_cs = set(gs.get("cs", []))
        if prev_cs != curr_cs:
            delta["cs_changed"] = True

        # Trade
        prev_trade = set(prev.get("trade", []))
        curr_trade = set(gs.get("trade", []))
        if prev_trade != curr_trade:
            delta["trade_changed"] = True

        if len(changes) == 1:
            changes.append("No significant changes.")

        delta["summary"] = " | ".join(changes)
        return delta

    def build_prompt(self, enriched: dict, user_question: str = "") -> str:
        """Build the final prompt for the AI using delta tracking."""
        sections = []
        gs = enriched["raw"]
        delta = enriched["delta"]
        is_first = enriched["is_first_turn"]

        # 0. DECISIONS FIRST (highest priority at top)
        decisions = enriched["decisions"]
        decision_lines = ["=== IMMEDIATE DECISIONS REQUIRED ==="]

        # HIGHEST PRIORITY: Settler placement
        if decisions["has_settler"]:
            settler_loc = decisions.get("settler_location")
            if settler_loc:
                decision_lines.append(f"*** SETTLER ACTIVE at ({settler_loc[0]},{settler_loc[1]}): Recommend optimal settlement location! ***")
            else:
                decision_lines.append("*** SETTLER ACTIVE: Recommend optimal settlement location! ***")

        if decisions["needs_tech"]:
            decision_lines.append("CHOOSE TECH: No technology being researched!")
        if decisions["needs_civic"]:
            decision_lines.append("CHOOSE CIVIC: No civic being developed!")
        if decisions["needs_production"] or decisions["cities_idle"]:
            cities = ", ".join(decisions["cities_idle"]) if decisions["cities_idle"] else "Some cities"
            decision_lines.append(f"SET PRODUCTION: {cities} idle!")
        if decisions["units_with_moves"]:
            decision_lines.append(f"MOVE UNITS: {len(decisions['units_with_moves'])} unit(s) have moves")
        if decisions["threats_nearby"]:
            decision_lines.append(f"THREATS: {len(decisions['threats_nearby'])} hostile unit(s) visible!")

        if len(decision_lines) == 1:
            decision_lines.append("No immediate decisions required.")

        sections.append("\n".join(decision_lines))

        # 1. Changes since last turn
        sections.append(f"=== CHANGES SINCE LAST TURN ===\n{enriched['changes_summary']}")

        # 2. Civ context - ONLY on first turn
        if is_first and enriched["civ_context"]:
            sections.append(f"=== CIVILIZATION STRATEGY ===\n{enriched['civ_context']}")

        # 3. Mini-map (with Fog Trimmer)
        sections.append(f"=== TACTICAL VIEW ===\n{enriched['mini_map']}")

        # 3.5 Tile details (with filtering)
        tile_details = self._generate_tile_details(gs)
        if tile_details:
            sections.append(tile_details)

        # 4. Current state summary
        state_lines = ["=== CURRENT STATE ==="]
        if is_first:
            state_lines.append(f"Turn {gs.get('turn', '?')} | Era: {get_era_name(gs.get('era'))} | Civ: {clean_game_string(gs.get('civ', '?'))}")
        else:
            state_lines.append(f"Turn {gs.get('turn', '?')} | Era: {get_era_name(gs.get('era'))}")

        state_lines.append(f"Gold: {format_number(gs.get('gold', 0))} ({format_number(gs.get('gpt', 0))}/turn)")
        state_lines.append(f"Science: {format_number(gs.get('sci', 0))}/turn | Culture: {format_number(gs.get('cul', 0))}/turn")
        if gs.get("faith"):
            state_lines.append(f"Faith: {format_number(gs.get('faith', 0))}/turn (Balance: {format_number(gs.get('faithBal', 0))})")

        if gs.get("tech"):
            state_lines.append(f"Researching: {clean_game_string(gs.get('tech'))} ({gs.get('techPct', 0)}%)")
        if gs.get("civic"):
            state_lines.append(f"Developing: {clean_game_string(gs.get('civic'))} ({gs.get('civicPct', 0)}%)")

        sections.append("\n".join(state_lines))

        # 5. Cities - ALWAYS show city list with production status
        cities = gs.get("cities", [])
        if cities:
            # Get capital coordinates for relative position display
            capital_xy = cities[0].get("xy", "") if cities else ""
            cap_x, cap_y = 0, 0
            if capital_xy:
                cap_parts = capital_xy.split(",")
                if len(cap_parts) == 2:
                    cap_x, cap_y = int(cap_parts[0]), int(cap_parts[1])

            city_lines = [f"=== CITIES ({len(cities)}) ==="]
            for city in cities:
                name = city.get("n", "?")
                pop = city.get("pop", 0)
                bld = clean_game_string(city.get("bld", "None"))
                turns_raw = city.get("turns", -1)
                turns = turns_raw if turns_raw is not None and turns_raw >= 0 else "?"
                grow = city.get("grow", "?")
                needs_production = (bld == "None" or bld == "" or bld is None)

                # Basic city line - always shown
                if needs_production:
                    city_lines.append(f"  {name} (pop {pop}): *** NEEDS PRODUCTION *** | Growth in {grow}t")
                else:
                    city_lines.append(f"  {name} (pop {pop}): Building {bld} ({turns}t) | Growth in {grow}t")

                # Show full details for cities needing production OR on first turn OR when changed
                show_full_details = needs_production or is_first or delta["cities_changed"]

                if show_full_details:
                    # Show city location relative to capital
                    city_xy = city.get("xy", "")
                    if city_xy and city_xy != capital_xy:
                        xy_parts = city_xy.split(",")
                        if len(xy_parts) == 2:
                            cx, cy = int(xy_parts[0]), int(xy_parts[1])
                            rel_x, rel_y = cx - cap_x, cy - cap_y
                            city_lines.append(f"    Location: [{rel_x:+d},{rel_y:+d}] from capital")

                    # Show districts if present
                    districts = city.get("districts", [])
                    if districts:
                        district_str = ", ".join(clean_game_list(districts))
                        city_lines.append(f"    Districts: {district_str}")

                    # Show buildings if present (! = wonder)
                    buildings = city.get("buildings", [])
                    if buildings:
                        building_str = ", ".join(clean_game_list(buildings))
                        city_lines.append(f"    Buildings: {building_str}")

                    # Show wonders with their precise locations (for adjacency planning)
                    wonders = city.get("wonders", [])
                    if wonders:
                        wonder_lines = []
                        for wonder_str in wonders:
                            # Parse "Colosseum 18,20" format and convert to relative coords
                            match = re.match(r"(.+?)\s+(\d+),(\d+)$", wonder_str)
                            if match:
                                wonder_name = clean_game_string(match.group(1))
                                wx, wy = int(match.group(2)), int(match.group(3))
                                rel_x, rel_y = wx - cap_x, wy - cap_y
                                wonder_lines.append(f"{wonder_name} [{rel_x:+d},{rel_y:+d}]")
                            else:
                                wonder_lines.append(clean_game_string(wonder_str))
                        city_lines.append(f"    Wonders: {', '.join(wonder_lines)}")

            sections.append("\n".join(city_lines))

        # 6. Units
        units = clean_game_list(gs.get("units", []))
        if units and (is_first or delta["units_changed"]):
            sections.append(f"=== UNITS ({len(units)}) ===\n  " + " | ".join(units[:10]))
            if len(units) > 10:
                sections[-1] += f"\n  ... and {len(units) - 10} more"
        elif units and not is_first:
            sections.append(f"=== UNITS ({len(units)}) === [unchanged]")

        # 7. Threats - ALWAYS send if present
        threats = clean_game_list(gs.get("threats", []))
        if threats:
            sections.append(f"=== THREATS ({len(threats)}) ===\n  " + "\n  ".join(threats))

        # 8. Diplomacy (now includes rich stats from scoreboard)
        diplo = gs.get("diplo", [])
        if diplo and (is_first or delta["diplo_changed"]):
            diplo_lines = []
            for entry in diplo:
                if isinstance(entry, dict):
                    # Rich format: {civ, leader, status, score, military, culture_pt, science_pt, tourism, gold}
                    civ = entry.get("civ", "?")
                    leader = entry.get("leader", "").replace("LEADER_", "").replace("_", " ").title()
                    status = entry.get("status", "?")
                    parts = [f"{civ} ({leader}): {status}"]

                    stats = []
                    if "score" in entry:
                        stats.append(f"Score:{entry['score']}")
                    if "military" in entry:
                        stats.append(f"Mil:{entry['military']}")
                    if "science_pt" in entry:
                        stats.append(f"Sci/t:{entry['science_pt']}")
                    if "culture_pt" in entry:
                        stats.append(f"Cul/t:{entry['culture_pt']}")
                    if "tourism" in entry:
                        stats.append(f"Tourism:{entry['tourism']}")
                    if "gold" in entry:
                        stats.append(f"Gold:{entry['gold']}")

                    if stats:
                        parts.append(" | ".join(stats))
                    diplo_lines.append("  " + " - ".join(parts))
                else:
                    # Legacy simple format: "CivName:Status"
                    diplo_lines.append(f"  {entry}")

            sections.append(f"=== DIPLOMACY ({len(diplo)} civs) ===\n" + "\n".join(diplo_lines))
        elif diplo and delta.get("diplo_changes"):
            sections.append(f"=== DIPLOMACY CHANGES ===\n  " + " | ".join(clean_game_list(delta["diplo_changes"])))

        # 8b. Foreign Cities (city centers and encampments of known civs)
        foreign_cities = clean_game_list(gs.get("foreign_cities", []))
        if foreign_cities and is_first:
            sections.append(f"=== FOREIGN CITIES ({len(foreign_cities)}) ===\n  " + "\n  ".join(foreign_cities[:20]))
            if len(foreign_cities) > 20:
                sections[-1] += f"\n  ... and {len(foreign_cities) - 20} more"

        # 8c. Foreign Tiles (discovered tiles owned by other civs with districts/improvements)
        foreign_tiles = clean_game_list(gs.get("foreign_tiles", []))
        if foreign_tiles and is_first:
            sections.append(f"=== FOREIGN TERRITORY ({len(foreign_tiles)} notable tiles) ===\n  " + "\n  ".join(foreign_tiles[:30]))
            if len(foreign_tiles) > 30:
                sections[-1] += f"\n  ... and {len(foreign_tiles) - 30} more"

        # 9. City States
        cs = clean_game_list(gs.get("cs", []))
        if cs and (is_first or delta["cs_changed"]):
            sections.append(f"=== CITY STATES ===\n  " + " | ".join(cs))

        # 10. Trade Routes
        trade = clean_game_list(gs.get("trade", []))
        if trade and (is_first or delta["trade_changed"]):
            sections.append(f"=== TRADE ROUTES ===\n  " + " | ".join(trade))

        # 11. Victory goal
        if enriched["victory_goal"]:
            sections.append(f"=== VICTORY GOAL: {enriched['victory_goal'].upper()} ===")

        # 12. User question
        if user_question:
            sections.append(f"=== PLAYER QUESTION ===\n{user_question}")

        return "\n\n".join(sections)
