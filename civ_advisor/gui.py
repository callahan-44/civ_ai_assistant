"""
Main GUI overlay for the Civ VI AI Advisor.
Contains only the CivOverlay class - dialogs are in ui_dialogs.py.
"""

import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional

from .config import Config
from .llm_client import AIAdvisor, DebugRequest
from .log_watcher import LogWatcher
from .constants import COLORS, VICTORY_GOALS
from .ui_dialogs import (
    VictoryGoalDialog,
    SettingsDialog,
    DebugWindow,
)


class CivOverlay:
    """Main overlay window for the AI Advisor."""

    def __init__(self):
        self.config = Config()
        self.advisor = AIAdvisor(self.config)
        self.log_watcher: Optional[LogWatcher] = None
        self.last_game_state: Optional[dict] = None
        self._debug_window: Optional[DebugWindow] = None

        self._paused = False  # Pause toggle state

        self._create_window()
        self._show_victory_goal_dialog()
        self._create_widgets()
        self._position_window()
        self._start_log_watcher()

    def _show_victory_goal_dialog(self):
        """Show dialog to select victory goal on startup."""
        self.root.withdraw()
        VictoryGoalDialog(self.root, self.config)
        self.root.deiconify()

    def _create_window(self):
        """Create the main overlay window."""
        self.root = tk.Tk()
        self.root.title("Civ VI Advisor")
        self.root.configure(bg=COLORS["bg"])
        self.root.attributes("-topmost", self.config.always_on_top)
        self.root.attributes("-alpha", 0.92)
        self.root.overrideredirect(False)
        self.root.geometry("380x500")
        self.root.minsize(300, 400)
        self.root.resizable(True, True)

    def _create_widgets(self):
        """Create all UI widgets."""
        # Custom title bar
        title_bar = tk.Frame(self.root, bg=COLORS["bg_secondary"], height=30)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)

        title_label = tk.Label(
            title_bar,
            text="Civ VI AI Advisor",
            fg=COLORS["accent"],
            bg=COLORS["bg_secondary"],
            font=("Segoe UI", 11, "bold"),
        )
        title_label.pack(side=tk.LEFT, padx=10)

        settings_btn = tk.Button(
            title_bar,
            text="\u2699",
            command=self._open_settings,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text"],
            font=("Segoe UI", 12),
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        settings_btn.pack(side=tk.RIGHT, padx=5)

        close_btn = tk.Button(
            title_bar,
            text="\u2715",
            command=self._on_close,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text"],
            font=("Segoe UI", 10),
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        close_btn.pack(side=tk.RIGHT, padx=5)

        title_bar.bind("<Button-1>", self._start_drag)
        title_bar.bind("<B1-Motion>", self._on_drag)
        title_label.bind("<Button-1>", self._start_drag)
        title_label.bind("<B1-Motion>", self._on_drag)

        # Main content frame
        content = tk.Frame(self.root, bg=COLORS["bg"], padx=15, pady=10)
        content.pack(fill=tk.BOTH, expand=True)

        # Status indicator
        status_frame = tk.Frame(content, bg=COLORS["bg"])
        status_frame.pack(fill=tk.X, pady=(0, 10))

        self.status_dot = tk.Label(
            status_frame,
            text="\u25cf",
            fg=COLORS["text_secondary"],
            bg=COLORS["bg"],
            font=("Segoe UI", 8),
        )
        self.status_dot.pack(side=tk.LEFT)

        self.status_label = tk.Label(
            status_frame,
            text="Waiting for game data...",
            fg=COLORS["text_secondary"],
            bg=COLORS["bg"],
            font=("Segoe UI", 9),
        )
        self.status_label.pack(side=tk.LEFT, padx=(5, 0))

        # Pause toggle button
        self.pause_btn = tk.Button(
            status_frame,
            text="\u25b6 Active",  # Play symbol + Active
            command=self._toggle_pause,
            bg=COLORS["success"],
            fg=COLORS["bg"],
            font=("Segoe UI", 8, "bold"),
            relief=tk.FLAT,
            padx=8,
            pady=2,
            cursor="hand2",
        )
        self.pause_btn.pack(side=tk.RIGHT)

        # Advice display area
        advice_frame = tk.Frame(content, bg=COLORS["border"], bd=1)
        advice_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.advice_text = tk.Text(
            advice_frame,
            wrap=tk.WORD,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text"],
            font=("Segoe UI", 11),
            relief=tk.FLAT,
            padx=10,
            pady=10,
            state=tk.DISABLED,
            cursor="arrow",
            height=10,  # Prevent default 24 lines from consuming all space
        )
        self.advice_text.pack(fill=tk.BOTH, expand=True)

        # Victory goal input
        goal_frame = tk.Frame(content, bg=COLORS["bg"])
        goal_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            goal_frame,
            text="Victory Goal:",
            fg=COLORS["text_secondary"],
            bg=COLORS["bg"],
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        self.goal_var = tk.StringVar(value=self.config.victory_goal)
        goal_combo = ttk.Combobox(
            goal_frame,
            textvariable=self.goal_var,
            values=[g[0] for g in VICTORY_GOALS],
            state="readonly",
            width=35,
        )
        goal_combo.pack(fill=tk.X, pady=(3, 0))
        goal_combo.bind("<<ComboboxSelected>>", self._on_goal_changed)

        # Question input
        question_frame = tk.Frame(content, bg=COLORS["bg"])
        question_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            question_frame,
            text="Ask the Advisor:",
            fg=COLORS["text_secondary"],
            bg=COLORS["bg"],
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        self.question_entry = tk.Entry(
            question_frame,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            font=("Segoe UI", 10),
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["accent"],
        )
        self.question_entry.pack(fill=tk.X, pady=(3, 0), ipady=5)
        self.question_entry.bind("<Return>", self._on_ask)

        # Ask button
        ask_btn = tk.Button(
            content,
            text="Ask Advisor",
            command=self._on_ask,
            bg=COLORS["accent"],
            fg=COLORS["bg"],
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT,
            padx=15,
            pady=8,
            cursor="hand2",
        )
        ask_btn.pack(fill=tk.X)

        # Configure ttk style for readable comboboxes
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

    def _position_window(self):
        """Position window in top-right corner."""
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        x = screen_width - self.root.winfo_width() - 20
        y = 20
        self.root.geometry(f"+{x}+{y}")

    def _start_drag(self, event):
        """Start window drag."""
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag(self, event):
        """Handle window drag."""
        x = self.root.winfo_x() + event.x - self._drag_x
        y = self.root.winfo_y() + event.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _start_log_watcher(self):
        """Start the log file watcher."""
        if self.log_watcher:
            self.log_watcher.stop()
        self.log_watcher = LogWatcher(str(self.config.get_log_path()), self._on_game_state)
        self.log_watcher.start()

    def _on_game_state(self, game_state: dict):
        """Handle new game state from log watcher."""
        self.last_game_state = game_state
        if self._paused:
            self.root.after(0, self._update_status, "Game state received (paused)", COLORS["error"])
        else:
            self.root.after(0, self._update_status, "Game state received", COLORS["success"])
            self.root.after(0, self._request_advice)

    def _update_status(self, text: str, color: str = None):
        """Update status label."""
        self.status_label.configure(text=text)
        if color:
            self.status_dot.configure(fg=color)

    def _set_advice(self, text: str):
        """Update the advice display."""
        self.advice_text.configure(state=tk.NORMAL)
        self.advice_text.delete("1.0", tk.END)
        self.advice_text.insert("1.0", text)
        self.advice_text.configure(state=tk.DISABLED)

    def _on_goal_changed(self, event=None):
        """Handle victory goal change."""
        self.config.victory_goal = self.goal_var.get()
        self.config.save()

    def _toggle_pause(self):
        """Toggle pause state for API requests."""
        self._paused = not self._paused
        if self._paused:
            self.pause_btn.configure(
                text="\u23f8 Paused",  # Pause symbol
                bg=COLORS["error"],
            )
            self._update_status("Paused - requests disabled", COLORS["error"])
        else:
            self.pause_btn.configure(
                text="\u25b6 Active",  # Play symbol
                bg=COLORS["success"],
            )
            self._update_status("Active - ready for requests", COLORS["success"])

    def _clipboard_copy(self, text: str) -> bool:
        """Copy text to clipboard. Returns True on success."""
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
            return True
        except Exception:
            return False

    def _request_advice(self, user_question: str = ""):
        """Request advice from AI in background thread."""
        # Check if paused
        if self._paused:
            self._set_advice("Advisor is paused.\n\nClick the 'Paused' button to resume.")
            return

        # Always include full game state and system prompt with questions
        if not self.last_game_state:
            self._set_advice("No game data available yet. Start a game or load a save.")
            return

        self._set_advice("Consulting Advisor...")
        self._update_status("Consulting AI...", COLORS["accent"])

        def get_advice_thread():
            result = self.advisor.get_advice(
                self.last_game_state,
                user_question,
                self.goal_var.get(),
                clipboard_copy_func=self._clipboard_copy,
            )

            # Check if it's a debug request
            if isinstance(result, DebugRequest):
                self.root.after(0, lambda: self._show_debug_window(result))
                self.root.after(0, self._set_advice,
                    f"DEBUG MODE\n\nRequest prepared but NOT sent.\n"
                    f"Check debug popup for details.\n"
                    f"Click 'Send to API' to transmit.\n\n"
                    f"Provider: {result.provider}\n"
                    f"Model: {result.model}\n"
                    f"Estimated tokens: ~{result.token_estimate}")
                self.root.after(0, self._update_status, "Debug mode", COLORS["accent"])
            else:
                self.root.after(0, self._set_advice, result)
                # Show the model that actually responded (helps detect fallback)
                model_used = self.advisor._last_used_model or "unknown"
                self.root.after(0, self._update_status, f"Ready | {model_used}", COLORS["success"])

        thread = threading.Thread(target=get_advice_thread, daemon=True)
        thread.start()

    def _show_debug_window(self, debug_request: DebugRequest):
        """Show debug window for a debug request."""
        def on_send(debug_info: dict):
            def send_thread():
                result = self.advisor.execute_debug_request(debug_info)
                self.root.after(0, self._set_advice, result)
                # Show the model that actually responded
                model_used = self.advisor._last_used_model or "unknown"
                self.root.after(0, self._update_status, f"Ready | {model_used}", COLORS["success"])
                if self._debug_window:
                    self._debug_window.update_status("Request sent successfully!", COLORS["success"])

            thread = threading.Thread(target=send_thread, daemon=True)
            thread.start()

        self._debug_window = DebugWindow(self.root, debug_request.to_dict(), on_send)

    def _on_ask(self, event=None):
        """Handle ask button click."""
        question = self.question_entry.get().strip()
        self.question_entry.delete(0, tk.END)
        self._request_advice(question)

    def _open_settings(self):
        """Open settings dialog."""
        SettingsDialog(self.root, self.config, self._on_settings_saved, main_window=self)

    def _on_settings_saved(self):
        """Handle settings save."""
        self._start_log_watcher()
        # Apply always-on-top setting
        self.root.attributes("-topmost", self.config.always_on_top)

    def _on_close(self):
        """Handle window close."""
        if self.log_watcher:
            self.log_watcher.stop()
        self.root.destroy()

    def run(self):
        """Start the main event loop."""
        self.root.mainloop()
