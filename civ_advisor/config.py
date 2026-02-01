"""
Configuration management for the Civ VI AI Advisor.
"""

import json
from pathlib import Path
from typing import Optional

from .constants import (
    CONFIG_FILE,
    DEFAULT_LOG_FOLDER,
    LOG_FILENAME,
    DEFAULT_TOKEN_LIMIT,
    DEFAULT_MIN_REQUEST_INTERVAL,
    DEFAULT_SYSTEM_PROMPT_CORE,
    DEFAULT_SYSTEM_PROMPT_EXTENDED,
    DEFAULT_OLLAMA_URL,
)


class Config:
    """Manages API keys and settings securely."""

    def __init__(self):
        self.anthropic_key: str = ""
        self.google_key: str = ""
        self.openai_key: str = ""
        self.selected_provider: str = "google"  # Default to google (cheaper)
        self.anthropic_model: str = "claude-3-5-sonnet-20241022"
        self.google_model: str = "gemini-2.5-flash-lite"  # Primary model in hierarchy
        self.openai_model: str = "gpt-4o"
        self.ollama_model: str = "llama3"
        self.ollama_url: str = DEFAULT_OLLAMA_URL
        self.log_folder: str = str(DEFAULT_LOG_FOLDER)
        # Request throttling
        self.min_request_interval: int = DEFAULT_MIN_REQUEST_INTERVAL
        # Rate limiting options (stricter, optional)
        self.rate_limit_enabled: bool = False
        self.token_limit: int = DEFAULT_TOKEN_LIMIT
        # Debug mode
        self.debug_mode: bool = False
        # System prompts (customizable)
        self.system_prompt_core: str = DEFAULT_SYSTEM_PROMPT_CORE
        self.system_prompt_extended: str = DEFAULT_SYSTEM_PROMPT_EXTENDED
        # Victory goal (persisted)
        self.victory_goal: str = "Domination"
        # UI settings
        self.always_on_top: bool = True
        self.load()

    def load(self):
        """Load configuration from file."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    self.anthropic_key = data.get("anthropic_key", "")
                    self.google_key = data.get("google_key", "")
                    self.openai_key = data.get("openai_key", "")
                    self.selected_provider = data.get("selected_provider", "google")
                    self.anthropic_model = data.get("anthropic_model", "claude-3-5-sonnet-20241022")
                    self.google_model = data.get("google_model", "gemini-2.5-flash-lite")
                    self.openai_model = data.get("openai_model", "gpt-4o")
                    self.ollama_model = data.get("ollama_model", "llama3")
                    self.ollama_url = data.get("ollama_url", DEFAULT_OLLAMA_URL)
                    # Support both old "log_path" and new "log_folder" keys
                    log_val = data.get("log_folder", data.get("log_path", str(DEFAULT_LOG_FOLDER)))
                    # If old config had full path with Lua.log, strip it
                    if log_val.lower().endswith("lua.log"):
                        log_val = str(Path(log_val).parent)
                    self.log_folder = log_val
                    self.min_request_interval = data.get("min_request_interval", DEFAULT_MIN_REQUEST_INTERVAL)
                    self.rate_limit_enabled = data.get("rate_limit_enabled", False)
                    self.token_limit = data.get("token_limit", DEFAULT_TOKEN_LIMIT)
                    self.debug_mode = data.get("debug_mode", False)
                    self.system_prompt_core = data.get("system_prompt_core", DEFAULT_SYSTEM_PROMPT_CORE)
                    self.system_prompt_extended = data.get("system_prompt_extended", DEFAULT_SYSTEM_PROMPT_EXTENDED)
                    self.victory_goal = data.get("victory_goal", "Domination")
                    self.always_on_top = data.get("always_on_top", True)
            except Exception as e:
                print(f"Error loading config: {e}")

    def save(self):
        """Save configuration to file."""
        try:
            data = {
                "anthropic_key": self.anthropic_key,
                "google_key": self.google_key,
                "openai_key": self.openai_key,
                "selected_provider": self.selected_provider,
                "anthropic_model": self.anthropic_model,
                "google_model": self.google_model,
                "openai_model": self.openai_model,
                "ollama_model": self.ollama_model,
                "ollama_url": self.ollama_url,
                "log_folder": self.log_folder,
                "min_request_interval": self.min_request_interval,
                "rate_limit_enabled": self.rate_limit_enabled,
                "token_limit": self.token_limit,
                "debug_mode": self.debug_mode,
                "system_prompt_core": self.system_prompt_core,
                "system_prompt_extended": self.system_prompt_extended,
                "victory_goal": self.victory_goal,
                "always_on_top": self.always_on_top,
            }
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get_active_key(self) -> Optional[str]:
        """Get the currently selected API key."""
        if self.selected_provider == "anthropic":
            return self.anthropic_key if self.anthropic_key else None
        elif self.selected_provider == "google":
            return self.google_key if self.google_key else None
        elif self.selected_provider == "openai":
            return self.openai_key if self.openai_key else None
        elif self.selected_provider == "ollama":
            return "local"  # Ollama doesn't need an API key
        elif self.selected_provider == "clipboard":
            return "clipboard"  # Clipboard mode doesn't need an API key
        else:
            return None

    def get_log_path(self) -> Path:
        """Get the full path to Lua.log file."""
        return Path(self.log_folder) / LOG_FILENAME
