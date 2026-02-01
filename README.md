# Civilization VI AI Advisor Bridge

A two-part system that reads Civilization VI game state and provides AI-powered strategic advice via a floating overlay.

## Components

1. **CivAI_Bridge** - A Civ VI Lua mod that logs game state to `Lua.log` at the start of each turn
2. **civ_advisor** - A Python package that reads the logs and provides AI advice through a desktop overlay

## Quick Start

```bash
# 1. Install the Lua mod (see detailed instructions below)
# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Run the advisor
python -m civ_advisor.main
```

---

## Installation

### Part 1: Install the Lua Mod

1. **Locate your Civ VI Mods folder:**
   ```
   Windows: C:\Users\<YourUsername>\Documents\My Games\Sid Meier's Civilization VI\Mods
   Mac: ~/Library/Application Support/Sid Meier's Civilization VI/Mods
   Linux: ~/.local/share/aspyr-media/Sid Meier's Civilization VI/Mods
   ```

2. **Copy the mod folder:**
   - Copy the entire `CivAI_Bridge` folder into the Mods folder
   - Final structure should be:
     ```
     .../Mods/CivAI_Bridge/
     ├── CivAI_Bridge.modinfo
     └── GameStateDump.lua
     ```

3. **Enable the mod in-game:**
   - Launch Civilization VI
   - Go to **Additional Content** from the main menu
   - Find **"CivAI Bridge - Game State Logger"** and enable it
   - Start a new game or load a save

### Part 2: Install the Python Package

1. **Requirements:**
   - Python 3.8 or higher
   - Tkinter (usually included with Python on Windows/Mac)

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

   Or install individually based on which providers you'll use:
   ```bash
   # Core (required)
   pip install requests

   # For Google Gemini
   pip install google-generativeai

   # For Anthropic Claude
   pip install anthropic

   # For OpenAI GPT
   pip install openai
   ```

3. **Run the overlay:**
   ```bash
   python -m civ_advisor.main
   ```

4. **First launch:**
   - Select your victory goal from the startup dialog
   - Click the gear icon to open Settings
   - Choose your AI provider and enter the required API key
   - Verify the Logs folder path matches your Civ VI installation

---

## AI Providers

The advisor supports multiple AI providers. Configure them in Settings > Model Selection.

| Provider | API Key Required | Cost | Notes |
|----------|-----------------|------|-------|
| **Google (Gemini)** | Yes | Free tier available | Auto-fallback: Flash Lite → Flash → Gemma 2 |
| **Anthropic (Claude)** | Yes | Paid | High quality responses |
| **OpenAI (GPT)** | Yes | Paid | GPT-4o recommended |
| **Ollama (Local)** | No | Free | Requires local Ollama server |
| **Clipboard (Manual)** | No | Free | Copies prompt for use with web interfaces |

### Getting API Keys

- **Google (Gemini):** https://makersuite.google.com/app/apikey
- **Anthropic (Claude):** https://console.anthropic.com/
- **OpenAI (GPT):** https://platform.openai.com/api-keys

### Ollama Setup (Local AI)

1. Install Ollama from https://ollama.ai
2. Pull a model: `ollama pull llama3`
3. Start Ollama (runs on http://localhost:11434 by default)
4. Select "Ollama (Local)" in the advisor settings

### Clipboard Mode

For users with paid web subscriptions (ChatGPT Plus, Claude Pro, Gemini Advanced):

1. Select "Clipboard (Manual)" as your provider
2. Click "Ask Advisor" - the full prompt is copied to your clipboard
3. Paste into your preferred AI chat interface
4. Copy the response back manually

---

## Usage

1. **Start the overlay:** `python -m civ_advisor.main`
2. **Launch Civ VI** with the mod enabled
3. **Start or load a game**
4. At each turn start, the overlay automatically receives game data
5. Select your **victory goal** from the dropdown
6. Type specific questions and press Enter or click "Ask Advisor"

### Features

- **Auto-detect game state** - Monitors Civ VI's Lua.log in real-time
- **Victory-focused advice** - Tailored recommendations for your chosen victory type
- **Capital-centered mini-map** - Tactical view with your capital at (0,0)
- **Fog trimmer** - Reduces token usage by trimming unexplored areas
- **Custom questions** - Ask specific questions about your situation
- **Always-on-top** - Optional setting to keep overlay visible over the game
- **Draggable window** - Position anywhere on screen
- **Civ VI themed UI** - Dark theme with gold accents

---

## How It Works

### Lua Mod (CivAI_Bridge)

The mod hooks into Civ VI's event system and exports game state at the **start of each turn**:

```
Events.LocalPlayerTurnBegin → DumpGameState() → Lua.log
```

**Data captured:**
- Turn number, era, civilization
- Treasury (gold, gold per turn)
- Yields (science, culture, faith)
- Current tech/civic research with progress %
- All cities: population, production queue, growth timer
- All units: type, position, health, remaining moves
- Visible threats: hostile units with distance from capital
- Diplomacy: relationship status with all met civs
- City-states: envoy counts, suzerain status
- Trade routes: origin and destination cities
- Visible tiles: terrain, features, resources, yields

**Output format:** JSON wrapped in markers for easy parsing:
```
>>>GAMESTATE>>>{"turn":42,"civ":"Rome",...}<<<END<<<
```

### Python Package (civ_advisor)

```
civ_advisor/
├── __init__.py      # Package init
├── main.py          # Entry point
├── constants.py     # Models, colors, civ strategies
├── config.py        # Settings management (saved to config.json)
├── log_watcher.py   # Monitors Lua.log for new game state
├── game_state.py    # Enriches raw data, generates mini-map
├── llm_client.py    # Handles API calls to all providers
└── gui.py           # Tkinter overlay interface
```

**Processing pipeline:**
1. `LogWatcher` detects new JSON in Lua.log
2. `GameStateEnricher` processes the data:
   - Cleans verbose strings (BUILDING_MONUMENT → Monument)
   - Generates capital-centered ASCII mini-map
   - Applies fog trimmer algorithm
   - Computes delta from previous turn
   - Adds civilization-specific strategy context
3. `AIAdvisor` sends enriched prompt to selected provider
4. Response displayed in overlay

### Mini-Map Coordinate System

The tactical view uses **capital-centered coordinates**:

```
Empire View (7x6, Capital-Centered):
Legend: C*=Capital(0,0) Ct=City !B=Barb !E=Enemy

      -3              0             +3
 +2  [  ] [  ] [  ] [Ct] [??] [??] [??]
 +1  [  ] [  ] [??] [??] [??] [  ] [??]
  0  [  ] [??] [??] [C*] [Wr] [??] [??]
 -1  [??] [??] [/\] [??] [??] [??] [  ]
 -2  [??] [!B] [??] [??] [  ] [  ] [  ]
```

- Capital is always at (0, 0)
- Positive Y = North, Negative Y = South
- Positive X = East, Negative X = West

---

## Settings

Access settings via the gear icon. Settings are organized into tabs:

### Model Selection
- Choose AI provider (Google, Anthropic, OpenAI, Ollama, Clipboard)
- Enter API keys for cloud providers
- Select specific model variants

### API Behavior
- **Rate limiting:** Enable 1 request/minute limit with token cap
- **Request throttle:** Minimum seconds between requests (default: 20s)

### Interface
- **Always on Top:** Keep overlay above other windows
- **Debug Mode:** Preview prompts before sending
- **Logs Folder:** Path to Civ VI's Logs directory

### System Prompts
- **Core prompt:** Sent with every request (rules, format)
- **Extended prompt:** Sent only on first turn (Civ VI context)

---

## File Structure

```
civ_llm/
├── CivAI_Bridge/
│   ├── CivAI_Bridge.modinfo    # Mod manifest for Civ VI
│   └── GameStateDump.lua       # Game state logging script
├── civ_advisor/
│   ├── __init__.py
│   ├── main.py                 # Entry point
│   ├── constants.py            # Static data
│   ├── config.py               # Configuration management
│   ├── log_watcher.py          # Log file monitoring
│   ├── game_state.py           # Data enrichment & mini-map
│   ├── llm_client.py           # AI provider integrations
│   └── gui.py                  # Tkinter interface
├── requirements.txt            # Python dependencies
├── config.json                 # User settings (auto-created, git-ignored)
└── README.md                   # This file
```

---

## Troubleshooting

### "Waiting for game data..."
- Ensure the mod is enabled in Civ VI's Additional Content
- Start a new turn to trigger data logging
- Verify the Logs folder path in Settings matches your installation
- Check that `Lua.log` exists and contains `>>>GAMESTATE>>>` entries

### API Errors
- Verify your API key is correct
- Check your account has available credits/quota
- For Ollama: ensure the server is running (`ollama serve`)
- For rate limit errors: wait or enable rate limiting in settings

### Mod Not Appearing
- Verify folder structure: `.../Mods/CivAI_Bridge/CivAI_Bridge.modinfo`
- Ensure both `.modinfo` and `.lua` files are present
- Restart Civilization VI completely

### Tkinter Not Found (Linux)
```bash
# Ubuntu/Debian
sudo apt-get install python3-tk

# Fedora
sudo dnf install python3-tkinter

# Arch
sudo pacman -S tk
```

---

## Available Models

### Google (Gemini)
- Gemini 2.5 Flash Lite (Primary - fastest)
- Gemini 2.0 Flash (Secondary)
- Gemma 2 9B (Failover - free, no system prompt support)

### Anthropic (Claude)
- Claude 3.5 Sonnet
- Claude Sonnet 4

### OpenAI (GPT)
- GPT-4o (Recommended)
- GPT-4o Mini
- GPT-4 Turbo
- GPT-3.5 Turbo

### Ollama (Local)
- Llama 3 (Default)
- Llama 3.1 8B
- Mistral
- Gemma 2
- Phi-3

---

## Notes

- API keys are stored locally in `config.json` (git-ignored)
- Google models have automatic fallback if quota is exceeded
- Gemma models don't support system prompts - they're merged into user content
- The overlay trims Lua.log when it exceeds 5MB
- Advice is limited to ~5 sentences for quick, actionable recommendations

## License

MIT License - See LICENSE file for details.
