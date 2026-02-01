"""
Log file watcher for the Civ VI AI Advisor.
Monitors Lua.log for game state updates.
"""

import re
import json
import time
import threading
from pathlib import Path
from typing import Optional, Callable


class LogWatcher:
    """Watches the Civ VI Lua.log file for game state updates."""

    # Trim log when it exceeds 5MB
    MAX_LOG_SIZE = 5 * 1024 * 1024
    # Check for trim every N iterations (every ~30 seconds)
    TRIM_CHECK_INTERVAL = 30

    def __init__(self, log_path: str, callback: Callable[[dict], None]):
        self.log_path = Path(log_path)
        self.callback = callback
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_position = 0
        self.pattern = re.compile(r">>>GAMESTATE>>>(.*?)<<<END<<<", re.DOTALL)
        self.iteration_count = 0
        self.initialized = False

    def start(self):
        """Start watching the log file."""
        self.running = True
        # On startup, find and send ONLY the most recent game state
        self._send_most_recent_state()
        self.thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.thread.start()

    def _send_most_recent_state(self):
        """Find and send only the most recent game state from the log."""
        try:
            if not self.log_path.exists():
                print("Log file not found, waiting for game...")
                return

            with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                # Move position to end of file for future reads
                self.last_position = f.tell()

            # Find ALL game states and only use the LAST one
            matches = self.pattern.findall(content)
            if matches:
                # Only send the most recent (last) game state
                try:
                    game_state = json.loads(matches[-1].strip())
                    print(f"Found {len(matches)} game state(s) in log, using most recent (turn {game_state.get('turn', '?')})")
                    self.callback(game_state)
                except json.JSONDecodeError as e:
                    print(f"JSON parse error on most recent state: {e}")
            else:
                print("No game states found in log yet")

            self.initialized = True

        except Exception as e:
            print(f"Error reading initial log state: {e}")

    def stop(self):
        """Stop watching the log file."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def _trim_log_if_needed(self):
        """Trim the log file if it exceeds the maximum size."""
        try:
            if not self.log_path.exists():
                return

            file_size = self.log_path.stat().st_size
            if file_size > self.MAX_LOG_SIZE:
                print(f"Log file size ({file_size / 1024 / 1024:.1f}MB) exceeds limit, trimming...")

                # Read the last portion of the file to preserve recent entries
                keep_size = self.MAX_LOG_SIZE // 4  # Keep ~1.25MB of recent logs
                with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(max(0, file_size - keep_size))
                    # Skip partial line at the start
                    if file_size > keep_size:
                        f.readline()
                    recent_content = f.read()

                # Write back the trimmed content
                with open(self.log_path, "w", encoding="utf-8") as f:
                    f.write("--- Log trimmed by CivAI Advisor ---\n")
                    f.write(recent_content)

                # Reset read position to start of new file
                self.last_position = 0
                print("Log file trimmed successfully")

        except PermissionError:
            # Game might have the file locked, skip this trim attempt
            print("Could not trim log (file in use), will retry later")
        except Exception as e:
            print(f"Error trimming log: {e}")

    def _watch_loop(self):
        """Main loop that tails the log file."""
        while self.running:
            try:
                # Periodically check if log needs trimming
                self.iteration_count += 1
                if self.iteration_count >= self.TRIM_CHECK_INTERVAL:
                    self.iteration_count = 0
                    self._trim_log_if_needed()

                if self.log_path.exists():
                    # Check if file was truncated/rotated (position beyond file size)
                    file_size = self.log_path.stat().st_size
                    if self.last_position > file_size:
                        self.last_position = 0

                    with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                        # Move to last known position
                        f.seek(self.last_position)
                        new_content = f.read()
                        self.last_position = f.tell()

                        # Search for game state markers
                        matches = self.pattern.findall(new_content)
                        for match in matches:
                            try:
                                game_state = json.loads(match.strip())
                                self.callback(game_state)
                            except json.JSONDecodeError as e:
                                print(f"JSON parse error: {e}")
            except Exception as e:
                print(f"Log watcher error: {e}")

            time.sleep(1.0)  # Check every second
