"""
ASCII map generation for the Civ VI AI Advisor.
Handles mini-map rendering with fog trimming and coordinate systems.
"""

import re
from .constants import MAP_SYMBOLS


def clean_game_string(s: str) -> str:
    """Clean verbose Civ VI game strings (imported locally to avoid circular imports)."""
    if s is None:
        return ""
    s = str(s)
    prefixes = (
        "BUILDING_", "UNIT_", "TECH_", "CIVIC_", "DISTRICT_", "IMPROVEMENT_",
        "RESOURCE_", "FEATURE_", "TERRAIN_", "PROMOTION_", "POLICY_",
        "GOVERNMENT_", "BELIEF_", "RELIGION_", "GREAT_PERSON_", "PROJECT_",
        "WONDER_", "ERA_", "CIVILIZATION_", "LEADER_",
    )
    for prefix in prefixes:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return s.replace("_", " ").title()


class AsciiMapGenerator:
    """Generates ASCII tactical maps from game state data."""

    def generate_mini_map(self, gs: dict, radius: int = 7) -> str:
        """
        Generate ASCII mini-map with Fog Trimmer algorithm and Reference-Centered coordinates.

        Features:
        1. REFERENCE CENTER: Capital/Settler at (0,0), all coordinates are relative
        2. VOIDING: Replace "deep fog" cells (surrounded by fog) with empty space
        3. TRIMMING: Crop to the active bounding box containing data
        """
        cities = gs.get("cities", [])

        # Get reference point (capital, settler, or first unit)
        ref_abs_x, ref_abs_y = self.get_reference_point(gs)

        if ref_abs_x is None:
            return "No reference point - map unavailable."

        # Parse all city coordinates
        city_positions = []
        city_coords = {}  # absolute coord string -> city name abbrev
        capital_coord = None

        for i, city in enumerate(cities):
            xy = city.get("xy", "")
            if xy:
                parts = xy.split(",")
                if len(parts) == 2:
                    cx, cy = int(parts[0]), int(parts[1])
                    city_positions.append((cx, cy))
                    city_coords[xy] = city.get("n", "?")[:2]
                    if i == 0:  # First city is capital
                        capital_coord = xy

        # Determine reference label
        if cities:
            ref_label = "Capital"
        else:
            ref_label = "Settler"

        # Calculate bounding box in absolute coordinates
        if city_positions:
            min_abs_x = min(pos[0] for pos in city_positions) - radius
            max_abs_x = max(pos[0] for pos in city_positions) + radius
            min_abs_y = min(pos[1] for pos in city_positions) - radius
            max_abs_y = max(pos[1] for pos in city_positions) + radius
        else:
            # No cities - center around reference point (settler)
            min_abs_x = ref_abs_x - radius
            max_abs_x = ref_abs_x + radius
            min_abs_y = ref_abs_y - radius
            max_abs_y = ref_abs_y + radius

        # Limit map size to avoid massive outputs (max 25x25)
        MAX_DIM = 25
        width = max_abs_x - min_abs_x + 1
        height = max_abs_y - min_abs_y + 1

        if width > MAX_DIM:
            # Center around reference point
            min_abs_x = ref_abs_x - MAX_DIM // 2
            max_abs_x = ref_abs_x + MAX_DIM // 2

        if height > MAX_DIM:
            min_abs_y = ref_abs_y - MAX_DIM // 2
            max_abs_y = ref_abs_y + MAX_DIM // 2

        # Helper to convert absolute to relative coordinates
        def to_rel(abs_x, abs_y):
            return (abs_x - ref_abs_x, abs_y - ref_abs_y)

        def abs_coord_str(x, y):
            return f"{x},{y}"

        # Build coordinate sets for quick lookup (using absolute coords as keys)
        unit_coords = {}
        for unit_str in gs.get("units", []):
            match = re.match(r"(\w+)\s+(\d+),(\d+)", unit_str)
            if match:
                unit_type_raw = match.group(1)
                unit_type = clean_game_string(unit_type_raw).lower().replace(" ", "_")
                x, y = int(match.group(2)), int(match.group(3))
                coord = abs_coord_str(x, y)
                symbol = MAP_SYMBOLS.get(unit_type, unit_type[:2].capitalize())
                if coord not in unit_coords:
                    unit_coords[coord] = symbol

        threat_coords = {}
        for threat_str in gs.get("threats", []):
            match = re.search(r"(\w+)\s+\([^)]+\)\s+(\d+),(\d+)", threat_str)
            if match:
                x, y = int(match.group(2)), int(match.group(3))
                coord = abs_coord_str(x, y)
                if "barb" in threat_str.lower():
                    threat_coords[coord] = "!B"
                else:
                    threat_coords[coord] = "!E"

        tile_data = {}
        for tile_str in gs.get("tiles", []):
            match = re.match(r"(\d+),(\d+):\s*(.+)", tile_str)
            if match:
                x, y = int(match.group(1)), int(match.group(2))
                coord = abs_coord_str(x, y)
                content = match.group(3).lower()

                if "mountain" in content:
                    symbol = "^^"
                elif "hill" in content:
                    symbol = "/\\"
                elif "forest" in content:
                    symbol = "Fo"
                elif "jungle" in content:
                    symbol = "Jg"
                elif "marsh" in content:
                    symbol = "Ms"
                elif "desert" in content:
                    symbol = ".."
                elif "ocean" in content or "coast" in content:
                    symbol = "::"
                elif " i" in content:  # Improved
                    symbol = "Im"
                else:
                    symbol = "--"
                tile_data[coord] = symbol

        # ========== FOG TRIMMER ALGORITHM ==========

        # Step 1: Build initial grid with cell contents (using absolute coords internally)
        grid = {}  # (abs_x, abs_y) -> cell_content
        for y in range(min_abs_y, max_abs_y + 1):
            for x in range(min_abs_x, max_abs_x + 1):
                coord = abs_coord_str(x, y)

                # Determine cell content (priority order)
                if coord in threat_coords:
                    cell = threat_coords[coord]
                elif coord in unit_coords:
                    cell = unit_coords[coord]
                elif coord in city_coords:
                    cell = "C*" if coord == capital_coord else "Ct"
                elif coord == f"{ref_abs_x},{ref_abs_y}" and not cities:
                    # Mark settler/reference location when no cities
                    cell = "S*"
                elif coord in tile_data:
                    cell = tile_data[coord]
                else:
                    cell = "??"  # Fog

                grid[(x, y)] = cell

        # Step 2: VOIDING - Replace deep fog with void
        def is_deep_fog(x, y):
            if grid.get((x, y)) != "??":
                return False

            neighbors = [
                (x-1, y-1), (x, y-1), (x+1, y-1),
                (x-1, y),            (x+1, y),
                (x-1, y+1), (x, y+1), (x+1, y+1),
            ]

            for nx, ny in neighbors:
                neighbor_cell = grid.get((nx, ny))
                if neighbor_cell is not None and neighbor_cell != "??":
                    return False
            return True

        void_coords = set()
        for (x, y), cell in grid.items():
            if cell == "??" and is_deep_fog(x, y):
                void_coords.add((x, y))

        for coord in void_coords:
            grid[coord] = "  "

        # Step 3: TRIMMING - Find active bounding box
        active_min_x, active_max_x = max_abs_x, min_abs_x
        active_min_y, active_max_y = max_abs_y, min_abs_y

        for (x, y), cell in grid.items():
            if cell.strip():
                active_min_x = min(active_min_x, x)
                active_max_x = max(active_max_x, x)
                active_min_y = min(active_min_y, y)
                active_max_y = max(active_max_y, y)

        if active_min_x <= active_max_x and active_min_y <= active_max_y:
            min_abs_x, max_abs_x = active_min_x, active_max_x
            min_abs_y, max_abs_y = active_min_y, active_max_y

        # ========== END FOG TRIMMER ==========

        # Convert bounds to relative coordinates
        min_rel_x, min_rel_y = to_rel(min_abs_x, min_abs_y)
        max_rel_x, max_rel_y = to_rel(max_abs_x, max_abs_y)

        actual_width = max_rel_x - min_rel_x + 1
        actual_height = max_rel_y - min_rel_y + 1

        # Collect all symbols used in the visible grid area for dynamic legend
        used_symbols = set()
        for rel_y in range(max_rel_y, min_rel_y - 1, -1):
            abs_y = rel_y + ref_abs_y
            for rel_x in range(min_rel_x, max_rel_x + 1):
                abs_x = rel_x + ref_abs_x
                cell = grid.get((abs_x, abs_y), "  ")
                if cell.strip():
                    used_symbols.add(cell)

        # Symbol descriptions for legend (ordered by importance)
        symbol_descriptions = [
            ("C*", "Capital(0,0)"),
            ("S*", "Settler(0,0)"),
            ("Ct", "City"),
            ("!B", "Barb"),
            ("!E", "Enemy"),
            ("Wr", "Warrior"),
            ("Sc", "Scout"),
            ("St", "Settler"),
            ("Bl", "Builder"),
            ("Ar", "Archer"),
            ("Sl", "Slinger"),
            ("Sp", "Spearman"),
            ("Hr", "Horseman"),
            ("Kn", "Knight"),
            ("Sw", "Swordsman"),
            ("Xb", "Crossbow"),
            ("Ca", "Catapult"),
            ("Mu", "Musket"),
            ("Cv", "Cavalry"),
            ("In", "Infantry"),
            ("Tk", "Tank"),
            ("Tr", "Trader"),
            ("Ms", "Missionary"),
            ("Ap", "Apostle"),
            ("GG", "Gr.General"),
            ("GA", "Gr.Admiral"),
            ("GP", "Gr.Prophet"),
            ("GS", "Gr.Scientist"),
            ("GE", "Gr.Engineer"),
            ("GM", "Gr.Merchant"),
            ("^^", "Mountain"),
            ("/\\", "Hills"),
            ("Fo", "Forest"),
            ("Jg", "Jungle"),
            ("Ms", "Marsh"),
            ("..", "Desert"),
            ("::", "Water"),
            ("--", "Plains/Grass"),
            ("Im", "Improved"),
            ("??", "Fog"),
        ]

        # Build legend with only symbols that appear in the map
        legend_parts = []
        for symbol, desc in symbol_descriptions:
            if symbol in used_symbols:
                legend_parts.append(f"{symbol}={desc}")

        # Generate output with RELATIVE coordinates
        lines = []
        lines.append(f"Empire View ({actual_width}x{actual_height}, {ref_label}-Centered):")
        if legend_parts:
            lines.append("Legend: " + " ".join(legend_parts))
        lines.append("")

        # Add relative coordinate header
        if actual_width <= 20:
            header = "     "
            for rel_x in range(min_rel_x, max_rel_x + 1):
                if rel_x == 0:
                    header += "  0  "
                elif rel_x % 3 == 0:
                    header += f"{rel_x:+3}  "
                else:
                    header += "     "
            lines.append(header.rstrip())

        # Render rows from top to bottom (high Y to low Y)
        for rel_y in range(max_rel_y, min_rel_y - 1, -1):
            abs_y = rel_y + ref_abs_y

            # Row label with relative coordinate
            if actual_height <= 20:
                if rel_y == 0:
                    row_label = "  0  "
                else:
                    row_label = f"{rel_y:+3}  "
            else:
                row_label = ""

            row = []
            row_has_content = False

            for rel_x in range(min_rel_x, max_rel_x + 1):
                abs_x = rel_x + ref_abs_x
                cell = grid.get((abs_x, abs_y), "  ")
                if cell.strip():
                    row_has_content = True
                row.append(f"[{cell}]")

            if row_has_content:
                lines.append(row_label + " ".join(row))

        return "\n".join(lines)

    def get_reference_point(self, gs: dict) -> tuple:
        """
        Get the reference point for coordinate calculations.
        Priority: Capital city > First city > Settler location > First unit
        Returns (x, y) or (None, None) if no reference found.
        """
        # Try capital/first city
        cities = gs.get("cities", [])
        if cities:
            capital_xy = cities[0].get("xy", "")
            if capital_xy:
                parts = capital_xy.split(",")
                if len(parts) == 2:
                    return (int(parts[0]), int(parts[1]))

        # Try settler location
        for unit_str in gs.get("units", []):
            if "settler" in unit_str.lower():
                match = re.search(r"(\d+),(\d+)", unit_str)
                if match:
                    return (int(match.group(1)), int(match.group(2)))

        # Try first unit location
        for unit_str in gs.get("units", []):
            match = re.search(r"(\d+),(\d+)", unit_str)
            if match:
                return (int(match.group(1)), int(match.group(2)))

        return (None, None)
