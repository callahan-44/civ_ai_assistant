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
        # Pattern for simple (non-chunked) format
        self.pattern_simple = re.compile(r">>>GAMESTATE>>>(.*?)<<<END<<<", re.DOTALL)
        # Pattern for chunked format: >>>GAMESTATE:N/M>>>...
        self.pattern_chunk = re.compile(r">>>GAMESTATE:(\d+)/(\d+)>>>(.*?)(?=>>>GAMESTATE:|<<<END<<<|$)", re.DOTALL)
        self.iteration_count = 0
        self.initialized = False

    def _extract_game_states(self, content: str) -> list:
        """
        Extract all complete game states from content.
        Handles both simple and chunked formats.
        Returns list of JSON strings.
        """
        game_states = []

        # First, find simple (non-chunked) game states
        for match in self.pattern_simple.finditer(content):
            game_states.append((match.start(), match.group(1).strip()))

        # Now find chunked game states
        # Look for complete chunk sets that end with <<<END<<<
        chunk_sets = re.findall(
            r">>>GAMESTATE:1/(\d+)>>>(.*?)<<<END<<<",
            content, re.DOTALL
        )

        for total_chunks_str, chunk_content in chunk_sets:
            total_chunks = int(total_chunks_str)
            # Extract the start position for sorting
            start_match = re.search(r">>>GAMESTATE:1/" + total_chunks_str + ">>>", content)
            start_pos = start_match.start() if start_match else 0

            # Find all chunks for this set
            chunks = {}
            # Re-search within this specific chunk set area
            chunk_area = content[start_pos:]
            end_pos = chunk_area.find("<<<END<<<")
            if end_pos > 0:
                chunk_area = chunk_area[:end_pos + len("<<<END<<<")]

            for chunk_match in re.finditer(r">>>GAMESTATE:(\d+)/" + total_chunks_str + r">>>(.*?)(?=>>>GAMESTATE:|<<<END<<<|$)", chunk_area, re.DOTALL):
                chunk_num = int(chunk_match.group(1))
                chunk_data = chunk_match.group(2)
                chunks[chunk_num] = chunk_data

            # Reassemble if we have all chunks
            if len(chunks) == total_chunks:
                full_json = "".join(chunks[i] for i in range(1, total_chunks + 1))
                game_states.append((start_pos, full_json.strip()))

        # Sort by position and return just the JSON strings
        game_states.sort(key=lambda x: x[0])
        return [gs[1] for gs in game_states]

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

            # Find ALL game states (handles both simple and chunked formats)
            game_state_jsons = self._extract_game_states(content)
            if game_state_jsons:
                # Only send the most recent (last) game state
                try:
                    game_state = json.loads(game_state_jsons[-1])
                    print(f"Found {len(game_state_jsons)} game state(s) in log, using most recent (turn {game_state.get('turn', '?')})")
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
        # Buffer to accumulate content for chunk reassembly
        pending_content = ""

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
                        pending_content = ""  # Reset buffer on file rotation

                    with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                        # Move to last known position
                        f.seek(self.last_position)
                        new_content = f.read()
                        self.last_position = f.tell()

                        # Add to pending buffer
                        pending_content += new_content

                        # Extract complete game states (handles chunked format)
                        game_state_jsons = self._extract_game_states(pending_content)
                        for gs_json in game_state_jsons:
                            try:
                                game_state = json.loads(gs_json)
                                self.callback(game_state)
                            except json.JSONDecodeError as e:
                                print(f"JSON parse error: {e}")

                        # Clear processed content from buffer (keep only after last <<<END<<<)
                        last_end = pending_content.rfind("<<<END<<<")
                        if last_end >= 0:
                            pending_content = pending_content[last_end + len("<<<END<<<"):]
                        # Prevent buffer from growing indefinitely
                        if len(pending_content) > 50000:
                            pending_content = pending_content[-10000:]

            except Exception as e:
                print(f"Log watcher error: {e}")

            time.sleep(1.0)  # Check every second
