"""
Dialog windows for the Civ VI AI Advisor.
Includes VictoryGoalDialog, SettingsDialog, and DebugWindow.
"""

import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable

from .config import Config
from .constants import (
    COLORS,
    ANTHROPIC_MODELS,
    GOOGLE_MODELS,
    OPENAI_MODELS,
    OLLAMA_MODELS,
    PROVIDERS,
    VICTORY_GOALS,
    DEFAULT_TOKEN_LIMIT,
    DEFAULT_MIN_REQUEST_INTERVAL,
    DEFAULT_SYSTEM_PROMPT_CORE,
    DEFAULT_SYSTEM_PROMPT_EXTENDED,
    NO_SYSTEM_PROMPT_MODELS,
)


class VictoryGoalDialog:
    """Dialog to select victory goal on startup."""

    def __init__(self, parent: tk.Tk, config: Config):
        self.config = config
        self.result: Optional[str] = None

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Select Victory Goal")
        self.dialog.configure(bg=COLORS["bg"])
        self.dialog.geometry("400x380")
        self.dialog.resizable(False, False)
        self.dialog.grab_set()
        self.dialog.attributes("-topmost", True)

        self._create_widgets()
        self._center_window(parent)

        parent.wait_window(self.dialog)

    def _center_window(self, parent):
        """Center dialog on screen."""
        self.dialog.update_idletasks()
        screen_width = self.dialog.winfo_screenwidth()
        screen_height = self.dialog.winfo_screenheight()
        x = (screen_width // 2) - (self.dialog.winfo_width() // 2)
        y = (screen_height // 2) - (self.dialog.winfo_height() // 2)
        self.dialog.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        """Create dialog widgets."""
        main_frame = tk.Frame(self.dialog, bg=COLORS["bg"], padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            main_frame,
            text="Choose Your Victory Goal",
            fg=COLORS["accent"],
            bg=COLORS["bg"],
            font=("Segoe UI", 14, "bold"),
        ).pack(pady=(0, 15))

        tk.Label(
            main_frame,
            text="The AI Advisor will tailor recommendations\nto help you achieve this victory type.",
            fg=COLORS["text_secondary"],
            bg=COLORS["bg"],
            font=("Segoe UI", 9),
            justify=tk.CENTER,
        ).pack(pady=(0, 15))

        self.goal_var = tk.StringVar(value=self.config.victory_goal)

        for goal_name, description in VICTORY_GOALS:
            frame = tk.Frame(main_frame, bg=COLORS["bg"])
            frame.pack(fill=tk.X, pady=2)

            rb = tk.Radiobutton(
                frame,
                text=goal_name,
                variable=self.goal_var,
                value=goal_name,
                fg=COLORS["text"],
                bg=COLORS["bg"],
                selectcolor=COLORS["bg_secondary"],
                activebackground=COLORS["bg"],
                activeforeground=COLORS["accent"],
                font=("Segoe UI", 10, "bold"),
                anchor="w",
            )
            rb.pack(side=tk.LEFT)

            desc_text = f"- {description[:45]}..." if len(description) > 45 else f"- {description}"
            tk.Label(
                frame,
                text=desc_text,
                fg=COLORS["text_secondary"],
                bg=COLORS["bg"],
                font=("Segoe UI", 8),
                anchor="w",
            ).pack(side=tk.LEFT, padx=(5, 0))

        start_btn = tk.Button(
            main_frame,
            text="Start Advisor",
            command=self._on_start,
            bg=COLORS["accent"],
            fg=COLORS["bg"],
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT,
            padx=30,
            pady=8,
            cursor="hand2",
        )
        start_btn.pack(pady=(20, 0))

    def _on_start(self):
        """Handle start button click."""
        self.result = self.goal_var.get()
        self.config.victory_goal = self.result
        self.config.save()
        self.dialog.destroy()


class SettingsDialog:
    """Settings dialog for API keys and configuration with 3-tab structure."""

    def __init__(self, parent: tk.Tk, config: Config, on_save: Callable, main_window=None):
        self.config = config
        self.on_save = on_save
        self.main_window = main_window

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Settings")
        self.dialog.configure(bg=COLORS["bg"])
        self.dialog.geometry("650x750")
        self.dialog.resizable(True, True)
        self.dialog.minsize(550, 650)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self._setup_styles()
        self._create_widgets()
        self._center_window(parent)

    def _setup_styles(self):
        """Configure ttk styles for readable comboboxes."""
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "TCombobox",
            fieldbackground="white",
            background=COLORS["button"],
            foreground="black",
            arrowcolor=COLORS["text"],
            selectbackground=COLORS["accent"],
            selectforeground="black",
        )
        style.map("TCombobox",
            fieldbackground=[("readonly", "white")],
            foreground=[("readonly", "black")],
        )

    def _center_window(self, parent):
        """Center dialog over parent window."""
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.dialog.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.dialog.winfo_height() // 2)
        self.dialog.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        """Create settings dialog with 3 tabs: Model Selection, API Behavior, Interface."""
        notebook = ttk.Notebook(self.dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ===== TAB 1: Model Selection =====
        model_frame = tk.Frame(notebook, bg=COLORS["bg"], padx=20, pady=15)
        notebook.add(model_frame, text="Model Selection")

        # Provider selection
        tk.Label(
            model_frame,
            text="AI Provider:",
            fg=COLORS["accent"],
            bg=COLORS["bg"],
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        self.provider_var = tk.StringVar(value=self.config.selected_provider)
        provider_combo_frame = tk.Frame(model_frame, bg=COLORS["bg"])
        provider_combo_frame.grid(row=0, column=1, sticky="w", pady=(0, 10))

        provider_display_names = [display for _, display in PROVIDERS]
        current_provider_display = self.config.selected_provider
        for key, display in PROVIDERS:
            if key == self.config.selected_provider:
                current_provider_display = display
                break

        self.provider_combo = ttk.Combobox(
            provider_combo_frame,
            values=provider_display_names,
            state="readonly",
            width=25,
        )
        self.provider_combo.set(current_provider_display)
        self.provider_combo.pack(side=tk.LEFT)
        self.provider_combo.bind("<<ComboboxSelected>>", self._on_provider_changed)

        # Container for API key sections
        self.api_sections_frame = tk.Frame(model_frame, bg=COLORS["bg"])
        self.api_sections_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 0))

        # --- Google Section ---
        self.google_section = tk.LabelFrame(
            self.api_sections_frame,
            text="Google (Gemini)",
            fg=COLORS["text"],
            bg=COLORS["bg"],
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=10,
        )
        self.google_section.pack(fill=tk.X, pady=(0, 10))

        tk.Label(self.google_section, text="API Key:", fg=COLORS["text"], bg=COLORS["bg"]).grid(row=0, column=0, sticky="w")
        self.google_entry = tk.Entry(self.google_section, width=40, show="*", bg=COLORS["bg_secondary"], fg=COLORS["text"], insertbackground=COLORS["text"], relief=tk.FLAT)
        self.google_entry.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.google_entry.insert(0, self.config.google_key)

        tk.Label(self.google_section, text="Model:", fg=COLORS["text"], bg=COLORS["bg"]).grid(row=1, column=0, sticky="w", pady=(5, 0))
        google_model_names = [name for name, _ in GOOGLE_MODELS]
        current_google_display = self.config.google_model
        for name, mid in GOOGLE_MODELS:
            if mid == self.config.google_model:
                current_google_display = name
                break
        self.google_model_combo = ttk.Combobox(self.google_section, values=google_model_names, state="readonly", width=37)
        self.google_model_combo.set(current_google_display)
        self.google_model_combo.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(5, 0))

        # --- Anthropic Section ---
        self.anthropic_section = tk.LabelFrame(
            self.api_sections_frame,
            text="Anthropic (Claude)",
            fg=COLORS["text"],
            bg=COLORS["bg"],
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=10,
        )
        self.anthropic_section.pack(fill=tk.X, pady=(0, 10))

        tk.Label(self.anthropic_section, text="API Key:", fg=COLORS["text"], bg=COLORS["bg"]).grid(row=0, column=0, sticky="w")
        self.anthropic_entry = tk.Entry(self.anthropic_section, width=40, show="*", bg=COLORS["bg_secondary"], fg=COLORS["text"], insertbackground=COLORS["text"], relief=tk.FLAT)
        self.anthropic_entry.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.anthropic_entry.insert(0, self.config.anthropic_key)

        tk.Label(self.anthropic_section, text="Model:", fg=COLORS["text"], bg=COLORS["bg"]).grid(row=1, column=0, sticky="w", pady=(5, 0))
        anthropic_model_names = [name for name, _ in ANTHROPIC_MODELS]
        current_anthropic_display = self.config.anthropic_model
        for name, mid in ANTHROPIC_MODELS:
            if mid == self.config.anthropic_model:
                current_anthropic_display = name
                break
        self.anthropic_model_combo = ttk.Combobox(self.anthropic_section, values=anthropic_model_names, state="readonly", width=37)
        self.anthropic_model_combo.set(current_anthropic_display)
        self.anthropic_model_combo.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(5, 0))

        # --- OpenAI Section ---
        self.openai_section = tk.LabelFrame(
            self.api_sections_frame,
            text="OpenAI (GPT)",
            fg=COLORS["text"],
            bg=COLORS["bg"],
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=10,
        )
        self.openai_section.pack(fill=tk.X, pady=(0, 10))

        tk.Label(self.openai_section, text="API Key:", fg=COLORS["text"], bg=COLORS["bg"]).grid(row=0, column=0, sticky="w")
        self.openai_entry = tk.Entry(self.openai_section, width=40, show="*", bg=COLORS["bg_secondary"], fg=COLORS["text"], insertbackground=COLORS["text"], relief=tk.FLAT)
        self.openai_entry.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.openai_entry.insert(0, self.config.openai_key)

        tk.Label(self.openai_section, text="Model:", fg=COLORS["text"], bg=COLORS["bg"]).grid(row=1, column=0, sticky="w", pady=(5, 0))
        openai_model_names = [name for name, _ in OPENAI_MODELS]
        current_openai_display = self.config.openai_model
        for name, mid in OPENAI_MODELS:
            if mid == self.config.openai_model:
                current_openai_display = name
                break
        self.openai_model_combo = ttk.Combobox(self.openai_section, values=openai_model_names, state="readonly", width=37)
        self.openai_model_combo.set(current_openai_display)
        self.openai_model_combo.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(5, 0))

        # --- Ollama Section ---
        self.ollama_section = tk.LabelFrame(
            self.api_sections_frame,
            text="Ollama (Local)",
            fg=COLORS["text"],
            bg=COLORS["bg"],
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=10,
        )
        self.ollama_section.pack(fill=tk.X, pady=(0, 10))

        tk.Label(self.ollama_section, text="URL:", fg=COLORS["text"], bg=COLORS["bg"]).grid(row=0, column=0, sticky="w")
        self.ollama_url_entry = tk.Entry(self.ollama_section, width=40, bg=COLORS["bg_secondary"], fg=COLORS["text"], insertbackground=COLORS["text"], relief=tk.FLAT)
        self.ollama_url_entry.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.ollama_url_entry.insert(0, self.config.ollama_url)

        tk.Label(self.ollama_section, text="Model:", fg=COLORS["text"], bg=COLORS["bg"]).grid(row=1, column=0, sticky="w", pady=(5, 0))
        ollama_model_names = [name for name, _ in OLLAMA_MODELS]
        current_ollama_display = self.config.ollama_model
        for name, mid in OLLAMA_MODELS:
            if mid == self.config.ollama_model:
                current_ollama_display = name
                break
        self.ollama_model_combo = ttk.Combobox(self.ollama_section, values=ollama_model_names, state="readonly", width=37)
        self.ollama_model_combo.set(current_ollama_display)
        self.ollama_model_combo.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(5, 0))

        # Clipboard mode notice
        self.clipboard_notice = tk.Label(
            self.api_sections_frame,
            text="Clipboard mode: Prompts are copied to your clipboard.\nPaste into ChatGPT, Claude.ai, or Gemini in your browser.",
            fg=COLORS["text_secondary"],
            bg=COLORS["bg"],
            font=("Segoe UI", 10),
            justify=tk.LEFT,
        )

        self._update_provider_visibility()

        # ===== TAB 2: API Behavior =====
        behavior_frame = tk.Frame(notebook, bg=COLORS["bg"], padx=20, pady=15)
        notebook.add(behavior_frame, text="API Behavior")

        # Rate Limiting
        tk.Label(
            behavior_frame,
            text="Rate Limiting",
            fg=COLORS["accent"],
            bg=COLORS["bg"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        self.rate_limit_var = tk.BooleanVar(value=self.config.rate_limit_enabled)
        rate_cb = tk.Checkbutton(
            behavior_frame,
            text="Enable rate limiting (1 request per minute)",
            variable=self.rate_limit_var,
            fg=COLORS["text"],
            bg=COLORS["bg"],
            selectcolor=COLORS["bg_secondary"],
            activebackground=COLORS["bg"],
            font=("Segoe UI", 10),
        )
        rate_cb.pack(anchor="w")

        token_frame = tk.Frame(behavior_frame, bg=COLORS["bg"])
        token_frame.pack(fill=tk.X, pady=(5, 0))

        tk.Label(token_frame, text="Max tokens:", fg=COLORS["text"], bg=COLORS["bg"]).pack(side=tk.LEFT)
        self.token_entry = tk.Entry(token_frame, width=10, bg=COLORS["bg_secondary"], fg=COLORS["text"], insertbackground=COLORS["text"], relief=tk.FLAT)
        self.token_entry.pack(side=tk.LEFT, padx=(10, 0))
        self.token_entry.insert(0, str(self.config.token_limit))

        # Min request interval
        interval_frame = tk.Frame(behavior_frame, bg=COLORS["bg"])
        interval_frame.pack(fill=tk.X, pady=(10, 0))

        tk.Label(interval_frame, text="Min request interval (seconds):", fg=COLORS["text"], bg=COLORS["bg"]).pack(side=tk.LEFT)
        self.interval_entry = tk.Entry(interval_frame, width=10, bg=COLORS["bg_secondary"], fg=COLORS["text"], insertbackground=COLORS["text"], relief=tk.FLAT)
        self.interval_entry.pack(side=tk.LEFT, padx=(10, 0))
        self.interval_entry.insert(0, str(self.config.min_request_interval))

        # Debug mode
        tk.Label(
            behavior_frame,
            text="Debug Mode",
            fg=COLORS["accent"],
            bg=COLORS["bg"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(20, 10))

        self.debug_var = tk.BooleanVar(value=self.config.debug_mode)
        debug_cb = tk.Checkbutton(
            behavior_frame,
            text="Enable debug mode (preview requests before sending)",
            variable=self.debug_var,
            fg=COLORS["text"],
            bg=COLORS["bg"],
            selectcolor=COLORS["bg_secondary"],
            activebackground=COLORS["bg"],
            font=("Segoe UI", 10),
        )
        debug_cb.pack(anchor="w")

        self.debug_logging_var = tk.BooleanVar(value=self.config.debug_logging)
        debug_logging_cb = tk.Checkbutton(
            behavior_frame,
            text="Enable debug logging (save prompts/responses to debug.log)",
            variable=self.debug_logging_var,
            fg=COLORS["text"],
            bg=COLORS["bg"],
            selectcolor=COLORS["bg_secondary"],
            activebackground=COLORS["bg"],
            font=("Segoe UI", 10),
        )
        debug_logging_cb.pack(anchor="w")

        # Log folder
        tk.Label(
            behavior_frame,
            text="Log Folder",
            fg=COLORS["accent"],
            bg=COLORS["bg"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(20, 10))

        self.log_folder_entry = tk.Entry(
            behavior_frame,
            width=50,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief=tk.FLAT,
        )
        self.log_folder_entry.pack(fill=tk.X)
        self.log_folder_entry.insert(0, self.config.log_folder)

        # ===== TAB 3: Interface =====
        interface_frame = tk.Frame(notebook, bg=COLORS["bg"], padx=20, pady=15)
        notebook.add(interface_frame, text="Interface")

        # Always on top
        tk.Label(
            interface_frame,
            text="Window Behavior",
            fg=COLORS["accent"],
            bg=COLORS["bg"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        self.always_on_top_var = tk.BooleanVar(value=self.config.always_on_top)
        always_on_top_cb = tk.Checkbutton(
            interface_frame,
            text="Keep window always on top",
            variable=self.always_on_top_var,
            fg=COLORS["text"],
            bg=COLORS["bg"],
            selectcolor=COLORS["bg_secondary"],
            activebackground=COLORS["bg"],
            font=("Segoe UI", 10),
        )
        always_on_top_cb.pack(anchor="w")

        # System prompts
        tk.Label(
            interface_frame,
            text="System Prompts",
            fg=COLORS["accent"],
            bg=COLORS["bg"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(20, 10))

        tk.Label(
            interface_frame,
            text="Core (always sent):",
            fg=COLORS["text"],
            bg=COLORS["bg"],
        ).pack(anchor="w")

        self.core_prompt_text = tk.Text(
            interface_frame,
            height=6,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text"],
            font=("Consolas", 9),
            wrap=tk.WORD,
            relief=tk.FLAT,
        )
        self.core_prompt_text.pack(fill=tk.X, pady=(5, 10))
        self.core_prompt_text.insert("1.0", self.config.system_prompt_core)

        tk.Label(
            interface_frame,
            text="Extended (sent on first turn only):",
            fg=COLORS["text"],
            bg=COLORS["bg"],
        ).pack(anchor="w")

        self.extended_prompt_text = tk.Text(
            interface_frame,
            height=4,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text"],
            font=("Consolas", 9),
            wrap=tk.WORD,
            relief=tk.FLAT,
        )
        self.extended_prompt_text.pack(fill=tk.X, pady=(5, 10))
        self.extended_prompt_text.insert("1.0", self.config.system_prompt_extended)

        reset_btn = tk.Button(
            interface_frame,
            text="Reset to Defaults",
            command=self._reset_prompts,
            bg=COLORS["button"],
            fg=COLORS["text"],
            font=("Segoe UI", 9),
            relief=tk.FLAT,
        )
        reset_btn.pack(anchor="w")

        # ===== Save Button =====
        save_btn = tk.Button(
            self.dialog,
            text="Save Settings",
            command=self._save,
            bg=COLORS["accent"],
            fg=COLORS["bg"],
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT,
            padx=30,
            pady=10,
        )
        save_btn.pack(pady=10)

    def _on_provider_changed(self, event=None):
        """Handle provider selection change."""
        self._update_provider_visibility()

    def _update_provider_visibility(self):
        """Show/hide API sections based on selected provider."""
        selected_display = self.provider_combo.get()
        selected_key = None
        for key, display in PROVIDERS:
            if display == selected_display:
                selected_key = key
                break

        if selected_key == "clipboard":
            self.google_section.pack_forget()
            self.anthropic_section.pack_forget()
            self.openai_section.pack_forget()
            self.ollama_section.pack_forget()
            self.clipboard_notice.pack(fill=tk.X, pady=20)
        else:
            self.clipboard_notice.pack_forget()
            self.google_section.pack(fill=tk.X, pady=(0, 10))
            self.anthropic_section.pack(fill=tk.X, pady=(0, 10))
            self.openai_section.pack(fill=tk.X, pady=(0, 10))
            self.ollama_section.pack(fill=tk.X, pady=(0, 10))

    def _reset_prompts(self):
        """Reset system prompts to defaults."""
        self.core_prompt_text.delete("1.0", tk.END)
        self.core_prompt_text.insert("1.0", DEFAULT_SYSTEM_PROMPT_CORE)
        self.extended_prompt_text.delete("1.0", tk.END)
        self.extended_prompt_text.insert("1.0", DEFAULT_SYSTEM_PROMPT_EXTENDED)

    def _save(self):
        """Save settings and close dialog."""
        # Provider
        selected_display = self.provider_combo.get()
        for key, display in PROVIDERS:
            if display == selected_display:
                self.config.selected_provider = key
                break

        # API keys
        self.config.google_key = self.google_entry.get()
        self.config.anthropic_key = self.anthropic_entry.get()
        self.config.openai_key = self.openai_entry.get()
        self.config.ollama_url = self.ollama_url_entry.get()

        # Models
        for name, mid in GOOGLE_MODELS:
            if name == self.google_model_combo.get():
                self.config.google_model = mid
                break

        for name, mid in ANTHROPIC_MODELS:
            if name == self.anthropic_model_combo.get():
                self.config.anthropic_model = mid
                break

        for name, mid in OPENAI_MODELS:
            if name == self.openai_model_combo.get():
                self.config.openai_model = mid
                break

        for name, mid in OLLAMA_MODELS:
            if name == self.ollama_model_combo.get():
                self.config.ollama_model = mid
                break

        # Behavior
        self.config.rate_limit_enabled = self.rate_limit_var.get()
        try:
            self.config.token_limit = int(self.token_entry.get())
        except ValueError:
            self.config.token_limit = DEFAULT_TOKEN_LIMIT

        try:
            self.config.min_request_interval = int(self.interval_entry.get())
        except ValueError:
            self.config.min_request_interval = DEFAULT_MIN_REQUEST_INTERVAL

        self.config.debug_mode = self.debug_var.get()
        self.config.debug_logging = self.debug_logging_var.get()
        self.config.log_folder = self.log_folder_entry.get()

        # Interface
        self.config.always_on_top = self.always_on_top_var.get()
        if self.main_window and hasattr(self.main_window, 'root'):
            self.main_window.root.attributes("-topmost", self.config.always_on_top)

        # Prompts
        self.config.system_prompt_core = self.core_prompt_text.get("1.0", tk.END).strip()
        self.config.system_prompt_extended = self.extended_prompt_text.get("1.0", tk.END).strip()

        self.config.save()
        self.on_save()
        self.dialog.destroy()


class DebugWindow:
    """Debug window for previewing API requests before sending."""

    def __init__(self, parent: tk.Tk, debug_info: dict, send_callback: Callable[[dict], None]):
        """
        Args:
            parent: Parent tkinter window
            debug_info: Dict with keys: provider, model, prompt, system_prompt, api_key, token_estimate
            send_callback: Called with debug_info when user clicks Send
        """
        self.debug_info = debug_info
        self.send_callback = send_callback
        self.parent = parent

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Debug: Planned API Request")
        self.dialog.geometry("800x600")
        self.dialog.configure(bg=COLORS["bg"])

        self._create_widgets()

    def _create_widgets(self):
        """Create debug window widgets."""
        provider = self.debug_info.get("provider", "?")
        model = self.debug_info.get("model", "?")
        prompt = self.debug_info.get("prompt", "")
        system_prompt = self.debug_info.get("system_prompt", "")
        token_estimate = self.debug_info.get("token_estimate", 0)

        header = tk.Frame(self.dialog, bg=COLORS["bg_secondary"], padx=10, pady=10)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text=f"Provider: {provider.upper()} | Model: {model}",
            fg=COLORS["accent"],
            bg=COLORS["bg_secondary"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")

        tk.Label(
            header,
            text=f"Estimated tokens: ~{token_estimate}",
            fg=COLORS["text_secondary"],
            bg=COLORS["bg_secondary"],
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        if model in NO_SYSTEM_PROMPT_MODELS:
            tk.Label(
                header,
                text=f"Note: {model} doesn't support system prompts - will be merged into user prompt",
                fg=COLORS["accent"],
                bg=COLORS["bg_secondary"],
                font=("Segoe UI", 9),
            ).pack(anchor="w")

        self.status_label = tk.Label(
            header,
            text="DEBUG MODE: Request prepared but NOT sent",
            fg=COLORS["error"],
            bg=COLORS["bg_secondary"],
            font=("Segoe UI", 10, "bold"),
        )
        self.status_label.pack(anchor="w", pady=(5, 0))

        notebook = ttk.Notebook(self.dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # System prompt tab
        sys_frame = tk.Frame(notebook, bg=COLORS["bg"])
        notebook.add(sys_frame, text="System Prompt")

        sys_text = tk.Text(
            sys_frame,
            wrap=tk.WORD,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text"],
            font=("Consolas", 10),
            padx=10,
            pady=10,
        )
        sys_text.pack(fill=tk.BOTH, expand=True)
        sys_text.insert("1.0", system_prompt)
        sys_text.configure(state=tk.DISABLED)

        # User prompt tab
        prompt_frame = tk.Frame(notebook, bg=COLORS["bg"])
        notebook.add(prompt_frame, text="User Prompt")

        prompt_text = tk.Text(
            prompt_frame,
            wrap=tk.WORD,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text"],
            font=("Consolas", 10),
            padx=10,
            pady=10,
        )
        prompt_text.pack(fill=tk.BOTH, expand=True)
        prompt_text.insert("1.0", prompt)
        prompt_text.configure(state=tk.DISABLED)

        # Buttons
        btn_frame = tk.Frame(self.dialog, bg=COLORS["bg"])
        btn_frame.pack(pady=10)

        self.send_btn = tk.Button(
            btn_frame,
            text="Send to API",
            command=self._on_send,
            bg=COLORS["success"],
            fg=COLORS["bg"],
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT,
            padx=20,
            pady=5,
        )
        self.send_btn.pack(side=tk.LEFT, padx=(0, 10))

        close_btn = tk.Button(
            btn_frame,
            text="Close",
            command=self.dialog.destroy,
            bg=COLORS["button"],
            fg=COLORS["text"],
            font=("Segoe UI", 10),
            relief=tk.FLAT,
            padx=20,
            pady=5,
        )
        close_btn.pack(side=tk.LEFT)

    def _on_send(self):
        """Handle send button click."""
        self.send_btn.configure(state=tk.DISABLED)
        self.status_label.configure(text="Sending to API...", fg=COLORS["accent"])
        self.send_callback(self.debug_info)

    def update_status(self, text: str, color: str):
        """Update status label."""
        if self.dialog.winfo_exists():
            self.status_label.configure(text=text, fg=color)
