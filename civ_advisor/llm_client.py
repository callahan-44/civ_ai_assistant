"""
LLM client for the Civ VI AI Advisor.
Handles API calls to multiple providers with fallback logic.
Pure logic - no UI dependencies.
"""

import time
import threading
from datetime import datetime
from typing import Optional, Callable, Any

from .config import Config
from .game_state import GameStateEnricher
from .constants import (
    GOOGLE_FALLBACK_CHAIN,
    NO_SYSTEM_PROMPT_MODELS,
    DEFAULT_RATE_LIMIT_SECONDS,
    DEBUG_LOG_FILE,
)


class DebugRequest:
    """Container for debug mode request info."""

    def __init__(self, provider: str, model: str, prompt: str, system_prompt: str,
                 api_key: str, token_estimate: int, tiles_trimmed: int = 0):
        self.provider = provider
        self.model = model
        self.prompt = prompt
        self.system_prompt = system_prompt
        self.api_key = api_key
        self.token_estimate = token_estimate
        self.tiles_trimmed = tiles_trimmed
        self.is_debug_request = True

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt": self.prompt,
            "system_prompt": self.system_prompt,
            "api_key": self.api_key,
            "token_estimate": self.token_estimate,
            "tiles_trimmed": self.tiles_trimmed,
        }


class AIAdvisor:
    """Handles AI API calls for advice with model hierarchy and fallback."""

    def __init__(self, config: Config):
        self.config = config
        self.enricher = GameStateEnricher()
        self.last_request_time: float = 0
        self._extended_prompt_sent: bool = False
        self._last_used_model: str = ""
        self._last_token_estimate: int = 0  # Track tokens for display
        self._last_tiles_trimmed: int = 0  # Track tiles trimmed for context management

    def _build_system_prompt(self, is_first_turn: bool, force_full: bool = False) -> str:
        """
        Build system prompt based on mode.

        Args:
            is_first_turn: Whether this is the first turn of the session
            force_full: If True (API mode), always send full prompt (Core + Extended).
                       If False (Clipboard mode), only send extended on first turn.

        Returns:
            str: The system prompt to use
        """
        prompt = self.config.system_prompt_core

        if force_full:
            # API Mode: Always send full system prompt (AI has no memory)
            prompt += "\n\n" + self.config.system_prompt_extended
        else:
            # Clipboard Mode: Only send extended on first turn (web UI maintains context)
            if is_first_turn and not self._extended_prompt_sent:
                prompt += "\n\n" + self.config.system_prompt_extended
                self._extended_prompt_sent = True

        return prompt

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation: ~4 chars per token for English."""
        return len(text) // 4

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to approximately max_tokens."""
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text

        truncated = text[:max_chars - 50]
        last_newline = truncated.rfind("\n")
        if last_newline > max_chars // 2:
            truncated = truncated[:last_newline]
        return truncated + "\n\n[... TRUNCATED for rate limiting ...]"

    def _log_debug(self, provider: str, model: str, system_prompt: str, user_prompt: str, response: str):
        """Log prompt and response to debug.log if debug logging is enabled."""
        if not self.config.debug_logging:
            return

        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            separator = "=" * 80

            log_entry = f"""
{separator}
[{timestamp}] Provider: {provider} | Model: {model}
{separator}

=== SYSTEM PROMPT ===
{system_prompt}

=== USER PROMPT ===
{user_prompt}

=== RESPONSE ===
{response}

"""
            with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Error writing to debug log: {e}")

    def get_advice(self, game_state: dict, user_question: str = "", victory_goal: str = "",
                   clipboard_copy_func: Callable[[str], bool] = None) -> Any:
        """
        Get AI advice for the current game state.

        Two modes:
        - API Mode (Google, OpenAI, Anthropic, Ollama): Stateless. Always sends full
          system prompt and full game state. AI has no memory between requests.
        - Clipboard Mode: Stateful. Web UI maintains context. Uses delta tracking
          and only sends system prompt on first turn to save tokens.

        Args:
            game_state: Raw game state from Lua
            user_question: Optional follow-up question
            victory_goal: Selected victory type
            clipboard_copy_func: Function to copy text to clipboard (for clipboard mode)

        Returns:
            str: AI response or error message
            DebugRequest: In debug mode, returns debug info instead of calling API
        """
        provider = self.config.selected_provider
        api_key = self.config.get_active_key()

        # Determine mode: clipboard is stateful, everything else is stateless
        is_clipboard_mode = (provider == "clipboard")
        force_full_state = not is_clipboard_mode  # API mode = full state every time

        # Clipboard mode doesn't need API key validation
        if not is_clipboard_mode and not api_key and not self.config.debug_mode:
            return f"No API key configured for {provider}. Open Settings to add one."

        # Check minimum request interval (not for debug mode or clipboard)
        now = time.time()
        elapsed = now - self.last_request_time
        min_interval = self.config.min_request_interval
        if not is_clipboard_mode and not self.config.debug_mode and elapsed < min_interval and self.last_request_time > 0:
            wait_time = int(min_interval - elapsed)
            return f"Please wait {wait_time}s before next request.\n\n(Min interval: {min_interval}s between requests)"

        # Enrich the game state
        enriched = self.enricher.enrich(game_state, victory_goal)
        is_first_turn = enriched.get("is_first_turn", False)

        # Build system prompt with appropriate mode
        # API Mode: Always send full system prompt (Core + Extended)
        # Clipboard Mode: Only send extended on first turn
        system_prompt = self._build_system_prompt(is_first_turn, force_full=force_full_state)

        # Build prompt with appropriate mode and intelligent context trimming
        # API Mode: force_full_state=True (send everything, AI has no memory)
        # Clipboard Mode: force_full_state=False (use deltas, web UI maintains context)
        self._last_tiles_trimmed = 0
        if is_clipboard_mode:
            # Clipboard mode: no token limit enforcement
            prompt = self.enricher.build_prompt(enriched, user_question, force_full_state=force_full_state)
        else:
            # API mode: use intelligent context trimming to fit token limit
            prompt, self._last_tiles_trimmed = self.enricher.build_prompt_with_limit(
                enriched, user_question, force_full_state,
                system_prompt, self.config.token_limit
            )

        # Apply rate limiting if enabled (not for clipboard)
        if not is_clipboard_mode and self.config.rate_limit_enabled:
            if elapsed < DEFAULT_RATE_LIMIT_SECONDS and self.last_request_time > 0:
                wait_time = int(DEFAULT_RATE_LIMIT_SECONDS - elapsed)
                return f"Rate limited. Next request in {wait_time} seconds.\n\n(1 request per minute, {self.config.token_limit} token limit)"

        # Get model for current provider
        model = self._get_model_for_provider(provider)

        # Calculate and store token estimate (system prompt + user prompt)
        self._last_token_estimate = self._estimate_tokens(prompt) + self._estimate_tokens(system_prompt)

        # Clipboard mode - copy to clipboard and return message
        if is_clipboard_mode:
            return self._handle_clipboard_mode(clipboard_copy_func, system_prompt, prompt, is_first_turn)

        # Debug mode - return debug info instead of calling API
        if self.config.debug_mode:
            return DebugRequest(
                provider=provider,
                model=model,
                prompt=prompt,
                system_prompt=system_prompt,
                api_key=api_key,
                token_estimate=self._last_token_estimate,
                tiles_trimmed=self._last_tiles_trimmed,
            )

        try:
            self.last_request_time = time.time()

            if provider == "anthropic":
                response = self._call_anthropic_with_system(api_key, prompt, system_prompt)
            elif provider == "google":
                response = self._call_google_with_fallback(api_key, prompt, system_prompt)
            elif provider == "openai":
                response = self._call_openai(api_key, prompt, system_prompt)
            elif provider == "ollama":
                response = self._call_ollama(prompt, system_prompt)
            else:
                return f"Unknown provider: {provider}"

            # Log to debug.log if enabled
            self._log_debug(provider, self._last_used_model, system_prompt, prompt, response)

            # Append token info to response
            info_parts = [f"Request: ~{self._last_token_estimate} tokens", f"Model: {self._last_used_model}"]
            if self._last_tiles_trimmed > 0:
                info_parts.append(f"Tiles trimmed: {self._last_tiles_trimmed}")
            return f"{response}\n\n---\n[{' | '.join(info_parts)}]"
        except Exception as e:
            return f"API Error: {str(e)}"

    def execute_debug_request(self, debug_info: dict) -> str:
        """
        Execute a debug request that was previously prepared.

        Args:
            debug_info: Dict with provider, api_key, prompt, system_prompt

        Returns:
            str: API response or error message
        """
        provider = debug_info.get("provider")
        api_key = debug_info.get("api_key")
        prompt = debug_info.get("prompt")
        system_prompt = debug_info.get("system_prompt")

        try:
            self.last_request_time = time.time()

            if provider == "anthropic":
                response = self._call_anthropic_with_system(api_key, prompt, system_prompt)
            elif provider == "google":
                response = self._call_google_with_fallback(api_key, prompt, system_prompt)
            elif provider == "openai":
                response = self._call_openai(api_key, prompt, system_prompt)
            elif provider == "ollama":
                response = self._call_ollama(prompt, system_prompt)
            else:
                return f"Unknown provider: {provider}"

            # Log to debug.log if enabled
            self._log_debug(provider, self._last_used_model, system_prompt, prompt, response)
            return response
        except Exception as e:
            return f"API Error: {str(e)}"

    def _get_model_for_provider(self, provider: str) -> str:
        """Get the configured model for a provider."""
        if provider == "google":
            return self.config.google_model
        elif provider == "anthropic":
            return self.config.anthropic_model
        elif provider == "openai":
            return self.config.openai_model
        elif provider == "ollama":
            return self.config.ollama_model
        else:
            return ""

    def _handle_clipboard_mode(self, clipboard_copy_func: Callable[[str], bool],
                               system_prompt: str, user_prompt: str,
                               is_first_turn: bool = True) -> str:
        """
        Handle clipboard mode - copy prompt to clipboard.

        In clipboard/stateful mode:
        - First turn: Include system prompt (web UI will remember it)
        - Subsequent turns: Only include game state delta (saves tokens)
        """
        system_tokens = self._estimate_tokens(system_prompt)
        prompt_tokens = self._estimate_tokens(user_prompt)

        if is_first_turn:
            # First turn: Include full system instructions
            full_prompt = f"""=== SYSTEM INSTRUCTIONS ===
{system_prompt}

=== GAME STATE & QUESTION ===
{user_prompt}"""
            total_tokens = system_tokens + prompt_tokens
        else:
            # Subsequent turns: Just the game state delta (web UI maintains context)
            full_prompt = f"""=== GAME STATE UPDATE ===
{user_prompt}"""
            total_tokens = prompt_tokens

        if clipboard_copy_func:
            success = clipboard_copy_func(full_prompt)
            if not success:
                return "Failed to copy to clipboard."

        if is_first_turn:
            return (f"Prompt copied to clipboard!\n\n"
                    f"Paste into your browser (ChatGPT/Claude/Gemini) to get advice.\n\n"
                    f"~{total_tokens} tokens (System: {system_tokens} + Game State: {prompt_tokens})")
        else:
            return (f"Game state update copied to clipboard!\n\n"
                    f"Paste into your existing chat to continue.\n\n"
                    f"~{total_tokens} tokens (delta only, system prompt already in chat)")

    def _call_anthropic_with_system(self, api_key: str, context: str, system_prompt: str) -> str:
        """Call Claude API with explicit system prompt."""
        try:
            import anthropic
        except ImportError:
            return "Error: 'anthropic' package not installed. Run: pip install anthropic"

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=self.config.anthropic_model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": context}],
        )
        self._last_used_model = self.config.anthropic_model
        return response.content[0].text

    def _call_google_with_fallback(self, api_key: str, context: str, system_prompt: str) -> str:
        """Call Google API with automatic model fallback using google-genai SDK."""
        try:
            from google import genai
            from google.genai import types, errors
        except ImportError:
            return "Error: 'google-genai' package not installed. Run: pip install google-genai"

        # Create client with API key
        client = genai.Client(api_key=api_key)

        # Build fallback chain starting with configured model
        models_to_try = [self.config.google_model]
        for fallback_model in GOOGLE_FALLBACK_CHAIN:
            if fallback_model not in models_to_try:
                models_to_try.append(fallback_model)

        last_error = None
        for model_name in models_to_try:
            try:
                # Check if model supports system prompts
                if model_name in NO_SYSTEM_PROMPT_MODELS:
                    # Merge system prompt into user content
                    merged_prompt = f"{system_prompt}\n\n---\n\n{context}"
                    response = client.models.generate_content(
                        model=model_name,
                        contents=merged_prompt,
                    )
                else:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=context,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                        ),
                    )

                self._last_used_model = model_name
                return response.text

            except errors.APIError as e:
                # Handle rate limiting (429) and other API errors
                if e.code == 429:  # Resource exhausted / rate limited
                    last_error = e
                    continue
                elif e.code == 400 and "system_instruction is not supported" in str(e.message):
                    # Retry with merged prompt for models that don't support system instructions
                    try:
                        merged_prompt = f"{system_prompt}\n\n---\n\n{context}"
                        response = client.models.generate_content(
                            model=model_name,
                            contents=merged_prompt,
                        )
                        self._last_used_model = model_name
                        return response.text
                    except Exception:
                        pass
                last_error = e
                continue
            except Exception as e:
                last_error = e
                continue

        return f"All models failed. Last error: {str(last_error)}"

    def _call_openai(self, api_key: str, context: str, system_prompt: str) -> str:
        """Call OpenAI API with system prompt."""
        try:
            from openai import OpenAI
        except ImportError:
            return "Error: 'openai' package not installed. Run: pip install openai"

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=self.config.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context},
            ],
            max_tokens=2048,
        )
        self._last_used_model = self.config.openai_model
        return response.choices[0].message.content

    def _call_ollama(self, context: str, system_prompt: str) -> str:
        """Call local Ollama API."""
        import urllib.request
        import json

        data = {
            "model": self.config.ollama_model,
            "prompt": context,
            "system": system_prompt,
            "stream": False,
        }

        req = urllib.request.Request(
            self.config.ollama_url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
            self._last_used_model = self.config.ollama_model
            return result.get("response", "No response")

