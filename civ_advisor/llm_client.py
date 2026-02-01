"""
LLM client for the Civ VI AI Advisor.
Handles API calls to multiple providers with fallback logic.
Pure logic - no UI dependencies.
"""

import time
import threading
from typing import Optional, Callable, Any

from .config import Config
from .game_state import GameStateEnricher
from .constants import (
    GOOGLE_FALLBACK_CHAIN,
    NO_SYSTEM_PROMPT_MODELS,
    DEFAULT_RATE_LIMIT_SECONDS,
)


class DebugRequest:
    """Container for debug mode request info."""

    def __init__(self, provider: str, model: str, prompt: str, system_prompt: str,
                 api_key: str, token_estimate: int):
        self.provider = provider
        self.model = model
        self.prompt = prompt
        self.system_prompt = system_prompt
        self.api_key = api_key
        self.token_estimate = token_estimate
        self.is_debug_request = True

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt": self.prompt,
            "system_prompt": self.system_prompt,
            "api_key": self.api_key,
            "token_estimate": self.token_estimate,
        }


class AIAdvisor:
    """Handles AI API calls for advice with model hierarchy and fallback."""

    def __init__(self, config: Config):
        self.config = config
        self.enricher = GameStateEnricher()
        self.last_request_time: float = 0
        self._extended_prompt_sent: bool = False
        self._last_used_model: str = ""

    def _build_system_prompt(self, is_first_turn: bool) -> str:
        """Build system prompt: core always sent, extended sent only on first turn."""
        prompt = self.config.system_prompt_core
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

    def get_advice(self, game_state: dict, user_question: str = "", victory_goal: str = "",
                   clipboard_copy_func: Callable[[str], bool] = None) -> Any:
        """
        Get AI advice for the current game state.

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

        # Clipboard mode doesn't need API key validation
        if provider != "clipboard" and not api_key and not self.config.debug_mode:
            return f"No API key configured for {provider}. Open Settings to add one."

        # Check minimum request interval (not for debug mode or clipboard)
        now = time.time()
        elapsed = now - self.last_request_time
        min_interval = self.config.min_request_interval
        if provider != "clipboard" and not self.config.debug_mode and elapsed < min_interval and self.last_request_time > 0:
            wait_time = int(min_interval - elapsed)
            return f"Please wait {wait_time}s before next request.\n\n(Min interval: {min_interval}s between requests)"

        # Enrich the game state
        enriched = self.enricher.enrich(game_state, victory_goal)
        prompt = self.enricher.build_prompt(enriched, user_question)

        # Build system prompt
        is_first_turn = enriched.get("is_first_turn", False)
        system_prompt = self._build_system_prompt(is_first_turn)

        # Apply rate limiting if enabled (not for clipboard)
        if provider != "clipboard" and self.config.rate_limit_enabled:
            if elapsed < DEFAULT_RATE_LIMIT_SECONDS and self.last_request_time > 0:
                wait_time = int(DEFAULT_RATE_LIMIT_SECONDS - elapsed)
                return f"Rate limited. Next request in {wait_time} seconds.\n\n(1 request per minute, {self.config.token_limit} token limit)"

            prompt = self._truncate_to_tokens(prompt, self.config.token_limit)

        # Get model for current provider
        model = self._get_model_for_provider(provider)

        # Clipboard mode - copy to clipboard and return message
        if provider == "clipboard":
            return self._handle_clipboard_mode(clipboard_copy_func, system_prompt, prompt)

        # Debug mode - return debug info instead of calling API
        if self.config.debug_mode:
            token_estimate = self._estimate_tokens(prompt) + self._estimate_tokens(system_prompt)
            return DebugRequest(
                provider=provider,
                model=model,
                prompt=prompt,
                system_prompt=system_prompt,
                api_key=api_key,
                token_estimate=token_estimate,
            )

        try:
            self.last_request_time = time.time()

            if provider == "anthropic":
                return self._call_anthropic_with_system(api_key, prompt, system_prompt)
            elif provider == "google":
                return self._call_google_with_fallback(api_key, prompt, system_prompt)
            elif provider == "openai":
                return self._call_openai(api_key, prompt, system_prompt)
            elif provider == "ollama":
                return self._call_ollama(prompt, system_prompt)
            else:
                return f"Unknown provider: {provider}"
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
                return self._call_anthropic_with_system(api_key, prompt, system_prompt)
            elif provider == "google":
                return self._call_google_with_fallback(api_key, prompt, system_prompt)
            elif provider == "openai":
                return self._call_openai(api_key, prompt, system_prompt)
            elif provider == "ollama":
                return self._call_ollama(prompt, system_prompt)
            else:
                return f"Unknown provider: {provider}"
        except Exception as e:
            return f"API Error: {str(e)}"

    def send_question_only(self, question: str,
                           clipboard_copy_func: Callable[[str], bool] = None) -> Any:
        """
        Send a question to the AI without game state context.
        Used when include_context_with_questions is disabled.

        Args:
            question: The user's question text
            clipboard_copy_func: Function to copy text to clipboard (for clipboard mode)

        Returns:
            str: AI response or error message
            DebugRequest: In debug mode, returns debug info instead of calling API
        """
        provider = self.config.selected_provider
        api_key = self.config.get_active_key()

        if not question.strip():
            return "Please enter a question."

        # Clipboard mode doesn't need API key validation
        if provider != "clipboard" and not api_key and not self.config.debug_mode:
            return f"No API key configured for {provider}. Open Settings to add one."

        # Check minimum request interval (not for debug mode or clipboard)
        now = time.time()
        elapsed = now - self.last_request_time
        min_interval = self.config.min_request_interval
        if provider != "clipboard" and not self.config.debug_mode and elapsed < min_interval and self.last_request_time > 0:
            wait_time = int(min_interval - elapsed)
            return f"Please wait {wait_time}s before next request.\n\n(Min interval: {min_interval}s between requests)"

        # Get model for current provider
        model = self._get_model_for_provider(provider)

        # Clipboard mode - copy question to clipboard
        if provider == "clipboard":
            if clipboard_copy_func:
                success = clipboard_copy_func(question)
                if not success:
                    return "Failed to copy to clipboard."
            token_est = self._estimate_tokens(question)
            return f"Question copied to clipboard!\n\nPaste into your browser to get advice.\n\n~{token_est} tokens"

        # Debug mode - return debug info instead of calling API
        if self.config.debug_mode:
            token_estimate = self._estimate_tokens(question)
            return DebugRequest(
                provider=provider,
                model=model,
                prompt=question,
                system_prompt="(none - question only mode)",
                api_key=api_key,
                token_estimate=token_estimate,
            )

        try:
            self.last_request_time = time.time()

            if provider == "anthropic":
                return self._call_anthropic_question_only(api_key, question)
            elif provider == "google":
                return self._call_google_question_only(api_key, question)
            elif provider == "openai":
                return self._call_openai_question_only(api_key, question)
            elif provider == "ollama":
                return self._call_ollama_question_only(question)
            else:
                return f"Unknown provider: {provider}"
        except Exception as e:
            return f"API Error: {str(e)}"

    def _call_anthropic_question_only(self, api_key: str, question: str) -> str:
        """Call Claude API with just the question (no system prompt)."""
        try:
            import anthropic
        except ImportError:
            return "Error: 'anthropic' package not installed. Run: pip install anthropic"

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=self.config.anthropic_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": question}],
        )
        self._last_used_model = self.config.anthropic_model
        return response.content[0].text

    def _call_google_question_only(self, api_key: str, question: str) -> str:
        """Call Google API with just the question."""
        try:
            import google.generativeai as genai
        except ImportError:
            return "Error: 'google-generativeai' package not installed. Run: pip install google-generativeai"

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(self.config.google_model)
        response = model.generate_content(question)
        self._last_used_model = self.config.google_model
        return response.text

    def _call_openai_question_only(self, api_key: str, question: str) -> str:
        """Call OpenAI API with just the question."""
        try:
            from openai import OpenAI
        except ImportError:
            return "Error: 'openai' package not installed. Run: pip install openai"

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=self.config.openai_model,
            messages=[{"role": "user", "content": question}],
            max_tokens=2048,
        )
        self._last_used_model = self.config.openai_model
        return response.choices[0].message.content

    def _call_ollama_question_only(self, question: str) -> str:
        """Call Ollama API with just the question."""
        import urllib.request
        import json

        data = {
            "model": self.config.ollama_model,
            "prompt": question,
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
                               system_prompt: str, user_prompt: str) -> str:
        """Handle clipboard mode - copy prompt to clipboard."""
        full_prompt = f"""=== SYSTEM INSTRUCTIONS ===
{system_prompt}

=== GAME STATE & QUESTION ===
{user_prompt}"""

        if clipboard_copy_func:
            success = clipboard_copy_func(full_prompt)
            if not success:
                return "Failed to copy to clipboard."

        token_est = self._estimate_tokens(full_prompt)
        return f"Prompt copied to clipboard!\n\nPaste into your browser (ChatGPT/Claude/Gemini) to get advice.\n\n~{token_est} tokens"

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
        """Call Google API with automatic model fallback."""
        try:
            import google.generativeai as genai
            from google.api_core import exceptions as google_exceptions
        except ImportError:
            return "Error: 'google-generativeai' package not installed. Run: pip install google-generativeai"

        genai.configure(api_key=api_key)

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
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(merged_prompt)
                else:
                    model = genai.GenerativeModel(
                        model_name,
                        system_instruction=system_prompt
                    )
                    response = model.generate_content(context)

                self._last_used_model = model_name
                return response.text

            except google_exceptions.ResourceExhausted as e:
                last_error = e
                continue
            except google_exceptions.InvalidArgument as e:
                if "system_instruction is not supported" in str(e):
                    # Retry with merged prompt
                    try:
                        merged_prompt = f"{system_prompt}\n\n---\n\n{context}"
                        model = genai.GenerativeModel(model_name)
                        response = model.generate_content(merged_prompt)
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

